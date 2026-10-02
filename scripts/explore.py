"""Phase 5 (exploratory, after the headline was frozen): other ways to ask land / water.

- continent:   Choice "which continent or ocean is this location in?" (7 continents + 5 oceans)
- land_choice: Choice "land" vs "water" (compare with the Noul)

Usage: uv run python -m scripts.explore 2
"""

import json
import sys

import numpy as np

from jevmap import geo, prompts, render, runner
from jevmap.runner import RunSpec, run_sync, usage
from scripts.analysis import grey, prob_grid, wacc
from scripts.main_runs import FROZEN

METRICS = geo.ROOT / "results" / "metrics"
CONTINENT_COLOURS = {
    "Africa": "#e3b25c", "Antarctica": "#f4f4f4", "Asia": "#d9786b", "Europe": "#8c7bc9",
    "North America": "#7cbf6a", "Oceania": "#e58fc0", "South America": "#4fa39a",
}


def main(step: float) -> None:
    grid = geo.Grid(step)
    tag = f"{step:g}deg"
    pts = grid.points()
    t = geo.truth(grid)
    land = t["land"]
    out: dict = {}

    for exp in ("continent", "land_choice"):
        run_sync(RunSpec(f"g{step:g}_{exp}", exp, batch=100, **FROZEN), pts)
        out[f"{exp}_usage"] = usage(f"g{step:g}_{exp}")

    # Continent / ocean
    name = f"g{step:g}_continent"
    p_land = prob_grid(name, grid, lambda r: sum(p for k, p in r["probs"].items() if k in geo.CONTINENTS))
    recs = runner.load(name)
    choice = np.full(grid.shape, "", dtype=object)
    for i, lat in enumerate(grid.lats):
        for j, lon in enumerate(grid.lons):
            r = recs.get(geo.point_id(lat, lon))
            if r:
                choice[i, j] = r["choice"]
    have = choice != ""
    pred_land = np.isin(choice, geo.CONTINENTS)
    out["continent_land_water_accuracy"] = wacc(pred_land == land, grid, have)
    out["continent_p_land_accuracy_0.5"] = wacc((p_land >= 0.5) == land, grid, have)
    true_cont = np.array(
        [[geo.continent_of(c, lon) for c, lon in zip(row, grid.lons)] for row in t["country"]], dtype=object
    )
    scored = have & (true_cont != "")
    out["continent_accuracy_on_land"] = wacc(choice == true_cont, grid, scored)
    out["continent_accuracy_by_continent"] = {
        c: wacc(choice == true_cont, grid, scored & (true_cont == c)) for c in geo.CONTINENTS
    }
    img = np.zeros(grid.shape + (3,))
    import matplotlib.colors as mc
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            c = choice[i, j]
            img[i, j] = mc.to_rgb(CONTINENT_COLOURS.get(c, render.OCEAN_COLOUR if c else render.MISSING))
    render.save(img, f"{tag}_continent_jev")
    timg = np.zeros(grid.shape + (3,))
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            c = true_cont[i, j]
            timg[i, j] = mc.to_rgb(CONTINENT_COLOURS[c]) if c else (mc.to_rgb("#cccccc") if land[i, j] else mc.to_rgb(render.OCEAN_COLOUR))
    render.save(timg, f"{tag}_continent_truth")
    render.save(grey(p_land), f"{tag}_p_land_continent")
    render.save(render.land_bw(pred_land), f"{tag}_land_from_continent")

    # Land vs water as a two-option Choice
    name = f"g{step:g}_land_choice"
    p_lc = prob_grid(name, grid, lambda r: r["probs"].get("land", 0.0))
    out["land_choice_accuracy_0.5"] = wacc((p_lc >= 0.5) == land, grid, ~np.isnan(p_lc))
    render.save(grey(p_lc), f"{tag}_p_land_choice")
    render.save(render.land_bw(p_lc >= 0.5), f"{tag}_land_choice_jev")

    (METRICS / f"{tag}_explore.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(float(sys.argv[1]))
