"""Phases 2-4: run all experiments on one grid with the prompt frozen after phase 1, then score and draw.

Usage: uv run python -m scripts.main_runs 5        (5 degree grid)
"""

import json
import sys

import numpy as np

from jevmap import geo, render, score
from jevmap.runner import RunSpec, run_sync, usage

# Frozen after phase 1 (results/metrics/phase1.json).
FROZEN = {"coord_style": "hemi", "layout": "question", "model": "jev-latest"}
LAND_THRESHOLD_TUNED = 0.70  # best threshold for hemi/question/latest on the 10 degree grid
BATCH = {"land": 100, "physical_terrain": 100, "physical_colour": 100, "political": 25}
EXPERIMENTS = list(BATCH)
METRICS = geo.ROOT / "results" / "metrics"


def run_name(exp: str, step: float) -> str:
    return f"g{step:g}_{exp}"


def main(step: float) -> None:
    grid = geo.Grid(step)
    pts = grid.points()
    t = geo.truth(grid)
    tag = f"{step:g}deg"
    out: dict = {"step": step, "points": len(pts), "frozen": FROZEN, "runs": {}}

    for exp in EXPERIMENTS:
        spec = RunSpec(run_name(exp, step), exp, batch=BATCH[exp], **FROZEN)
        run_sync(spec, pts)
        s = score.score(spec.name, grid, exp)
        s["usage"] = usage(spec.name)
        out["runs"][exp] = s

    # Land / water
    name = run_name("land", step)
    g = score.to_grid(name, grid, "land")
    w = grid.weights
    tuned = np.nan_to_num(g["p"]) >= LAND_THRESHOLD_TUNED
    out["runs"]["land"]["accuracy_tuned_threshold"] = float((((tuned == t["land"]) * w)[g["have"]]).sum() / w[g["have"]].sum())
    out["runs"]["land"]["tuned_threshold"] = LAND_THRESHOLD_TUNED
    out["runs"]["land"]["calibration"] = score.calibration(name, grid)
    render.save(render.land_bw(t["land"]), f"{tag}_land_truth")
    render.save(render.land_bw(g["pred"], g["have"]), f"{tag}_land_jev")
    render.save(render.land_bw(tuned, g["have"]), f"{tag}_land_jev_tuned")
    render.save(render.land_prob(g["p"]), f"{tag}_land_jev_probability")
    render.save(render.land_errors(g["pred"], t["land"], g["have"]), f"{tag}_land_errors")

    # Physical
    render.save(render.bands(t["band"]), f"{tag}_physical_truth")
    for exp in ("physical_terrain", "physical_colour"):
        name = run_name(exp, step)
        g = score.to_grid(name, grid, exp)
        render.save(render.bands(g["pred"]), f"{tag}_{exp}_jev")
        out["runs"][exp]["confusion"] = score.confusion(name, grid, exp).round(3).tolist()

    # Political
    name = run_name("political", step)
    g = score.to_grid(name, grid, "political")
    render.save(render.political(t["country"]), f"{tag}_political_truth")
    render.save(render.political(g["pred"]), f"{tag}_political_jev")
    render.save(render.political_errors(g["pred"], t["country"], g["have"]), f"{tag}_political_errors")
    out["runs"]["political"]["per_country"] = score.per_country(name, grid)

    out["total_cost_usd"] = sum(r["usage"]["cost_usd"] for r in out["runs"].values())
    METRICS.mkdir(parents=True, exist_ok=True)
    (METRICS / f"{tag}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print(f"\n=== {tag}: {len(pts)} points, cost ${out['total_cost_usd']:.3f}")
    for exp, s in out["runs"].items():
        keys = [k for k, v in s.items() if isinstance(v, float) and k not in ("step",)]
        print(exp, {k: round(s[k], 3) for k in keys})


if __name__ == "__main__":
    main(float(sys.argv[1]))
