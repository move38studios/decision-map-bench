"""The original "blind model" wording, asked of Jev on the 2 degree grid.

Prompt from outsidetext.substack.com/p/how-does-a-blind-model-see-the-earth:
"If this location is over land, say 'Land'. If this location is over water, say 'Water'. ... x° S, y° W"
"""

import json

import numpy as np

from jevmap import geo, render
from jevmap.runner import RunSpec, run_sync, usage
from scripts.analysis import grey, prob_grid, wacc

GRID = geo.Grid(2)
ARMS = [
    RunSpec("g2_orig_choice_state", "orig_choice", layout="state"),
    RunSpec("g2_orig_choice_question", "orig_choice", layout="question", batch=100),
    RunSpec("g2_orig_noul_state", "orig_noul", layout="state"),
    RunSpec("g2_orig_noul_question", "orig_noul", layout="question", batch=100),
]

if __name__ == "__main__":
    land = geo.truth(GRID)["land"]
    out = {}
    for spec in ARMS:
        run_sync(spec, GRID.points())
        key = "p" if spec.experiment == "orig_noul" else None
        p = prob_grid(spec.name, GRID, (lambda r: r["p"]) if key else (lambda r: r["probs"].get("Land", 0.0)))
        have = ~np.isnan(p)
        best = max(((t, wacc((p >= t) == land, GRID, have)) for t in np.arange(0.05, 0.96, 0.01)), key=lambda x: x[1])
        out[spec.name] = {
            "accuracy_0.5": wacc((p >= 0.5) == land, GRID, have),
            "accuracy_0.7": wacc((p >= 0.7) == land, GRID, have),
            "best_threshold": round(float(best[0]), 2),
            "best_threshold_accuracy": best[1],
            "antarctica_mean_p": float(np.nanmean(p[GRID.lats <= -71])),
            "usage": usage(spec.name),
        }
        render.save(grey(p), f"2deg_p_land_{spec.name.removeprefix('g2_')}")
        render.save(render.land_bw(p >= 0.5), f"2deg_land_{spec.name.removeprefix('g2_')}")
    (geo.ROOT / "results" / "metrics" / "2deg_original_prompt.json").write_text(json.dumps(out, indent=2))
    for k, v in out.items():
        print(f"{k:28} acc@0.5={v['accuracy_0.5']:.1%} acc@0.7={v['accuracy_0.7']:.1%} best={v['best_threshold_accuracy']:.1%}@{v['best_threshold']} antarctica_p={v['antarctica_mean_p']:.2f} cost=${v['usage']['cost_usd']:.3f}")
