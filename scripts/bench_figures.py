"""Map images for the cross-model write-up (results/maps/bench_*.png)."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mc
import matplotlib.pyplot as plt
import numpy as np

from jevmap import bench, geo, render, runner, score
from scripts.analysis import grey
from scripts.explore import CONTINENT_COLOURS

GRID = geo.Grid(2)
MAPS = render.MAPS
MODELS = [(k, k, bench.BEST_LAYOUT[k]) for k in ("jev", "clef", "clef-flash", "laya-typed")]


def continent_img(pred: np.ndarray) -> np.ndarray:
    img = np.zeros(pred.shape + (3,))
    for i in range(pred.shape[0]):
        for j in range(pred.shape[1]):
            c = pred[i, j]
            img[i, j] = mc.to_rgb(CONTINENT_COLOURS.get(c, render.OCEAN_COLOUR if c else render.MISSING))
    return img


def choices(name: str) -> np.ndarray:
    recs = runner.load(name)
    pred = np.full(GRID.shape, "", dtype=object)
    for i, lat in enumerate(GRID.lats):
        for j, lon in enumerate(GRID.lons):
            r = recs.get(geo.point_id(lat, lon))
            if r:
                pred[i, j] = r["choice"]
    return pred


def main() -> None:
    t = geo.truth(GRID)
    metrics = json.loads((geo.ROOT / "results" / "metrics" / "bench_2deg.json").read_text())
    sheet = [(render.land_bw(t["land"]), "Truth (1-km land mask)")]
    for key, backend, _ in MODELS:
        layout = bench.section_layout(key)
        p = bench.p_land(bench.best_land_run(key), "orig_choice", GRID)
        render.save(render.land_bw(p >= 0.5), f"bench_land_{key}")
        render.save(grey(p), f"bench_p_land_{key}")
        acc = bench.land_metrics(p, GRID)["accuracy"]
        label = f"{bench.LABEL[key]}   says Land everywhere ({acc:.1%})" if key.startswith("laya") else f"{bench.LABEL[key]}   {acc:.1%}"
        sheet.append((render.land_bw(p >= 0.5), label))
        # Continent / ocean answers.
        render.save(continent_img(choices(bench.run_name(backend, "continent", layout))), f"bench_continent_{key}")
        # Physical, atlas colours.
        g = score.to_grid(bench.run_name(backend, "physical_colour", layout), GRID, "physical_colour")
        render.save(render.bands(g["pred"]), f"bench_physical_colour_{key}")
        g = score.to_grid(bench.run_name(backend, "physical_terrain", layout), GRID, "physical_terrain")
        render.save(render.bands(g["pred"]), f"bench_physical_terrain_{key}")
        # Political, on true land points only.
        name = bench.run_name(backend, "political", layout)
        if runner.has(name):
            pred = choices(name)
            render.save(render.political(np.where(t["country"] == geo.OCEAN, geo.OCEAN, pred)), f"bench_political_{key}")
            render.save(render.political(pred), f"bench_political_all_{key}")
    # Truth images under bench_ names, so the report only ships one family.
    true_c = np.array([[geo.continent_of(c, lon) for c, lon in zip(row, GRID.lons)] for row in t["country"]], dtype=object)
    timg = np.zeros(GRID.shape + (3,))
    for i in range(GRID.shape[0]):
        for j in range(GRID.shape[1]):
            c = true_c[i, j]
            timg[i, j] = mc.to_rgb(CONTINENT_COLOURS[c]) if c else (mc.to_rgb("#cccccc") if t["land"][i, j] else mc.to_rgb(render.OCEAN_COLOUR))
    render.save(timg, "bench_continent_truth")
    render.save(render.land_bw(t["land"]), "bench_land_truth")
    render.save(render.bands(t["band"]), "bench_physical_truth")
    render.save(render.political(t["country"]), "bench_political_truth")

    # One shareable sheet in the style of the Claude chart.
    fig, axes = plt.subplots(2, 3, figsize=(12.6, 5.6), dpi=150)
    for ax in axes.flat:
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#999999")
    axes.flat[-1].set_axis_off()
    for ax, (img, title) in zip(axes.flat, sheet):
        ax.imshow(img, extent=render.EXTENT, interpolation="nearest", aspect="auto")
        ax.set_title(title, fontsize=11, loc="left")
    axes.flat[-1].text(0.0, 0.55, "“If this location is over land, say 'Land'.\nIf this location is over water, say 'Water'.”\n\n2° grid · 16,200 points · white = Land (p ≥ 0.5)\naccuracy area-weighted vs 1-km land mask\nanswering “water” everywhere scores 71.0%\neach model in its better layout\n(coordinate in the question or as the state)",
                       transform=axes.flat[-1].transAxes, fontsize=9.5, va="center", color="#333")
    fig.suptitle("How decision models see the Earth", fontsize=15, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(MAPS / "bench_sheet.png", facecolor="white", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
