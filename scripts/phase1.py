"""Phase 1: prompt tuning on the 10 degree grid (648 points)."""

import json
from itertools import product

from jevmap import geo, render, score
from jevmap.runner import RunSpec, run_sync, usage

GRID = geo.Grid(10)
PTS = GRID.points()
METRICS = geo.ROOT / "results" / "metrics"
MODELS = {"latest": "jev-latest", "preview": "jev-preview"}
BATCH = {"land": 100, "physical_terrain": 100, "physical_colour": 100, "political": 25}


def arms():
    for style, layout, m in product(["decimal", "hemi", "words"], ["state", "question"], MODELS):
        yield RunSpec(f"p1_land_{style}_{layout}_{m}", "land", style, layout, MODELS[m], BATCH["land"])
    for exp in ["physical_terrain", "physical_colour", "political"]:
        for style, layout, m in product(["decimal", "hemi"], ["state", "question"], MODELS):
            yield RunSpec(f"p1_{exp}_{style}_{layout}_{m}", exp, style, layout, MODELS[m], BATCH[exp])


if __name__ == "__main__":
    rows = []
    for spec in arms():
        run_sync(spec, PTS)
        s = score.score(spec.name, GRID, spec.experiment)
        s.update(style=spec.coord_style, layout=spec.layout, model=spec.model, **{"usage": usage(spec.name)})
        rows.append(s)
    METRICS.mkdir(parents=True, exist_ok=True)
    (METRICS / "phase1.json").write_text(json.dumps(rows, indent=2))

    # Land panel: every arm plus truth.
    t = geo.truth(GRID)
    imgs = [(render.land_bw(t["land"]), "Truth (1-km land mask)")]
    for r in rows:
        if r["experiment"] == "land":
            g = score.to_grid(r["run"], GRID, "land")
            imgs.append((render.land_bw(g["pred"], g["have"]), f"{r['run'].removeprefix('p1_land_')}  {r['accuracy']:.1%}"))
    render.panel(imgs, geo.ROOT / "results" / "maps" / "phase1_land_arms.png", cols=4,
                 suptitle="Phase 1, land/water, 10° grid")

    total = sum(r["usage"]["cost_usd"] for r in rows)
    print(f"\nTotal phase 1 cost: ${total:.3f}")
