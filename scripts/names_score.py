"""Score the names test for every model that has been run."""

import json

import numpy as np

from jevmap import geo

RAW = geo.ROOT / "results" / "raw"
MODELS = ["jev", "clef", "clef-flash", "laya-typed", "laya-english", "laya-multilingual"]


def score() -> dict:
    items = json.loads((RAW / "names_items.json").read_text())
    truth = {i["id"]: i for i in items["cities"] + items["countries"]}
    out = {}
    for m in MODELS:
        path = RAW / f"names_{m}.jsonl"
        if not path.exists():
            continue
        recs = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        res = {}
        for task in ["continent", "north", "east", "lat_band", "lon_band"]:
            for kind in ["city", "country"]:
                rows = [r for r in recs if r["id"].startswith(kind + ":") and task in r]
                if not rows:
                    continue
                ok = []
                for r in rows:
                    t = truth[r["id"]][task]
                    a = r[task]
                    ok.append((a["p"] >= 0.5) == t if "p" in a else a["choice"] == t)
                res[f"{kind}_{task}"] = float(np.mean(ok))
        out[m] = res
    # Chance / majority baselines for reference.
    cs = items["cities"]
    out["_baseline"] = {
        "city_continent": max(np.mean([c["continent"] == k for c in cs]) for k in geo.CONTINENTS),
        "city_north": max(np.mean([c["north"] for c in cs]), 1 - np.mean([c["north"] for c in cs])),
        "city_east": max(np.mean([c["east"] for c in cs]), 1 - np.mean([c["east"] for c in cs])),
        "city_lat_band": max(np.mean([c["lat_band"] == b for c in cs]) for b in set(c["lat_band"] for c in cs)),
        "city_lon_band": max(np.mean([c["lon_band"] == b for c in cs]) for b in set(c["lon_band"] for c in cs)),
    }
    (geo.ROOT / "results" / "metrics" / "names.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    out = score()
    keys = ["city_continent", "country_continent", "city_north", "city_east", "city_lat_band", "city_lon_band"]
    print(f"{'model':18}" + "".join(f"{k:>18}" for k in keys))
    for m, r in out.items():
        print(f"{m:18}" + "".join(f"{r.get(k, float('nan')):18.1%}" for k in keys))
