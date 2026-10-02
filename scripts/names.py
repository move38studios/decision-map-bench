"""Names, not numbers: the same geography asked with place names instead of coordinates.

Items: the 500 most populous Natural Earth places (state = city name) and every admin-0 country
(state = country name). Truth: Natural Earth coordinates and continent.

Usage: uv run python -m scripts.names jev|clef|clef-flash|laya-typed|laya-english|laya-multilingual
"""

import asyncio
import json
import sys

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy

from dotenv import load_dotenv

from jevmap import backends, geo

load_dotenv()

RAW = geo.ROOT / "results" / "raw"
LAT_BANDS = ["60°N to 90°N", "30°N to 60°N", "0° to 30°N", "0° to 30°S", "30°S to 60°S", "60°S to 90°S"]
LON_BANDS = ["180°W to 120°W", "120°W to 60°W", "60°W to 0°", "0° to 60°E", "60°E to 120°E", "120°E to 180°E"]


def lat_band(lat: float) -> str:
    return LAT_BANDS[min(5, int((90 - lat) // 30))]


def lon_band(lon: float) -> str:
    return LON_BANDS[min(5, int((lon + 180) // 60))]


def cities() -> list[dict]:
    feats = json.loads((geo.DATA / "ne_50m_populated_places_simple.geojson").read_text())["features"]
    rows = sorted((f["properties"] for f in feats), key=lambda p: -p["pop_max"])
    out, seen = [], set()
    for p in rows:
        if p["name"] in seen:
            continue
        lat, lon = p["latitude"], p["longitude"]
        country = geo.country_of([(lat, lon)])[0]
        cont = geo.continent_of(country, lon)
        if not cont:
            continue
        seen.add(p["name"])
        out.append({"id": f"city:{p['name']}", "state": p["name"], "lat": lat, "lon": lon, "continent": cont,
                    "north": lat > 0, "east": lon > 0, "lat_band": lat_band(lat), "lon_band": lon_band(lon)})
        if len(out) == 500:
            break
    return out


def countries() -> list[dict]:
    names, geoms = geo.countries()
    out = []
    for name, g in zip(names, geoms):
        c = g.representative_point()
        cont = geo.continent_of(name, c.x)
        if cont and name != "Russia":
            out.append({"id": f"country:{name}", "state": name, "continent": cont})
    return out


CITY_QUESTIONS = {
    "continent": Choice(instructions="Which continent is this city in?", criteria={c: None for c in geo.CONTINENTS}),
    "north": Noul(instructions="This city is in the northern hemisphere."),
    "east": Noul(instructions="This city is east of the Prime Meridian (Greenwich)."),
    "lat_band": Choice(instructions="Which latitude band is this city in?", criteria={b: None for b in LAT_BANDS}),
    "lon_band": Choice(instructions="Which longitude band is this city in?", criteria={b: None for b in LON_BANDS}),
}
COUNTRY_QUESTIONS = {
    "continent": Choice(instructions="Which continent is this country or territory in?", criteria={c: None for c in geo.CONTINENTS}),
}


def dump(qs: dict) -> dict:
    return {k: q.model_dump(mode="json") for k, q in qs.items()}


def record(item: dict, answers: dict) -> dict:
    out = {"id": item["id"]}
    for k, a in answers.items():
        if not isinstance(a, dict):
            a = {"type": a.type, "noul": getattr(a, "noul", None), "choice": getattr(a, "choice", None),
                 "probabilities": getattr(a, "probabilities", None)}
        out[k] = {"p": a["noul"]} if a["type"] == "noul" else {"choice": a["choice"], "probs": a["probabilities"]}
    return out


async def run_api(model: str, jobs: list[tuple[dict, dict]]) -> list[dict]:
    if model == "jev":
        client = AsyncTypeSafeClient(model="jev-latest", retry=RetryPolicy(max_retries=8, backoff_max=20.0))
    else:
        client = backends.CloudflareClient(model)
    sem = asyncio.Semaphore(16)
    async with client:
        async def one(item, qs):
            async with sem:
                r = await client.system_one(state=item["state"], questions=qs)
                return record(item, r.answers)
        return await asyncio.gather(*(one(i, q) for i, q in jobs))


def run_laya(model: str, groups: list[tuple[list[dict], dict]]) -> list[dict]:
    import modal

    from scripts.modal_laya import Laya, app

    ckpt = {"laya-english": "english", "laya-multilingual": "multilingual", "laya-typed": "typed-decisions"}[model]
    out = []
    with app.run():
        m = Laya(checkpoint=ckpt)
        for items, qs in groups:
            res = m.same_questions.remote([i["state"] for i in items], dump(qs))
            out += [record(i, r["answers"]) for i, r in zip(items, res)]
    return out


if __name__ == "__main__":
    model = sys.argv[1]
    cs, ks = cities(), countries()
    if model.startswith("laya"):
        recs = run_laya(model, [(cs, CITY_QUESTIONS), (ks, COUNTRY_QUESTIONS)])
    else:
        jobs = [(c, CITY_QUESTIONS) for c in cs] + [(k, COUNTRY_QUESTIONS) for k in ks]
        recs = asyncio.run(run_api(model, jobs))
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"names_{model}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n")
    (RAW / "names_items.json").write_text(json.dumps({"cities": cs, "countries": ks}, ensure_ascii=False, indent=1))
    print(model, len(recs), "records")
