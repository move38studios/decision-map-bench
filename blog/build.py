"""Build blog/index.html ("How well do decision models know geography?") from results/.

Usage: uv run python -m blog.build
"""

import html
import json
import shutil

from jevmap import bench, geo, runner
from scripts.analysis import CLAUDE

ROOT = geo.ROOT
OUT = ROOT / "blog"
IMG = OUT / "img"
MAPS = ROOT / "results" / "maps"
MET = ROOT / "results" / "metrics"

B = json.loads((MET / "bench_2deg.json").read_text())
N = json.loads((MET / "names.json").read_text())
M = B["models"]
WATER = B["water_baseline"]


def _best(k: str) -> dict:
    st = M.get(f"{k}-state")
    if bench.BEST_LAYOUT.get(k) == "state" and st and all(x in st for x in ("political", "continent_accuracy", "physical_terrain", "physical_colour")):
        return st
    return M[k]


MB = {k: _best(k) for k in ("jev", "clef", "clef-flash", "laya-typed")}


def _conf_median(k: str) -> float:
    import statistics
    name = bench.run_name(k, "political", bench.section_layout(k))
    return statistics.median(r["confidence"] for r in runner.load(name).values())


CONF_MED = {k: _conf_median(k) for k in ("jev", "clef")}

KEYS = ["jev", "clef", "clef-flash", "laya-typed"]
NAME = {"jev": "Jev 1.13", "clef": "Clef", "clef-flash": "Clef-flash", "laya-typed": "Laya typed-decisions"}
CSSVAR = {"jev": "var(--m-jev)", "clef": "var(--m-clef)", "clef-flash": "var(--m-flash)", "laya-typed": "var(--m-laya)"}


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def img(name: str, alt: str, cap: str = "") -> str:
    c = f"<figcaption>{cap}</figcaption>" if cap else ""
    return f'<figure><img src="img/{name}.png" alt="{esc(alt)}" width="945" height="476" loading="lazy">{c}</figure>'


def dot(key: str) -> str:
    return f'<i class="sw" style="background:{CSSVAR[key]}"></i>'


# ------------------------------------------------------------------ numbers used in the text
SL = B.get("state_layout", {})
oc = {k: (SL[k] if bench.BEST_LAYOUT[k] == "state" else M[k]["land"]["orig_choice"]) for k in KEYS}
MIR = json.loads((MET / "bench_mirror.json").read_text())
lay_rows = ""
for k in KEYS:
    q, st = M[k]["land"]["orig_choice"], SL.get(k)
    if st is None:
        continue
    lay_rows += (f"<tr><td>{dot(k)}{NAME[k]}</td><td>{pct(q['accuracy'])}</td><td>{q['auc']:.2f}</td><td>{q['ece']:.3f}</td>"
                 f"<td>{pct(st['accuracy'])}</td><td>{st['auc']:.2f}</td><td>{st['ece']:.3f}</td></tr>")
mir_rows = f"<tr><td>Real world</td><td>{MIR['truth']['ew']:.2f}</td><td>{MIR['truth']['ns']:.2f}</td></tr>" + "".join(
    f"<tr><td>{dot(k)}{NAME[k]}</td><td>{MIR[k + '_' + bench.BEST_LAYOUT[k]]['ew']:.2f}</td><td>{MIR[k + '_' + bench.BEST_LAYOUT[k]]['ns']:.2f}</td></tr>"
    for k in ("jev", "clef", "clef-flash")
)
cost_total = 0.0
for f in (ROOT / "results" / "raw").glob("*.usage.jsonl"):
    meta = f.with_name(f.name.replace(".usage.jsonl", ".meta.json"))
    backend = json.loads(meta.read_text()).get("backend", "jev") if meta.exists() else "jev"
    price = {"jev": 0.042, "clef": 0.24, "clef-flash": 0.24}.get(backend, 0.0)
    cost_total += sum((json.loads(l)["input_tokens"] or 0) for l in f.read_text().splitlines()) / 1e6 * price

# Determinism (repeat runs on the 10 degree grid).
det = {}
for k in ("jev", "clef", "clef-flash"):
    a, b = runner.load(f"det_{k}_1"), runner.load(f"det_{k}_2")
    diffs = [abs(a[i]["probs"]["Land"] - b[i]["probs"]["Land"]) for i in a]
    det[k] = {"mean": sum(diffs) / len(diffs), "max": max(diffs), "flips": sum(a[i]["choice"] != b[i]["choice"] for i in a), "n": len(a)}

# Speed and cost per 2 degree land/water map.
speed = {}
for k in ("jev", "clef", "clef-flash"):
    rows = [json.loads(l) for l in runner.paths(bench.run_name(k, "orig_choice"))[1].read_text().splitlines()]
    speed[k] = {
        "s_per_req": sum(r["seconds"] for r in rows) / len(rows),
        "per_req": sum(r["points"] for r in rows) / len(rows),
        "tok_per_q": sum(r["input_tokens"] for r in rows) / sum(r["points"] for r in rows),
        "map_cost": runner.usage(bench.run_name(k, "orig_choice"))["cost_usd"],
    }

# ------------------------------------------------------------------ chart: accuracy vs Claudes
rows = [(k, v / 100, "claude") for k, v in CLAUDE.items()] + [(NAME[k], oc[k]["accuracy"], k) for k in KEYS]
rows.sort(key=lambda r: -r[1])
LO, HI = 0.2, 1.0


def xs(v: float) -> float:
    return (v - LO) / (HI - LO) * 100


bars = "".join(
    f'<div class="bar {"dm" if t != "claude" else ""}"><span class="bl">{esc(n)}</span>'
    f'<span class="bt"><span class="bf" style="width:{xs(v):.2f}%;{"background:" + CSSVAR[t] if t != "claude" else ""}"></span></span>'
    f'<span class="bv">{pct(v)}</span></div>'
    for n, v, t in rows
)
bar_ticks = "".join(f'<span style="left:{xs(t):.1f}%">{int(t * 100)}</span>' for t in (0.2, 0.4, 0.6, 0.8, 1.0))
base_x = xs(WATER)

# ------------------------------------------------------------------ table: every question type
SRC = bench.LAND_SOURCES
src_head = "".join(f"<th>{esc(bench.SOURCE_LABEL[s])}</th>" for s in SRC)
qt_rows = ""
for k in KEYS:
    cells = ""
    for s in SRC:
        v = M[k]["land"][s]["accuracy"]
        a = M[k]["land"][s]["auc"]
        shade = max(0.0, min(1.0, (v - WATER) / (0.9 - WATER)))
        cells += f'<td style="--s:{shade:.2f}"><b>{pct(v)}</b><small>AUC {a:.2f}</small></td>'
    qt_rows += f"<tr><th>{dot(k)}{NAME[k]}</th>{cells}</tr>"

# ------------------------------------------------------------------ chart: calibration
W, H, P = 360, 330, 44


def cx(v):
    return P + v * (W - P - 14)


def cy(v):
    return H - P - v * (H - P - 14)


cal = []
for t in (0, 0.2, 0.4, 0.6, 0.8, 1.0):
    cal.append(f'<line x1="{cx(t)}" y1="{cy(0)}" x2="{cx(t)}" y2="{cy(1)}" class="g"/><line x1="{cx(0)}" y1="{cy(t)}" x2="{cx(1)}" y2="{cy(t)}" class="g"/>')
    cal.append(f'<text x="{cx(t)}" y="{cy(0) + 16}" class="tk" text-anchor="middle">{t:.1f}</text><text x="{cx(0) - 6}" y="{cy(t) + 4}" class="tk" text-anchor="end">{t:.1f}</text>')
cal.append(f'<line x1="{cx(0)}" y1="{cy(0)}" x2="{cx(1)}" y2="{cy(1)}" class="diag"/>')
for k in KEYS:
    pts = [(c["mean_p"], c["land_fraction"]) for c in oc[k]["calibration"] if c["points"] >= 30]
    cal.append(f'<polyline points="{" ".join(f"{cx(a):.1f},{cy(b):.1f}" for a, b in pts)}" fill="none" style="stroke:{CSSVAR[k]}" stroke-width="2"/>')
    cal += [f'<circle cx="{cx(a):.1f}" cy="{cy(b):.1f}" r="3" style="fill:{CSSVAR[k]}"/>' for a, b in pts]
cal.append(f'<text x="{(cx(0) + cx(1)) / 2}" y="{H - 6}" class="ax" text-anchor="middle">Model’s P(Land)</text>')
cal.append(f'<text x="13" y="{(cy(0) + cy(1)) / 2}" class="ax" text-anchor="middle" transform="rotate(-90 13 {(cy(0) + cy(1)) / 2})">Share that is land</text>')
cal_svg = f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Calibration curves">{"".join(cal)}</svg>'
cal_table = "".join(
    f"<tr><td>{dot(k)}{NAME[k]}</td><td>{oc[k]['ece']:.3f}</td><td>{oc[k]['brier']:.3f}</td><td>{oc[k]['best_threshold']:.2f}</td><td>{pct(oc[k]['best_accuracy'])}</td></tr>"
    for k in KEYS
)

# ------------------------------------------------------------------ chart: names vs coordinates
NM = ["jev", "clef", "clef-flash", "laya-typed"]
dumb = []
DW, DH, DL = 560, 40 + 44 * len(NM), 150


def dx(v):
    return DL + v * (DW - DL - 20)


for t in (0, 0.25, 0.5, 0.75, 1.0):
    dumb.append(f'<line x1="{dx(t)}" y1="22" x2="{dx(t)}" y2="{DH - 22}" class="g"/><text x="{dx(t)}" y="{DH - 6}" class="tk" text-anchor="middle">{int(t * 100)}%</text>')
for r, k in enumerate(NM):
    y = 40 + r * 44
    by_name = N[k]["city_continent"]
    by_coord = MB[k].get("continent_accuracy", 0.0)
    dumb.append(f'<text x="{DL - 10}" y="{y + 4}" class="lbl" text-anchor="end">{esc(NAME[k])}</text>')
    dumb.append(f'<line x1="{dx(min(by_name, by_coord))}" y1="{y}" x2="{dx(max(by_name, by_coord))}" y2="{y}" class="conn"/>')
    dumb.append(f'<circle cx="{dx(by_coord)}" cy="{y}" r="6" class="hollow" style="stroke:{CSSVAR[k]}"><title>coordinate: {pct(by_coord)}</title></circle>')
    dumb.append(f'<circle cx="{dx(by_name)}" cy="{y}" r="6" style="fill:{CSSVAR[k]}"><title>name: {pct(by_name)}</title></circle>')
    dumb.append(f'<text x="{dx(by_name)}" y="{y - 11}" class="tk" text-anchor="middle">{pct(by_name, 0)}</text>')
    dumb.append(f'<text x="{dx(by_coord)}" y="{y + 20}" class="tk" text-anchor="middle">{pct(by_coord, 0)}</text>')
dumb_svg = f'<svg viewBox="0 0 {DW} {DH}" role="img" aria-label="Continent accuracy by place name versus by coordinate">{"".join(dumb)}</svg>'
names_rows = "".join(
    f"<tr><td>{dot(k) if k in CSSVAR else ''}{esc(NAME.get(k, k))}</td>"
    + "".join(f"<td>{pct(N[k][c], 0)}</td>" for c in ("city_continent", "country_continent", "city_north", "city_east", "city_lat_band", "city_lon_band"))
    + "</tr>"
    for k in ("jev", "clef", "clef-flash", "laya-typed", "laya-english", "laya-multilingual")
)
nb = N["_baseline"]
names_rows += "<tr class='base'><td>Most common answer</td>" + "".join(
    f"<td>{pct(nb[c], 0) if c in nb else '–'}</td>" for c in ("city_continent", "country_continent", "city_north", "city_east", "city_lat_band", "city_lon_band")
) + "</tr>"

# ------------------------------------------------------------------ chart: confidence vs coverage (political)
PW, PH, PP = 360, 300, 44


def px(v):
    return PP + v * (PW - PP - 14)


def py(v):
    return PH - PP - (v - 0.3) / 0.7 * (PH - PP - 14)


pol = ["jev", "clef", "clef-flash"]
cc = []
for t in (0, 0.25, 0.5, 0.75, 1.0):
    cc.append(f'<line x1="{px(t)}" y1="{py(0.3)}" x2="{px(t)}" y2="{py(1)}" class="g"/><text x="{px(t)}" y="{py(0.3) + 16}" class="tk" text-anchor="middle">{int(t * 100)}%</text>')
for t in (0.3, 0.5, 0.7, 0.9, 1.0):
    cc.append(f'<line x1="{px(0)}" y1="{py(t)}" x2="{px(1)}" y2="{py(t)}" class="g"/><text x="{px(0) - 6}" y="{py(t) + 4}" class="tk" text-anchor="end">{int(t * 100)}%</text>')
for k in pol:
    pts = [(c["coverage"], c["accuracy"]) for c in MB[k]["political"]["confidence_curve"]]
    cc.append(f'<polyline points="{" ".join(f"{px(a):.1f},{py(b):.1f}" for a, b in pts)}" fill="none" style="stroke:{CSSVAR[k]}" stroke-width="2"/>')
cc.append(f'<text x="{(px(0) + px(1)) / 2}" y="{PH - 6}" class="ax" text-anchor="middle">Land points answered (highest confidence first)</text>')
cc.append(f'<text x="13" y="{(py(0.3) + py(1)) / 2}" class="ax" text-anchor="middle" transform="rotate(-90 13 {(py(0.3) + py(1)) / 2})">Right country</text>')
cc_svg = f'<svg viewBox="0 0 {PW} {PH}" role="img" aria-label="Political accuracy against coverage when keeping only confident answers">{"".join(cc)}</svg>'


def at_cov(k: str, target: float) -> str:
    curve = MB[k]["political"]["confidence_curve"]
    best = min(curve, key=lambda c: abs(c["coverage"] - target))
    return pct(best["accuracy"])


pol_rows = "".join(
    f"<tr><td>{dot(k)}{NAME[k]}</td><td>{pct(MB[k]['political']['accuracy_land'])}</td><td>{pct(MB[k]['political']['top3_land'])}</td>"
    f"<td>{at_cov(k, 0.5)}</td><td>{pct(MB[k]['political']['ocean_recall'])}</td><td>{len(MB[k]['political']['never_chosen'])}</td></tr>"
    for k in pol
)


def country_acc(k: str, names: list[str]) -> list[str]:
    by = {r["country"]: r["accuracy"] for r in MB[k]["political"]["per_country"]}
    return [pct(by.get(n, float("nan")), 0) for n in names]


CN = ["Russia", "Canada", "United States of America", "China", "Brazil", "Australia", "India", "Argentina", "Kazakhstan", "Algeria", "Democratic Republic of the Congo", "Saudi Arabia"]
CN_LABEL = {"United States of America": "USA", "Democratic Republic of the Congo": "DR Congo"}
cn_rows = "".join(
    f"<tr><td>{CN_LABEL.get(n, n)}</td>" + "".join(f"<td>{v}</td>" for v in (country_acc(k, [n])[0] for k in pol)) + "</tr>" for n in CN
)

# ------------------------------------------------------------------ continents and physical
cont_rows = "".join(
    f"<tr><td>{c}</td>" + "".join(f"<td>{pct(MB[k]['continent_by'][c], 0)}</td>" for k in KEYS) + "</tr>" for c in geo.CONTINENTS
)
cont_rows += "<tr class='tot'><td>All land</td>" + "".join(f"<td>{pct(MB[k]['continent_accuracy'], 1)}</td>" for k in KEYS) + "</tr>"
cont_rows += "<tr><td>Ocean points called an ocean</td>" + "".join(f"<td>{pct(MB[k]['continent_ocean_recall'], 1)}</td>" for k in KEYS) + "</tr>"
phys_rows = "".join(
    f"<tr><td>{dot(k)}{NAME[k]}</td><td>{pct(MB[k]['physical_terrain']['accuracy'])}</td><td>{pct(MB[k]['physical_terrain']['within_one'])}</td>"
    f"<td>{pct(MB[k]['physical_colour']['accuracy'])}</td><td>{pct(MB[k]['physical_colour']['within_one'])}</td></tr>"
    for k in KEYS
)

# ------------------------------------------------------------------ practical table
prac = ""
for k in ("jev", "clef", "clef-flash"):
    s, d = speed[k], det[k]
    prac += (f"<tr><td>{dot(k)}{NAME[k]}</td><td>Hosted API</td><td>${ {'jev': 0.042, 'clef': 0.24, 'clef-flash': 0.24}[k] }</td>"
             f"<td>{s['tok_per_q']:.0f}</td><td>${s['map_cost']:.2f}</td><td>{s['s_per_req']:.2f} s / {s['per_req']:.0f} q</td>"
             f"<td>{d['flips']} of {d['n']} ({d['mean']:.3f})</td></tr>")
prac += f"<tr><td>{dot('laya-typed')}{NAME['laya-typed']}</td><td>Open weights (Apache-2.0)</td><td>own GPU</td><td>–</td><td>&lt; $0.01 GPU</td><td>16,200 q in 6–30 s on one L4</td><td>–</td></tr>"

# ------------------------------------------------------------------ images
IMAGES = ["bench_sheet", "bench_land_truth"] + [f"bench_p_land_{k}" for k in KEYS] + \
    ["bench_continent_truth"] + [f"bench_continent_{k}" for k in KEYS] + \
    ["bench_political_truth"] + [f"bench_political_{k}" for k in pol] + [f"bench_political_all_{k}" for k in pol] + \
    ["bench_physical_truth"] + [f"bench_physical_colour_{k}" for k in KEYS]
IMG.mkdir(parents=True, exist_ok=True)
for n in IMAGES:
    shutil.copy(MAPS / f"{n}.png", IMG / f"{n}.png")

LAYOUT_NOTE = {"question": "coordinate in question", "state": "coordinate as state"}
prob_figs = "".join(img(f"bench_p_land_{k}", f"{NAME[k]} probability of land", f"{dot(k)}{NAME[k]} · AUC {oc[k]['auc']:.2f} · {LAYOUT_NOTE[bench.BEST_LAYOUT[k]]}") for k in KEYS)
cont_figs = img("bench_continent_truth", "True continents", "Truth") + "".join(
    img(f"bench_continent_{k}", f"{NAME[k]} continent answers", f"{dot(k)}{NAME[k]} · {pct(MB[k]['continent_accuracy'])}") for k in KEYS[:3]
)
pol_figs = img("bench_political_truth", "True political map", "Truth") + "".join(
    img(f"bench_political_{k}", f"{NAME[k]} country answers on land", f"{dot(k)}{NAME[k]} · {pct(MB[k]['political']['accuracy_land'])} of land") for k in pol
)
phys_figs = img("bench_physical_truth", "True physical map", "Truth (ETOPO1)") + "".join(
    img(f"bench_physical_colour_{k}", f"{NAME[k]} physical map", f"{dot(k)}{NAME[k]}") for k in KEYS[:3]
)

subs = {
    "WATER": pct(WATER),
    "CLEF_CONF_MED": f"{CONF_MED['clef']:.2f}",
    "JEV_CONF_MED": f"{CONF_MED['jev']:.2f}",
    "FLASH_CONT_Q": pct(M["clef-flash"]["continent_accuracy"]),
    "FLASH_CONT": pct(MB["clef-flash"]["continent_accuracy"]),
    "CLEF_TERR": pct(MB["clef"]["physical_terrain"]["accuracy"]),
    "JEV_TERR_W1": pct(MB["jev"]["physical_terrain"]["within_one"]),
    "LAY_ROWS": lay_rows,
    "MIR_ROWS": mir_rows,
    "FLASH_Q_ACC": pct(M["clef-flash"]["land"]["orig_choice"]["accuracy"]),
    "BASE_X": f"{base_x:.2f}",
    "BARS": bars,
    "BAR_TICKS": bar_ticks,
    "SRC_HEAD": src_head,
    "QT_ROWS": qt_rows,
    "CAL_SVG": cal_svg,
    "CAL_ROWS": cal_table,
    "DUMB_SVG": dumb_svg,
    "NAMES_ROWS": names_rows,
    "CC_SVG": cc_svg,
    "POL_ROWS": pol_rows,
    "CN_ROWS": cn_rows,
    "CONT_ROWS": cont_rows,
    "PHYS_ROWS": phys_rows,
    "PRAC_ROWS": prac,
    "PROB_FIGS": prob_figs,
    "CONT_FIGS": cont_figs,
    "POL_FIGS": pol_figs,
    "PHYS_FIGS": phys_figs,
    "COST_TOTAL": f"${cost_total:.0f}",
    "JEV_ACC": pct(oc["jev"]["accuracy"]),
    "CLEF_ACC": pct(oc["clef"]["accuracy"]),
    "FLASH_ACC": pct(oc["clef-flash"]["accuracy"]),
    "LAYA_ACC": pct(oc["laya-typed"]["accuracy"]),
    "JEV_AUC": f"{oc['jev']['auc']:.2f}",
    "CLEF_AUC": f"{oc['clef']['auc']:.2f}",
    "FLASH_AUC": f"{oc['clef-flash']['auc']:.2f}",
    "LAYA_AUC": f"{oc['laya-typed']['auc']:.2f}",
    "JEV_CONT": pct(MB["jev"]["continent_accuracy"]),
    "CLEF_CONT": pct(MB["clef"]["continent_accuracy"]),
    "FLASH_CONT": pct(MB["clef-flash"]["continent_accuracy"]),
    "JEV_NAME_CONT": pct(N["jev"]["city_continent"]),
    "CLEF_NAME_CONT": pct(N["clef"]["city_continent"]),
    "JEV_POL": pct(MB["jev"]["political"]["accuracy_land"]),
    "CLEF_POL": pct(MB["clef"]["political"]["accuracy_land"]),
    "FLASH_POL": pct(MB["clef-flash"]["political"]["accuracy_land"]),
    "JEV_POL50": at_cov("jev", 0.5),
    "CLEF_POL50": at_cov("clef", 0.5),
    "JEV_DET_FLIPS": f"{det['jev']['flips']} of {det['jev']['n']}",
    "JEV_DET_MAX": f"{det['jev']['max']:.2f}",
    "JEV_RANGE": f"{pct(min(M['jev']['land'][s]['accuracy'] for s in SRC), 0)}–{pct(max(M['jev']['land'][s]['accuracy'] for s in SRC), 0)}",
    "CLEF_RANGE": f"{pct(min(M['clef']['land'][s]['accuracy'] for s in SRC), 0)}–{pct(max(M['clef']['land'][s]['accuracy'] for s in SRC), 0)}",
    "JEV_EAST": pct(N["jev"]["city_east"], 0),
    "CLEF_EAST": pct(N["clef"]["city_east"], 0),
    "CLEF_OCEAN": pct(MB["clef"]["political"]["ocean_recall"], 0),
    "JEV_OCEAN": pct(MB["jev"]["political"]["ocean_recall"], 0),
}
page = (OUT / "template.html").read_text()
for k, v in subs.items():
    page = page.replace("{{" + k + "}}", v)
assert "{{" not in page, page[page.index("{{") : page.index("{{") + 40]
(OUT / "index.html").write_text(page)
print("wrote", OUT / "index.html", "| total API cost", f"${cost_total:.2f}")
