"""Cross-model scoring: P(land) from every question type, accuracy, AUC, calibration."""

import numpy as np

from jevmap import geo, prompts, runner

MODELS = ["jev", "clef", "clef-flash", "laya-typed"]
LABEL = {"jev": "Jev 1.13", "clef": "Clef", "clef-flash": "Clef-flash", "laya-typed": "Laya typed-decisions"}

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

LAND_SOURCES = ["orig_choice", "orig_noul", "land", "land_choice", "continent", "physical_terrain", "physical_colour"]
SOURCE_LABEL = {
    "orig_choice": "“Land or Water?” (Choice)",
    "orig_noul": "“…is over land” (yes/no)",
    "land": "“…is on land, not in an ocean, sea or lake” (yes/no)",
    "land_choice": "“On land or in water?” (Choice)",
    "continent": "Which continent or ocean?",
    "physical_terrain": "Terrain / sea depth",
    "physical_colour": "Colour on a physical atlas",
}


def run_name(model: str, exp: str, layout: str = "question", step: float = 2) -> str:
    if model == "jev" and step == 2 and layout == "question":
        return JEV_NAMES[exp]
    suffix = "_state" if layout == "state" else ""
    return f"{model}_g{step:g}_{exp}{suffix}"


def _land_labels(exp: str) -> set[str]:
    if exp.startswith("physical_"):
        v = exp.removeprefix("physical_")
        return {lab for lab, b in prompts.physical_label_to_band(v).items() if b not in geo.WATER_BANDS}
    if exp == "continent":
        return set(geo.CONTINENTS)
    if exp == "orig_choice":
        return {"Land"}
    if exp == "land_choice":
        return {"land"}
    return set()


def p_land(name: str, exp: str, grid: geo.Grid) -> np.ndarray:
    """P(land) per grid point read from a run's answers (Noul p, or summed land options of a Choice)."""
    recs = runner.load(name)
    labels = _land_labels(exp)
    out = np.full(grid.shape, np.nan)
    for i, lat in enumerate(grid.lats):
        for j, lon in enumerate(grid.lons):
            r = recs.get(geo.point_id(lat, lon))
            if r is None:
                continue
            out[i, j] = r["p"] if "p" in r else sum(v for k, v in r["probs"].items() if k in labels)
    return out


def weighted_auc(score: np.ndarray, label: np.ndarray, w: np.ndarray) -> float:
    """Area-weighted ROC AUC (probability a random land point scores above a random water point)."""
    order = np.argsort(score, kind="mergesort")
    s, y, w = score[order], label[order].astype(bool), w[order]
    # Group ties.
    uniq, idx = np.unique(s, return_index=True)
    bounds = list(idx) + [len(s)]
    w_neg_below = 0.0
    total = 0.0
    for a, b in zip(bounds[:-1], bounds[1:]):
        pos = w[a:b][y[a:b]].sum()
        neg = w[a:b][~y[a:b]].sum()
        total += pos * (w_neg_below + 0.5 * neg)
        w_neg_below += neg
    return float(total / (w[y].sum() * w[~y].sum()))


def land_metrics(p: np.ndarray, grid: geo.Grid) -> dict:
    land = geo.truth(grid)["land"]
    have = ~np.isnan(p)
    w = grid.weights[have]
    pv, yv = p[have], land[have]
    acc = lambda t: float((((pv >= t) == yv) * w).sum() / w.sum())
    thr = np.arange(0.02, 0.99, 0.01)
    accs = [acc(t) for t in thr]
    k = int(np.argmax(accs))
    bins = np.clip((pv * 10).astype(int), 0, 9)
    ece = 0.0
    curve = []
    for b in range(10):
        m = bins == b
        if m.any():
            mp = float((pv[m] * w[m]).sum() / w[m].sum())
            fr = float((yv[m] * w[m]).sum() / w[m].sum())
            ece += w[m].sum() / w.sum() * abs(mp - fr)
            curve.append({"bin": b, "points": int(m.sum()), "mean_p": mp, "land_fraction": fr})
    return {
        "accuracy": acc(0.5),
        "best_accuracy": accs[k],
        "best_threshold": round(float(thr[k]), 2),
        "auc": weighted_auc(pv, yv, w),
        "brier": float((((pv - yv) ** 2) * w).sum() / w.sum()),
        "ece": float(ece),
        "mean_p_land": float(pv[yv].mean()),
        "mean_p_water": float(pv[~yv].mean()),
        "calibration": curve,
        "points": int(have.sum()),
    }


def water_baseline(grid: geo.Grid) -> float:
    land = geo.truth(grid)["land"]
    w = grid.weights
    return float((w * ~land).sum() / w.sum())


# Each model's better layout for "Land or Water?" at 2° (by AUC): see results/metrics/bench_2deg.json["state_layout"].
BEST_LAYOUT = {"jev": "question", "clef": "state", "clef-flash": "state", "laya-typed": "question"}


def best_land_run(model: str) -> str:
    if BEST_LAYOUT[model] == "state":
        return "g2_orig_choice_state" if model == "jev" else f"{model}_g2_orig_choice_state"
    return run_name(model, "orig_choice")


def section_layout(model: str, step: float = 2) -> str:
    """Layout used for the continent / physical / political sections: the model's better layout,
    but only once every state-layout run is complete; otherwise the coordinate-in-question runs."""
    if BEST_LAYOUT.get(model) != "state":
        return "question"
    n = round(180 / step) * round(360 / step)
    for exp in ("continent", "physical_terrain", "physical_colour", "political"):
        name = run_name(model, exp, "state", step)
        if not runner.has(name) or len(runner.load(name)) < n:
            return "question"
    return "state"
