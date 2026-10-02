"""Composite images for social cards (1200x630) in the style of the post.

Usage: uv run python -m scripts.og_images   -> results/maps/og_*.png
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

from jevmap import bench, geo, render, runner
from scripts.analysis import grey
from scripts.bench_figures import choices, continent_img

GRID = geo.Grid(2)
MAPS = render.MAPS
FONTS = geo.DATA / "fonts"
BG, FG, MUTED, RULE = "#fbfbfa", "#1b1d21", "#61666f", "#d6d9dd"
COL = {"jev": "#d0491c", "clef": "#1f56d6", "clef-flash": "#5ea3f0", "laya-typed": "#8a4fd8"}
NAME = {"jev": "Jev 1.13", "clef": "Clef", "clef-flash": "Clef-flash", "laya-typed": "Laya"}
W, H, DPI = 1200, 630, 100


def font(weight: str) -> fm.FontProperties:
    path = FONTS / f"IBMPlexSans-{weight}.ttf"
    return fm.FontProperties(fname=str(path)) if path.exists() else fm.FontProperties(weight="bold" if weight == "SemiBold" else "normal")


SEMI, REG = font("SemiBold"), font("Regular")


def canvas():
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=BG)
    return fig


def px(x, y, w, h):
    """Axes rectangle from pixel coordinates (top-left origin)."""
    return [x / W, 1 - (y + h) / H, w / W, h / H]


def put_map(fig, img, x, y, w, label=None, colour=None, value=None):
    h = w / 2
    ax = fig.add_axes(px(x, y, w, h))
    ax.imshow(img, extent=render.EXTENT, interpolation="nearest", aspect="auto")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color(RULE)
    if label:
        ty = 1 - (y + h + 8) / H
        tx = x / W
        if colour:
            fig.patches.append(matplotlib.patches.Rectangle((tx, ty - 13 / H), 12 / W, 12 / H, transform=fig.transFigure, color=colour))
            tx += 18 / W
        fig.text(tx, ty, label, fontproperties=SEMI, fontsize=15, color=FG, va="top")
        if value:
            fig.text((x + w) / W, ty, value, fontproperties=REG, fontsize=15, color=MUTED, va="top", ha="right")
    return h


def title(fig, text, sub, x=48, y=40):
    fig.text(x / W, 1 - y / H, text, fontproperties=SEMI, fontsize=30, color=FG, va="top")
    fig.text(x / W, 1 - (y + 48) / H, sub, fontproperties=REG, fontsize=16, color=MUTED, va="top")


def save(fig, name):
    fig.savefig(MAPS / f"{name}.png", dpi=DPI, facecolor=BG)
    plt.close(fig)


def land_card(metrics: dict) -> None:
    t = geo.truth(GRID)
    fig = canvas()
    title(fig, "How well do decision models know geography?", "“Land or Water?” at 16,200 points  ·  P(Land): white = land, black = water")
    mw, gap, top = 352, 24, 128
    cells = [("truth", render.land_bw(t["land"]), "Truth", None, None)]
    for k in ("jev", "clef", "clef-flash", "laya-typed"):
        p = bench.p_land(bench.best_land_run(k), "orig_choice", GRID)
        m = bench.land_metrics(p, GRID)
        val = "says Land everywhere" if k == "laya-typed" else f"{m['accuracy']:.1%}"
        cells.append((k, grey(p), NAME[k], COL[k], val))
    for i, (k, img, lab, col, val) in enumerate(cells):
        r, c = divmod(i, 3)
        put_map(fig, img, 48 + c * (mw + gap), top + r * (mw / 2 + 64), mw, lab, col, val)
    # Sixth cell: what the numbers mean.
    x, y = 48 + 2 * (mw + gap), top + (mw / 2 + 64)
    lines = ["Accuracy: P(Land) ≥ 0.5, area-weighted", "Answering “water” everywhere: 71.0%", "", "Jev (TypeSafe) · Clef (Cloudflare)", "Laya (open weights)"]
    for j, line in enumerate(lines):
        fig.text(x / W, 1 - (y + 6 + j * 26) / H, line, fontproperties=REG, fontsize=14, color=MUTED, va="top")
    save(fig, "og_landwater")


def continent_card() -> None:
    t = geo.truth(GRID)
    fig = canvas()
    fig.text(48 / W, 1 - 48 / H, "How decision\nmodels picture\nthe continents", fontproperties=SEMI, fontsize=28, color=FG, va="top", linespacing=1.15)
    fig.text(48 / W, 1 - 228 / H, "“Which continent or ocean\nis this location in?”\nasked at 16,200 points", fontproperties=REG, fontsize=16, color=MUTED, va="top", linespacing=1.4)
    true_c = np.array([[geo.continent_of(c, lon) for c, lon in zip(row, GRID.lons)] for row in t["country"]], dtype=object)
    import matplotlib.colors as mc
    from scripts.explore import CONTINENT_COLOURS
    timg = np.zeros(GRID.shape + (3,))
    for i in range(GRID.shape[0]):
        for j in range(GRID.shape[1]):
            c = true_c[i, j]
            timg[i, j] = mc.to_rgb(CONTINENT_COLOURS[c]) if c else (mc.to_rgb("#cccccc") if t["land"][i, j] else mc.to_rgb(render.OCEAN_COLOUR))
    metrics = json.loads((geo.ROOT / "results" / "metrics" / "bench_2deg.json").read_text())["models"]
    cells = [(timg, "Truth", None, None)]
    for k in ("jev", "clef", "clef-flash"):
        layout = bench.section_layout(k)
        mk = metrics[f"{k}-state"] if layout == "state" else metrics[k]
        cells.append((continent_img(choices(bench.run_name(k, "continent", layout))), NAME[k], COL[k], f"{mk['continent_accuracy']:.0%} of land"))
    mw, gap, x0, y0 = 380, 22, 376, 50
    for i, (img, lab, col, val) in enumerate(cells):
        r, c = divmod(i, 2)
        put_map(fig, img, x0 + c * (mw + gap), y0 + r * (mw / 2 + 74), mw, lab, col, val)
    save(fig, "og_continents")


def names_card() -> None:
    names = json.loads((geo.ROOT / "results" / "metrics" / "names.json").read_text())
    metrics = json.loads((geo.ROOT / "results" / "metrics" / "bench_2deg.json").read_text())["models"]
    fig = canvas()
    title(fig, "Names, not numbers", "Which continent? Filled: asked with a city name.  Hollow: asked with a coordinate.")
    ax = fig.add_axes(px(210, 150, 930, 420))
    ax.set_facecolor(BG)
    keys = ["jev", "clef", "clef-flash", "laya-typed"]
    for r, k in enumerate(keys):
        y = len(keys) - 1 - r
        layout = bench.section_layout(k)
        mk = metrics[f"{k}-state"] if layout == "state" else metrics[k]
        by_name, by_coord = names[k]["city_continent"], mk.get("continent_accuracy", 0.0)
        ax.plot([by_coord, by_name], [y, y], color=RULE, lw=3, zorder=1)
        ax.scatter([by_name], [y], s=260, color=COL[k], zorder=3)
        ax.scatter([by_coord], [y], s=260, facecolor=BG, edgecolor=COL[k], linewidth=3, zorder=3)
        ax.text(by_name, y + 0.28, f"{by_name:.0%}", ha="center", fontproperties=REG, fontsize=14, color=FG)
        ax.text(by_coord, y - 0.42, f"{by_coord:.0%}", ha="center", fontproperties=REG, fontsize=14, color=MUTED)
        ax.text(-0.02, y, NAME[k], transform=ax.get_yaxis_transform(), ha="right", va="center", fontproperties=SEMI, fontsize=18, color=FG, clip_on=False)
    ax.set_xlim(-0.03, 1.05)
    ax.set_ylim(-0.8, len(keys) - 0.4)
    ax.set_yticks([])
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontproperties=REG, fontsize=12, color=MUTED)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="x", color=RULE, lw=0.8)
    ax.set_axisbelow(True)
    save(fig, "og_names")




BAND_LABELS = {
    "deep_ocean": "Deep ocean, > 3,000 m", "open_ocean": "Ocean, 200–3,000 m", "shallow_sea": "Shallow sea", "lowland": "Lowland, < 200 m",
    "hills": "Hills, 200–500 m", "upland": "Upland, 500–1,500 m", "mountains": "Mountains, 1,500–3,000 m", "high_mountains": "High mountains, > 3,000 m",
}


def physical_card() -> None:
    from jevmap import score
    t = geo.truth(GRID)
    metrics = json.loads((geo.ROOT / "results" / "metrics" / "bench_2deg.json").read_text())["models"]
    fig = canvas()
    fig.text(48 / W, 1 - 44 / H, "How well do\ndecision models\nknow geography?", fontproperties=SEMI, fontsize=27, color=FG, va="top", linespacing=1.15)
    fig.text(48 / W, 1 - 178 / H, "Elevation and sea depth,\nasked as the colour on a\nphysical atlas, 16,200 points", fontproperties=REG, fontsize=14, color=MUTED, va="top", linespacing=1.4)
    for j, (b, lab) in enumerate(BAND_LABELS.items()):
        y = 300 + j * 30
        fig.patches.append(matplotlib.patches.Rectangle((48 / W, 1 - (y + 16) / H), 16 / W, 16 / H, transform=fig.transFigure, color=render.BAND_COLOURS[b]))
        fig.text(74 / W, 1 - (y + 1) / H, lab, fontproperties=REG, fontsize=13, color=FG, va="top")
    cells = [(render.bands(t["band"]), "Truth (ETOPO1)", None, None)]
    for k in ("jev", "clef", "clef-flash"):
        layout = bench.section_layout(k)
        mk = metrics[f"{k}-state"] if layout == "state" else metrics[k]
        g = score.to_grid(bench.run_name(k, "physical_colour", layout), GRID, "physical_colour")
        cells.append((render.bands(g["pred"]), NAME[k], COL[k], f"{mk['physical_colour']['within_one']:.0%} within one band"))
    mw, gap, x0, y0 = 380, 22, 376, 50
    for i, (img, lab, col, val) in enumerate(cells):
        r, c = divmod(i, 2)
        put_map(fig, img, x0 + c * (mw + gap), y0 + r * (mw / 2 + 74), mw, lab, col, val)
    save(fig, "og_physical")


if __name__ == "__main__":
    physical_card()  # the main social card for the post
    land_card(None)
    continent_card()
    names_card()
    print("wrote og_physical, og_landwater, og_continents, og_names")
