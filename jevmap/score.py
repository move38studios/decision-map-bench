"""Turn cached answers into grid arrays and area-weighted scores."""

import numpy as np

from jevmap import geo, prompts, runner


def to_grid(name: str, grid: geo.Grid, experiment: str) -> dict[str, np.ndarray]:
    """Arrays shaped like the grid: 'pred' (+ 'p' for land, 'conf' for choices); missing = NaN / ''."""
    recs = runner.load(name)
    shape = grid.shape
    out: dict[str, np.ndarray] = {}
    if experiment == "land":
        p = np.full(shape, np.nan)
        for i, lat in enumerate(grid.lats):
            for j, lon in enumerate(grid.lons):
                r = recs.get(geo.point_id(lat, lon))
                if r:
                    p[i, j] = r["p"]
        out["p"] = p
        out["pred"] = p >= 0.5
        out["have"] = ~np.isnan(p)
        return out
    pred = np.full(shape, "", dtype=object)
    conf = np.full(shape, np.nan)
    top3 = np.full(shape, None, dtype=object)
    to_band = (
        prompts.physical_label_to_band(experiment.removeprefix("physical_"))
        if experiment.startswith("physical_")
        else None
    )
    for i, lat in enumerate(grid.lats):
        for j, lon in enumerate(grid.lons):
            r = recs.get(geo.point_id(lat, lon))
            if not r:
                continue
            labels = list(r["probs"])[:3]
            if to_band:
                pred[i, j] = to_band[r["choice"]]
                top3[i, j] = [to_band[l] for l in labels]
            else:
                pred[i, j] = r["choice"]
                top3[i, j] = labels
            conf[i, j] = r["confidence"]
    out["pred"] = pred
    out["conf"] = conf
    out["top3"] = top3
    out["have"] = pred != ""
    return out


def _wacc(correct: np.ndarray, w: np.ndarray, mask: np.ndarray) -> float:
    m = mask.astype(bool)
    return float((correct[m] * w[m]).sum() / w[m].sum()) if m.any() else float("nan")


def score(name: str, grid: geo.Grid, experiment: str) -> dict:
    t = geo.truth(grid)
    g = to_grid(name, grid, experiment)
    w = grid.weights
    have = g["have"]
    out = {"run": name, "experiment": experiment, "step": grid.step, "points": int(have.sum())}
    if experiment == "land":
        land = t["land"]
        p = np.nan_to_num(g["p"])
        out["accuracy"] = _wacc(g["pred"] == land, w, have)
        out["land_recall"] = _wacc(g["pred"] == land, w, have & land)
        out["water_recall"] = _wacc(g["pred"] == land, w, have & ~land)
        out["brier"] = float(((p - land) ** 2 * w)[have].sum() / w[have].sum())
        # Best single threshold, as a diagnostic of ranking quality (not the headline number).
        best = max(
            ((thr, _wacc((p >= thr) == land, w, have)) for thr in np.arange(0.05, 0.96, 0.01)),
            key=lambda x: x[1],
        )
        out["best_threshold"], out["best_threshold_accuracy"] = round(float(best[0]), 2), best[1]
        out["mean_p_land"] = float(p[have & land].mean())
        out["mean_p_water"] = float(p[have & ~land].mean())
        return out
    pred = g["pred"]
    top3 = g["top3"]
    in_top3 = np.array(
        [[(tl in t3) if t3 else False for tl, t3 in zip(trow, prow)] for trow, prow in zip(t[_key(experiment)], top3)]
    )
    if experiment.startswith("physical_"):
        truth = t["band"]
        idx = {b: k for k, b in enumerate(geo.BANDS)}
        ti = np.vectorize(idx.get)(truth)
        pi = np.vectorize(lambda b: idx.get(b, -99))(pred)
        is_land_t = ~np.isin(truth, list(geo.WATER_BANDS))
        is_land_p = ~np.isin(pred, list(geo.WATER_BANDS))
        out["accuracy"] = _wacc(pred == truth, w, have)
        out["within_one"] = _wacc(np.abs(ti - pi) <= 1, w, have)
        out["land_only_accuracy"] = _wacc(pred == truth, w, have & is_land_t)
        out["water_only_accuracy"] = _wacc(pred == truth, w, have & ~is_land_t)
        out["land_water_accuracy"] = _wacc(is_land_p == is_land_t, w, have)
        out["top3"] = _wacc(in_top3, w, have)
        return out
    truth = t["country"]
    on_land = truth != geo.OCEAN
    out["accuracy_all"] = _wacc(pred == truth, w, have)
    out["accuracy_land"] = _wacc(pred == truth, w, have & on_land)
    out["top3_land"] = _wacc(in_top3, w, have & on_land)
    out["ocean_recall"] = _wacc(pred == truth, w, have & ~on_land)
    out["land_water_accuracy"] = _wacc((pred != geo.OCEAN) == on_land, w, have)
    return out


def _key(experiment: str) -> str:
    return "band" if experiment.startswith("physical_") else "country"


def per_country(name: str, grid: geo.Grid) -> list[dict]:
    """Per-country accuracy (area-weighted) for a political run, largest countries first."""
    t = geo.truth(grid)["country"]
    g = to_grid(name, grid, "political")
    w = grid.weights
    rows = []
    for c in np.unique(t):
        if c == geo.OCEAN:
            continue
        m = (t == c) & g["have"]
        if not m.any():
            continue
        wrong = g["pred"][m & (g["pred"] != t)]
        vals, counts = np.unique(wrong.astype(str), return_counts=True) if wrong.size else ([], [])
        confused = vals[np.argsort(-counts)][:3].tolist() if len(vals) else []
        rows.append(
            {
                "country": c,
                "points": int(m.sum()),
                "area_weight": float(w[m].sum()),
                "accuracy": _wacc(g["pred"] == t, w, m),
                "confused_with": confused,
            }
        )
    return sorted(rows, key=lambda r: -r["area_weight"])


def confusion(name: str, grid: geo.Grid, experiment: str) -> np.ndarray:
    """Area-weighted confusion matrix over BANDS: rows = truth, cols = prediction."""
    t = geo.truth(grid)["band"]
    g = to_grid(name, grid, experiment)
    w = grid.weights
    n = len(geo.BANDS)
    m = np.zeros((n, n))
    for a, ta in enumerate(geo.BANDS):
        for b, pb in enumerate(geo.BANDS):
            m[a, b] = w[(t == ta) & (g["pred"] == pb) & g["have"]].sum()
    return m


def calibration(name: str, grid: geo.Grid, bins: int = 10) -> list[dict]:
    """For land runs: per probability bin, mean predicted p vs observed land fraction (area-weighted)."""
    t = geo.truth(grid)["land"]
    g = to_grid(name, grid, "land")
    w = grid.weights
    p = g["p"]
    rows = []
    for k in range(bins):
        lo, hi = k / bins, (k + 1) / bins
        m = g["have"] & (p >= lo) & ((p < hi) if k < bins - 1 else (p <= hi))
        if m.any():
            rows.append(
                {
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "points": int(m.sum()),
                    "mean_p": float((p[m] * w[m]).sum() / w[m].sum()),
                    "land_fraction": float((t[m] * w[m]).sum() / w[m].sum()),
                }
            )
    return rows
