"""Run the benchmark suite (2 degree grid, coordinate in the question) for one backend.

Usage: uv run python -m scripts.bench clef [experiments...]
"""

import sys

from jevmap import geo
from jevmap.runner import RunSpec, run_sync

STEP = 2.0
SUITE = ["orig_choice", "orig_noul", "land", "land_choice", "continent", "physical_terrain", "physical_colour", "political"]
BATCH = {"political": 25}

# Jev runs were made earlier under these names.
JEV_NAMES = {
    "orig_choice": "g2_orig_choice_question",
    "orig_noul": "g2_orig_noul_question",
    "land": "g2_land",
    "land_choice": "g2_land_choice",
    "continent": "g2_continent",
    "physical_terrain": "g2_physical_terrain",
    "physical_colour": "g2_physical_colour",
    "political": "g2_political",
}


def run_name(backend: str, exp: str) -> str:
    return JEV_NAMES[exp] if backend == "jev" else f"{backend}_g2_{exp}"


if __name__ == "__main__":
    backend = sys.argv[1]
    exps = sys.argv[2:] or SUITE
    pts = geo.Grid(STEP).points()
    for exp in exps:
        spec = RunSpec(run_name(backend, exp), exp, batch=BATCH.get(exp, 64), backend=backend)
        run_sync(spec, pts, concurrency=16, rps=20, tps=10**9)
