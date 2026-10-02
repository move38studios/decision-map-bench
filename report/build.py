"""Build report/index.html from results/metrics and results/maps.

Usage: uv run python -m report.build
"""

import collections
import html
import json
import shutil

from jevmap import geo, runner
from scripts.analysis import CLAUDE

ROOT = geo.ROOT
OUT = ROOT / "report"
IMG = OUT / "img"
MAPS = ROOT / "results" / "maps"
MET = ROOT / "results" / "metrics"

m2 = json.loads((MET / "2deg.json").read_text())
a2 = json.loads((MET / "2deg_analysis.json").read_text())
e2 = json.loads((MET / "2deg_explore.json").read_text())
m1 = json.loads((MET / "1deg.json").read_text())
p1 = json.loads((MET / "phase1.json").read_text())

IMAGES = [
    "2deg_land_truth", "2deg_land_jev", "2deg_land_jev_probability", "2deg_land_errors",
    "2deg_p_land_noul", "2deg_p_land_choice", "2deg_p_land_continent", "2deg_p_land_colour", "2deg_p_land_terrain",
    "2deg_physical_truth", "2deg_physical_terrain_jev", "2deg_physical_colour_jev",
    "2deg_continent_truth", "2deg_continent_jev",
    "2deg_political_truth", "2deg_political_jev_on_land", "2deg_political_jev", "2deg_political_confidence",
    "1deg_p_land_noul", "1deg_p_land_terrain", "1deg_physical_colour_jev",
]


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def fig(name: str, alt: str, caption: str = "") -> str:
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure><img src="img/{name}.png" alt="{esc(alt)}" width="945" height="476" loading="lazy">{cap}</figure>'


# ---------------------------------------------------------------- numbers
land = m2["runs"]["land"]
pol = m2["runs"]["political"]
phy_t = m2["runs"]["physical_terrain"]
phy_c = m2["runs"]["physical_colour"]
jev_raw = land["accuracy"]
jev_tuned = land["accuracy_tuned_threshold"]
total_cost = 0.0
for f in (ROOT / "results" / "raw").glob("*.usage.jsonl"):
    total_cost += sum((json.loads(l)["input_tokens"] or 0) for l in f.read_text().splitlines()) / 1e6 * runner.PRICE_PER_MTOK

# ---------------------------------------------------------------- Jev vs Claudes bars
rows = [(k, v / 100, False) for k, v in CLAUDE.items()]
rows += [("Jev 1.13, p ≥ 0.5", jev_raw, True), ("Jev 1.13, p ≥ 0.70", jev_tuned, True)]
rows.sort(key=lambda r: -r[1])
LO = 0.5
bars = "".join(
    f'<div class="bar{" jev" if j else ""}"><span class="bl">{esc(k)}</span>'
    f'<span class="bt"><span class="bf" style="width:{(v - LO) / (1 - LO) * 100:.2f}%"></span></span>'
    f'<span class="bv">{pct(v)}</span></div>'
    for k, v, j in rows
)
ticks = "".join(f'<span style="left:{(t - LO) / (1 - LO) * 100:.1f}%">{int(t * 100)}%</span>' for t in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0))

# ---------------------------------------------------------------- ways of asking
ways = [
    ("noul", "2deg_p_land_noul", "Yes/no (Noul)", "“The location at 35°S, 175°W is on land, not in an ocean, sea or lake.”", a2["p_land_noul_acc_0.5"]),
    ("choice", "2deg_p_land_choice", "Land or water (Choice)", "“Is the location at 35°S, 175°W on land or in water?” Options: land, water.", e2["land_choice_accuracy_0.5"]),
    ("continent", "2deg_p_land_continent", "Continent or ocean (Choice)", "“Which continent or ocean is the location at 35°S, 175°W in?” 7 continents and 5 oceans; P(land) is the sum over continents.", e2["continent_p_land_accuracy_0.5"]),
    ("colour", "2deg_p_land_colour", "Atlas colour (Choice)", "“On a classic physical atlas map coloured by elevation and sea depth, what colour is the location at 35°S, 175°W?” P(land) is the sum over the five land colours.", a2["p_land_colour_acc_0.5"]),
    ("terrain", "2deg_p_land_terrain", "Terrain (Choice)", "“What is the terrain or sea depth at the location at 35°S, 175°W?” P(land) is the sum over the five land bands.", a2["p_land_terrain_acc_0.5"]),
]
way_buttons = "".join(
    f'<button type="button" id="way-{k}" data-img="img/{img}.png" data-q="{esc(q)}" data-acc="{pct(acc)}" aria-pressed="{"true" if k == "noul" else "false"}">'
    f'<span>{esc(label)}</span><b>{pct(acc)}</b></button>'
    for k, img, label, q, acc in ways
)
ways_sorted = sorted(ways, key=lambda w: -w[4])

# ---------------------------------------------------------------- calibration svg
cal = land["calibration"]
W, H, PAD = 320, 320, 40


def sx(v: float) -> float:
    return PAD + v * (W - PAD - 12)


def sy(v: float) -> float:
    return H - PAD - v * (H - PAD - 12)


grid_lines = "".join(
    f'<line x1="{sx(t)}" y1="{sy(0)}" x2="{sx(t)}" y2="{sy(1)}" class="g"/><line x1="{sx(0)}" y1="{sy(t)}" x2="{sx(1)}" y2="{sy(t)}" class="g"/>'
    f'<text x="{sx(t)}" y="{sy(0) + 16}" class="tk" text-anchor="middle">{t:.1f}</text>'
    f'<text x="{sx(0) - 6}" y="{sy(t) + 4}" class="tk" text-anchor="end">{t:.1f}</text>'
    for t in (0, 0.2, 0.4, 0.6, 0.8, 1.0)
)
pts = " ".join(f"{sx(r['mean_p']):.1f},{sy(r['land_fraction']):.1f}" for r in cal)
dots = "".join(f'<circle cx="{sx(r["mean_p"]):.1f}" cy="{sy(r["land_fraction"]):.1f}" r="3.5" class="dot"><title>p ≈ {r["mean_p"]:.2f}: {pct(r["land_fraction"], 0)} land, {r["points"]} points</title></circle>' for r in cal)
cal_svg = f"""<svg viewBox="0 0 {W} {H}" role="img" aria-label="Calibration of Jev's probability of land on the 2 degree grid">
{grid_lines}
<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(1)}" y2="{sy(1)}" class="diag"/>
<polyline points="{pts}" class="line"/>{dots}
<text x="{(sx(0) + sx(1)) / 2}" y="{H - 4}" class="ax" text-anchor="middle">Jev's probability of land</text>
<text x="12" y="{(sy(0) + sy(1)) / 2}" class="ax" text-anchor="middle" transform="rotate(-90 12 {(sy(0) + sy(1)) / 2})">Share actually land</text>
</svg>"""
cal_rows = "".join(
    f"<tr><td>{r['bin']}</td><td>{r['points']:,}</td><td>{pct(r['land_fraction'], 0)}</td></tr>" for r in cal
)

# ---------------------------------------------------------------- political tables
pc = pol["per_country"]
big = pc[:12]
big_rows = "".join(
    f"<tr><td>{esc(r['country'])}</td><td>{r['points']:,}</td><td>{pct(r['accuracy'], 0)}</td><td>{esc(', '.join(r['confused_with']))}</td></tr>"
    for r in big
)
worst = sorted([r for r in pc if r["points"] >= 15], key=lambda r: r["accuracy"])[:8]
worst_rows = "".join(
    f"<tr><td>{esc(r['country'])}</td><td>{r['points']:,}</td><td>{pct(r['accuracy'], 0)}</td><td>{esc(', '.join(r['confused_with']))}</td></tr>"
    for r in worst
)
recs = runner.load("g2_political")
chosen = collections.Counter(r["choice"] for r in recs.values())
in_top = collections.Counter(c for r in recs.values() for c in r["probs"])
never = []
for name in ("Zambia", "Chad", "Togo", "Mali", "Laos"):
    never.append(f"<tr><td>{name}</td><td>{chosen[name]}</td><td>{in_top[name]:,}</td></tr>")
never_rows = "".join(never)
gate_rows = "".join(
    f"<tr><td>≥ {g['threshold']:.1f}</td><td>{pct(g['coverage'], 0)}</td><td>{pct(g['accuracy'])}</td></tr>"
    for g in a2["political_confidence_gate"]
)
sea_claims = collections.Counter()
t2 = geo.truth(geo.Grid(2))
for i, lat in enumerate(geo.Grid(2).lats):
    for j, lon in enumerate(geo.Grid(2).lons):
        if t2["country"][i, j] == geo.OCEAN:
            r = recs.get(geo.point_id(lat, lon))
            if r and r["choice"] != geo.OCEAN:
                sea_claims[r["choice"]] += 1
claims = ", ".join(f"{esc(c)} {n:,}" for c, n in sea_claims.most_common(6))

# ---------------------------------------------------------------- continent table
cont_rows = "".join(
    f"<tr><td>{c}</td><td>{pct(v)}</td></tr>"
    for c, v in sorted(e2["continent_accuracy_by_continent"].items(), key=lambda kv: -kv[1])
)

# ---------------------------------------------------------------- phase 1 table
def p1get(exp, style, layout, key):
    for r in p1:
        if r["experiment"] == exp and r["style"] == style and r["layout"] == layout and r["model"] == "jev-latest":
            return r[key]


fmt = {"decimal": "latitude -35, longitude -175", "hemi": "35°S, 175°W", "words": "35 degrees south, 175 degrees west"}
p1_rows = "".join(
    f"<tr><td><code>{fmt[s]}</code></td>"
    f"<td>{pct(p1get('land', s, 'state', 'accuracy'))} / {pct(p1get('land', s, 'state', 'best_threshold_accuracy'))}</td>"
    f"<td>{pct(p1get('land', s, 'question', 'accuracy'))} / {pct(p1get('land', s, 'question', 'best_threshold_accuracy'))}</td>"
    f"<td>{pct(p1get('political', s, 'question', 'accuracy_land')) if s != 'words' else '–'}</td></tr>"
    for s in ("decimal", "hemi", "words")
)

# ---------------------------------------------------------------- grid resolution table
res_rows = "".join(
    f"<tr><td>{label}</td><td>{pct(v2)}</td><td>{pct(v1)}</td></tr>"
    for label, v2, v1 in [
        ("Yes/no, p ≥ 0.5", jev_raw, m1["runs"]["land"]["accuracy"]),
        ("Yes/no, best threshold", land["best_threshold_accuracy"], m1["runs"]["land"]["best_threshold_accuracy"]),
        ("Land or water (Choice)", e2["land_choice_accuracy_0.5"], m1["runs"]["land_choice"]["p_land_accuracy_0.5"]),
        ("Terrain (Choice), P(land)", a2["p_land_terrain_acc_0.5"], m1["runs"]["terrain"]["p_land_accuracy_0.5"]),
    ]
)

# ---------------------------------------------------------------- copy images
IMG.mkdir(parents=True, exist_ok=True)
for n in IMAGES:
    shutil.copy(MAPS / f"{n}.png", IMG / f"{n}.png")

page = (OUT / "template.html").read_text()
subs = {
    "JEV_RAW": pct(jev_raw),
    "JEV_TUNED": pct(jev_tuned),
    "POL_LAND": pct(pol["accuracy_land"]),
    "POL_TOP3": pct(pol["top3_land"]),
    "POL_OCEAN": pct(pol["ocean_recall"], 0),
    "CONT_LAND": pct(e2["continent_accuracy_on_land"]),
    "TERRAIN_PLAND": pct(a2["p_land_terrain_acc_0.5"]),
    "CHOICE_PLAND": pct(e2["land_choice_accuracy_0.5"]),
    "TOTAL_COST": f"${total_cost:.2f}",
    "COST_2DEG": f"${m2['total_cost_usd']:.2f}",
    "COST_LAND_2DEG": f"{m2['runs']['land']['usage']['cost_usd'] * 100:.1f}¢",
    "LAND_RECALL": pct(land["land_recall"], 0),
    "WATER_RECALL": pct(land["water_recall"], 0),
    "PHY_T_ACC": pct(phy_t["accuracy"]),
    "PHY_T_W1": pct(phy_t["within_one"]),
    "PHY_T_LAND": pct(phy_t["land_only_accuracy"]),
    "PHY_C_ACC": pct(phy_c["accuracy"]),
    "PHY_C_W1": pct(phy_c["within_one"]),
    "PHY_C_LAND": pct(phy_c["land_only_accuracy"]),
    "BARS": bars,
    "TICKS": ticks,
    "WAY_BUTTONS": way_buttons,
    "WAY_FIRST_IMG": "img/2deg_p_land_noul.png",
    "WAY_FIRST_Q": esc(ways[0][3]),
    "CAL_SVG": cal_svg,
    "CAL_ROWS": cal_rows,
    "BIG_ROWS": big_rows,
    "WORST_ROWS": worst_rows,
    "NEVER_ROWS": never_rows,
    "GATE_ROWS": gate_rows,
    "SEA_CLAIMS": claims,
    "CONT_ROWS": cont_rows,
    "P1_ROWS": p1_rows,
    "RES_ROWS": res_rows,
    "FIG_LAND_PROB": fig("2deg_land_jev_probability", "Jev's probability of land at every 2 degree point, white is land"),
    "FIG_LAND_ERR": fig("2deg_land_errors", "Error map: red is water Jev called land, blue is land Jev called water"),
    "FIG_PHY_TRUTH": fig("2deg_physical_truth", "True physical map from ETOPO1", "Truth (ETOPO1 + land mask)"),
    "FIG_PHY_T": fig("2deg_physical_terrain_jev", "Jev physical map, terrain-named options", f"Terrain names: {pct(phy_t['accuracy'])} exact"),
    "FIG_PHY_C": fig("2deg_physical_colour_jev", "Jev physical map, atlas-colour options", f"Atlas colours: {pct(phy_c['accuracy'])} exact"),
    "FIG_CONT_T": fig("2deg_continent_truth", "True continents", "Truth (Natural Earth)"),
    "FIG_CONT_J": fig("2deg_continent_jev", "Jev's answer to which continent or ocean each point is in", "Jev"),
    "FIG_POL_T": fig("2deg_political_truth", "True political map", "Truth (Natural Earth 1:50m)"),
    "FIG_POL_J": fig("2deg_political_jev_on_land", "Jev's country answers drawn on true land points only", "Jev, true land points only"),
    "FIG_POL_ALL": fig("2deg_political_jev", "Jev's country answers at every point including the sea", "Jev, every point"),
    "FIG_POL_CONF": fig("2deg_political_confidence", "Confidence of Jev's country answers, bright is high", "Confidence of the country answer (bright = high)"),
    "FIG_1_NOUL": fig("1deg_p_land_noul", "Yes/no probability of land at 1 degree", "Yes/no, P(land), 1°"),
    "FIG_1_TERR": fig("1deg_p_land_terrain", "Terrain-derived probability of land at 1 degree", "Terrain, P(land), 1°"),
}
for k, v in subs.items():
    page = page.replace("{{" + k + "}}", v)
assert "{{" not in page, page[page.index("{{") : page.index("{{") + 40]
(OUT / "index.html").write_text(page)
print("wrote", OUT / "index.html", f"total cost ${total_cost:.2f}")
