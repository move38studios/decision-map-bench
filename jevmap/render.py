"""Draw grid arrays as equirectangular map images."""

from functools import cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely

from jevmap import geo

MAPS = geo.ROOT / "results" / "maps"
EXTENT = (-180, 180, -90, 90)

BAND_COLOURS = {
    "deep_ocean": "#1f4e79",
    "open_ocean": "#3a7dc0",
    "shallow_sea": "#9cc9eb",
    "lowland": "#3f8f4f",
    "hills": "#a6cf7a",
    "upland": "#f0e08a",
    "mountains": "#b07a43",
    "high_mountains": "#6b3f22",
}
MISSING = "#ff00ff"
OCEAN_COLOUR = "#dce9f2"
POLITICAL_PALETTE = ["#e8a0a0", "#f2cf8a", "#a8d5a2", "#9fc3e6", "#c8a8dc", "#f0b8d0", "#b8d8d0"]


def _hex(c: str) -> tuple[float, float, float]:
    return matplotlib.colors.to_rgb(c)


def _save(img: np.ndarray, path: Path, title: str | None = None, scale: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8 * scale, 4.2 * scale if title else 4 * scale), dpi=150)
    ax.imshow(img, extent=EXTENT, interpolation="nearest", aspect="auto")
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=11, loc="left")
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, facecolor="white")
    plt.close(fig)
    return path


def land_bw(pred: np.ndarray, have: np.ndarray | None = None) -> np.ndarray:
    img = np.where(pred[..., None], 1.0, 0.0) * np.ones(3)
    if have is not None:
        img[~have] = _hex(MISSING)
    return img


def land_prob(p: np.ndarray) -> np.ndarray:
    img = np.nan_to_num(p, nan=0.5)[..., None] * np.ones(3)
    img[np.isnan(p)] = _hex(MISSING)
    return img


def land_errors(pred: np.ndarray, truth: np.ndarray, have: np.ndarray) -> np.ndarray:
    """Correct land light grey, correct water dark grey, false land red, false water blue."""
    img = np.zeros(pred.shape + (3,))
    img[truth & pred] = _hex("#d9d9d9")
    img[~truth & ~pred] = _hex("#4d4d4d")
    img[~truth & pred] = _hex("#e0382c")
    img[truth & ~pred] = _hex("#2c7be0")
    img[~have] = _hex(MISSING)
    return img


def bands(pred: np.ndarray) -> np.ndarray:
    img = np.zeros(pred.shape + (3,))
    for b, c in BAND_COLOURS.items():
        img[pred == b] = _hex(c)
    img[pred == ""] = _hex(MISSING)
    return img


@cache
def country_colours() -> dict[str, str]:
    """Greedy map colouring so that neighbouring countries differ."""
    names, geoms = geo.countries()
    tree = shapely.STRtree(geoms)
    order = sorted(range(len(names)), key=lambda k: -geoms[k].area)
    colour: dict[int, int] = {}
    for k in order:
        near = tree.query(geoms[k].buffer(0.3), predicate="intersects")
        used = {colour[n] for n in near if n in colour}
        colour[k] = next(c for c in range(len(POLITICAL_PALETTE)) if c not in used) if len(used) < len(
            POLITICAL_PALETTE
        ) else k % len(POLITICAL_PALETTE)
    out = {names[k]: POLITICAL_PALETTE[c] for k, c in colour.items()}
    out[geo.OCEAN] = OCEAN_COLOUR
    return out


def political(pred: np.ndarray) -> np.ndarray:
    cols = country_colours()
    img = np.zeros(pred.shape + (3,))
    for i in range(pred.shape[0]):
        for j in range(pred.shape[1]):
            c = pred[i, j]
            img[i, j] = _hex(cols.get(c, MISSING)) if c else _hex(MISSING)
    return img


def political_errors(pred: np.ndarray, truth: np.ndarray, have: np.ndarray) -> np.ndarray:
    """Ocean light, correct country green, wrong country red, land called ocean blue, ocean called land orange."""
    img = np.ones(pred.shape + (3,))
    sea_t = truth == geo.OCEAN
    sea_p = pred == geo.OCEAN
    img[sea_t & sea_p] = _hex(OCEAN_COLOUR)
    img[~sea_t & (pred == truth)] = _hex("#5aa469")
    img[~sea_t & ~sea_p & (pred != truth)] = _hex("#e0382c")
    img[~sea_t & sea_p] = _hex("#2c7be0")
    img[sea_t & ~sea_p] = _hex("#f0a030")
    img[~have] = _hex(MISSING)
    return img


def save(img: np.ndarray, name: str, title: str | None = None, scale: float = 1.0) -> Path:
    return _save(img, MAPS / f"{name}.png", title, scale)


def panel(images: list[tuple[np.ndarray, str]], path: Path, cols: int = 3, suptitle: str | None = None) -> Path:
    """Several maps in one figure, like the Claude comparison chart."""
    rows = (len(images) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 2.4 * rows), dpi=150, squeeze=False)
    for ax in axes.flat:
        ax.set_axis_off()
    for ax, (img, title) in zip(axes.flat, images):
        ax.imshow(img, extent=EXTENT, interpolation="nearest", aspect="auto")
        ax.set_title(title, fontsize=10, loc="left")
    if suptitle:
        fig.suptitle(suptitle, fontsize=13, x=0.01, ha="left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
