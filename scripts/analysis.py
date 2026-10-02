"""Extra figures from the probabilities Jev returns, plus the comparison with the Claude chart.

Usage: uv run python -m scripts.analysis 2
"""

import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from jevmap import geo, prompts, render, runner, score

MAPS = render.MAPS
METRICS = geo.ROOT / "results" / "metrics"

# Read off the "How 12 blind Claudes see the Earth" chart (2 degree grid, area-weighted).
CLAUDE = {
    "Sonnet 4.5": 60.5,
    "Haiku 4.5": 81.3,
    "Opus 4.5": 82.6,
    "Sonnet 4.6": 89.1,
    "Opus 4.6": 91.2,
    "Opus 4.7": 91.2,
    "Sonnet 5": 91.5,
    "Opus 4.8": 91.7,
    "Opus 5": 92.5,
    "Fable 5": 97.8,
    "Fable 5.1": 98.2,
    "Opus 5.5": 99.0,
}


def prob_grid(name: str, grid: geo.Grid, fn) -> np.ndarray:
    """Apply fn(record) to every cached record, as a grid array (NaN where missing)."""
    recs = runner.load(name)
    out = np.full(grid.shape, np.nan)
    for i, lat in enumerate(grid.lats):
        for j, lon in enumerate(grid.lons):
            r = recs.get(geo.point_id(lat, lon))
            if r:
                out[i, j] = fn(r)
    return out


def grey(a: np.ndarray, cmap: str = "gray") -> np.ndarray:
    img = plt.get_cmap(cmap)(np.nan_to_num(a, nan=0.0))[..., :3]
    img[np.isnan(a)] = matplotlib.colors.to_rgb(render.MISSING)
    return img


def wacc(correct: np.ndarray, grid: geo.Grid, mask: np.ndarray) -> float:
    w = grid.weights
    return float((correct * w)[mask].sum() / w[mask].sum())


def main(step: float) -> None:
    grid = geo.Grid(step)
    tag = f"{step:g}deg"
    t = geo.truth(grid)
    land = t["land"]
    metrics = json.loads((METRICS / f"{tag}.json").read_text())
    extra: dict = {}

    # 1. Probability of land, three ways: Noul, and the summed land bands of each physical Choice.
    p_noul = score.to_grid(f"g{step:g}_land", grid, "land")["p"]
    land_labels = {
        v: {lab for lab, b in prompts.physical_label_to_band(v).items() if b not in geo.WATER_BANDS}
        for v in ("terrain", "colour")
    }
    p_terrain = prob_grid(f"g{step:g}_physical_terrain", grid, lambda r: sum(p for k, p in r["probs"].items() if k in land_labels["terrain"]))
    p_colour = prob_grid(f"g{step:g}_physical_colour", grid, lambda r: sum(p for k, p in r["probs"].items() if k in land_labels["colour"]))
    for key, p in [("noul", p_noul), ("terrain", p_terrain), ("colour", p_colour)]:
        render.save(grey(p), f"{tag}_p_land_{key}")
        have = ~np.isnan(p)
        extra[f"p_land_{key}_acc_0.5"] = wacc((p >= 0.5) == land, grid, have)
    # Average of the three probability maps: a cheap ensemble.
    p_mean = np.nanmean(np.stack([p_noul, p_terrain, p_colour]), axis=0)
    render.save(grey(p_mean), f"{tag}_p_land_ensemble")
    render.save(render.land_bw(p_mean >= 0.5), f"{tag}_land_ensemble")
    extra["p_land_ensemble_acc_0.5"] = wacc((p_mean >= 0.5) == land, grid, ~np.isnan(p_mean))
    render.panel(
        [
            (render.land_bw(land), "Truth"),
            (grey(p_noul), "Noul: 'this location is on land'"),
            (grey(p_terrain), "Physical Choice (terrain names): P(land bands)"),
            (grey(p_colour), "Physical Choice (atlas colours): P(land colours)"),
            (grey(p_mean), "Average of the three"),
            (render.land_bw(p_mean >= 0.5), f"Average ≥ 0.5: {extra['p_land_ensemble_acc_0.5']:.1%}"),
        ],
        MAPS / f"{tag}_p_land_panel.png",
        cols=3,
        suptitle=f"Probability of land, {step:g}° grid (white = land)",
    )

    # 2. Confidence maps for the Choice answers; political P(Ocean).
    conf_terrain = prob_grid(f"g{step:g}_physical_terrain", grid, lambda r: r["confidence"])
    conf_colour = prob_grid(f"g{step:g}_physical_colour", grid, lambda r: r["confidence"])
    conf_pol = prob_grid(f"g{step:g}_political", grid, lambda r: r["confidence"])
    p_ocean = prob_grid(f"g{step:g}_political", grid, lambda r: r["probs"].get(geo.OCEAN, 0.0))
    for key, a in [("physical_terrain", conf_terrain), ("physical_colour", conf_colour), ("political", conf_pol)]:
        render.save(grey(a, "magma"), f"{tag}_{key}_confidence")
    render.save(grey(p_ocean), f"{tag}_political_p_ocean")

    # Political answers on true land only (sea points painted as sea), next to the truth.
    pol = score.to_grid(f"g{step:g}_political", grid, "political")
    sea = t["country"] == geo.OCEAN
    pol_on_land = np.where(sea, geo.OCEAN, pol["pred"])
    render.save(render.political(pol_on_land), f"{tag}_political_jev_on_land")
    render.panel(
        [(render.political(t["country"]), "Truth (Natural Earth)"), (render.political(pol_on_land), "Jev, on land points")],
        MAPS / f"{tag}_political_panel.png",
        cols=2,
    )

    # Does confidence predict correctness? Political accuracy on land by confidence quintile.
    on_land = (t["country"] != geo.OCEAN) & pol["have"]
    correct = pol["pred"] == t["country"]
    qs = np.nanquantile(conf_pol[on_land], [0, 0.2, 0.4, 0.6, 0.8, 1.0])
    extra["political_accuracy_by_confidence"] = []
    for lo, hi in zip(qs[:-1], qs[1:]):
        m = on_land & (conf_pol >= lo) & (conf_pol <= hi)
        extra["political_accuracy_by_confidence"].append(
            {"confidence": f"{lo:.2f}-{hi:.2f}", "points": int(m.sum()), "accuracy": wacc(correct, grid, m)}
        )
    # Coverage/accuracy trade-off: keep only answers above a confidence threshold.
    extra["political_confidence_gate"] = []
    for thr in (0.0, 0.3, 0.5, 0.7, 0.9):
        m = on_land & (conf_pol >= thr)
        extra["political_confidence_gate"].append(
            {"threshold": thr, "coverage": float(m.sum() / on_land.sum()), "accuracy": wacc(correct, grid, m)}
        )

    # 3. Calibration of the Noul.
    cal = score.calibration(f"g{step:g}_land", grid, bins=10)
    fig, ax = plt.subplots(figsize=(4.5, 4.5), dpi=150)
    ax.plot([0, 1], [0, 1], color="#999", lw=1, ls="--")
    ax.plot([r["mean_p"] for r in cal], [r["land_fraction"] for r in cal], marker="o", color="#222")
    for r in cal:
        ax.annotate(str(r["points"]), (r["mean_p"], r["land_fraction"]), fontsize=7, xytext=(4, -10), textcoords="offset points", color="#666")
    ax.set_xlabel("Jev's probability of land")
    ax.set_ylabel("Fraction actually land")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title(f"Calibration, {step:g}° grid", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(MAPS / f"{tag}_land_calibration.png", facecolor="white")
    plt.close(fig)

    # 4. Accuracy by latitude band (land/water at 0.5).
    lw = score.to_grid(f"g{step:g}_land", grid, "land")
    by_lat = []
    for lo in range(-90, 90, 10):
        rows = (grid.lats >= lo) & (grid.lats < lo + 10)
        sel = lw["have"][rows]
        by_lat.append({"lat": f"{lo}..{lo + 10}", "accuracy": float(((lw["pred"] == land)[rows][sel]).mean()), "land_share": float(land[rows].mean())})
    extra["land_accuracy_by_latitude"] = by_lat
    fig, ax = plt.subplots(figsize=(4.5, 4.5), dpi=150)
    centers = [lo + 5 for lo in range(-90, 90, 10)]
    ax.barh(centers, [r["accuracy"] for r in by_lat], height=8, color="#444")
    ax.set_xlim(0, 1)
    ax.set_ylabel("Latitude")
    ax.set_xlabel("Land/water accuracy (p ≥ 0.5)")
    ax.set_title(f"Accuracy by latitude, {step:g}° grid", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(MAPS / f"{tag}_land_by_latitude.png", facecolor="white")
    plt.close(fig)

    # 5. The Claude chart with Jev added.
    jev = metrics["runs"]["land"]["accuracy"] * 100
    jev_tuned = metrics["runs"]["land"]["accuracy_tuned_threshold"] * 100
    rows = sorted(list(CLAUDE.items()) + [("Jev 1.13 (p ≥ 0.5)", jev), ("Jev 1.13 (p ≥ 0.70)", jev_tuned)], key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(6.5, 5), dpi=150)
    colours = ["#d9534f" if k.startswith("Jev") else "#8a8a8a" for k, _ in rows]
    ax.barh([k for k, _ in rows], [v for _, v in rows], color=colours)
    for k, (name, v) in enumerate(rows):
        ax.text(v + 0.5, k, f"{v:.1f}%", va="center", fontsize=8)
    ax.set_xlim(50, 102)
    ax.set_xlabel("Land/water accuracy, 2° grid, area-weighted (%)")
    ax.set_title("Jev vs the 12 Claudes", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(MAPS / f"{tag}_jev_vs_claudes.png", facecolor="white")
    plt.close(fig)

    # 6. Headline image in the style of the Claude chart.
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    ax.imshow(render.land_bw(lw["pred"]), extent=render.EXTENT, interpolation="nearest", aspect="auto")
    ax.set_axis_off()
    ax.set_title(f"Jev 1.13   {jev:.1f}%", loc="left", fontsize=12)
    fig.savefig(MAPS / f"{tag}_land_jev_headline.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    (METRICS / f"{tag}_analysis.json").write_text(json.dumps(extra, indent=2))
    print(json.dumps(extra, indent=2))


if __name__ == "__main__":
    main(float(sys.argv[1]))
