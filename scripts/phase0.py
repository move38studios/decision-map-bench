"""Phase 0: hand-picked sanity points; measure tokens per question."""

import json

from jevmap import geo
from jevmap.runner import RunSpec, run_sync, usage

POINTS = {
    "Mid-Pacific": (0.0, -150.0),
    "Mid-Atlantic": (30.0, -40.0),
    "Southern Ocean": (-60.0, 90.0),
    "Arctic Ocean (N Pole)": (89.0, 0.0),
    "Sahara": (23.0, 13.0),
    "Amazon": (-4.0, -62.0),
    "Siberia": (62.0, 100.0),
    "Central Australia": (-25.0, 133.0),
    "Antarctic plateau": (-80.0, 60.0),
    "Greenland ice": (72.0, -40.0),
    "Tibetan plateau": (33.0, 88.0),
    "Kansas": (38.5, -98.0),
    "Mediterranean": (35.0, 18.0),
    "Black Sea": (43.0, 34.0),
    "Caspian Sea": (42.0, 50.5),
    "Hudson Bay": (60.0, -85.0),
    "Lake Victoria": (-1.0, 33.0),
    "Madagascar": (-20.0, 46.5),
    "Indonesia (Borneo)": (0.5, 114.0),
    "New Zealand (S Island)": (-44.0, 170.5),
    "Andes (Bolivia)": (-19.0, -67.0),
    "Gulf of Mexico": (25.0, -90.0),
}

pts = list(POINTS.values())
specs = [
    RunSpec("p0_land_state_hemi", "land", layout="state"),
    RunSpec("p0_land_q1_hemi", "land", layout="question", batch=1),
    RunSpec("p0_land_q22_hemi", "land", layout="question", batch=22),
    RunSpec("p0_physical_terrain", "physical_terrain", layout="state"),
    RunSpec("p0_physical_colour", "physical_colour", layout="state"),
    RunSpec("p0_political_state", "political", layout="state"),
    RunSpec("p0_political_q22", "political", layout="question", batch=22),
]
for s in specs:
    run_sync(s, pts)

from jevmap.runner import load

truth_country = geo.country_of(pts)
print()
header = f"{'point':24} {'land':>5} {'band':>14} {'country':>16} | " + " | ".join(s.name.removeprefix("p0_") for s in specs)
print(header)
res = {s.name: load(s.name) for s in specs}
for (name, (lat, lon)), country in zip(POINTS.items(), truth_country):
    pid = geo.point_id(lat, lon)
    cells = []
    for s in specs:
        r = res[s.name].get(pid, {})
        cells.append(f"{r['p']:.2f}" if "p" in r else f"{r.get('choice')} ({r.get('confidence', 0):.2f})")
    print(f"{name:24} {str(geo.is_land(lat, lon)):>5} {geo.band(lat, lon):>14} {country:>16} | " + " | ".join(cells))

print()
for s in specs:
    u = usage(s.name)
    print(f"{s.name:24} requests={u['requests']:3} tokens={u['input_tokens']:7} per point={u['input_tokens']/len(pts):7.1f}  cost=${u['cost_usd']:.4f}")
