"""Phase 4: 1 degree grid (64,800 points) for the cheap experiments; political skipped (~$5, ~45 min)."""

import json

import numpy as np

from jevmap import geo, render, score
from jevmap.runner import RunSpec, run_sync, usage
from scripts.analysis import grey, prob_grid, wacc
from scripts.main_runs import FROZEN
from jevmap import prompts

STEP = 1.0
GRID = geo.Grid(STEP)
TAG = "1deg"
EXPS = ["land", "land_choice", "physical_terrain", "physical_colour", "continent"]

if __name__ == "__main__":
    pts = GRID.points()
    t = geo.truth(GRID)
    land = t["land"]
    out = {"step": STEP, "points": len(pts), "runs": {}}
    for exp in EXPS:
        name = f"g1_{exp}"
        run_sync(RunSpec(name, exp, batch=100, **FROZEN), pts, tps=90_000)
        out["runs"][exp] = {"usage": usage(name)}
    for exp in ("land", "physical_terrain", "physical_colour"):
        s = score.score(f"g1_{exp}", GRID, exp)
        out["runs"][exp].update(s)
    p = {
        "noul": score.to_grid("g1_land", GRID, "land")["p"],
        "land_choice": prob_grid("g1_land_choice", GRID, lambda r: r["probs"].get("land", 0.0)),
        "continent": prob_grid("g1_continent", GRID, lambda r: sum(v for k, v in r["probs"].items() if k in geo.CONTINENTS)),
    }
    for v in ("terrain", "colour"):
        labels = {lab for lab, b in prompts.physical_label_to_band(v).items() if b not in geo.WATER_BANDS}
        p[v] = prob_grid(f"g1_physical_{v}", GRID, lambda r: sum(x for k, x in r["probs"].items() if k in labels))
    for k, a in p.items():
        out["runs"].setdefault(k, {})["p_land_accuracy_0.5"] = wacc((a >= 0.5) == land, GRID, ~np.isnan(a))
        render.save(grey(a), f"{TAG}_p_land_{k}")
        render.save(render.land_bw(a >= 0.5), f"{TAG}_land_from_{k}")
    render.save(render.land_bw(land), f"{TAG}_land_truth")
    render.save(render.bands(t["band"]), f"{TAG}_physical_truth")
    for v in ("terrain", "colour"):
        render.save(render.bands(score.to_grid(f"g1_physical_{v}", GRID, f"physical_{v}")["pred"]), f"{TAG}_physical_{v}_jev")
    out["total_cost_usd"] = sum(r.get("usage", {}).get("cost_usd", 0) for r in out["runs"].values())
    (geo.ROOT / "results" / "metrics" / f"{TAG}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if isinstance(vv, float)} for k, v in out["runs"].items()}, indent=2))
    print("total cost", out["total_cost_usd"])
