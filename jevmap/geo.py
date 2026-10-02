"""Grids and ground truth: land mask, elevation bands, countries."""

import csv
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
import shapely
from global_land_mask import globe

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Physical-map bands, ordered from deepest to highest.
BANDS = [
    "deep_ocean",
    "open_ocean",
    "shallow_sea",
    "lowland",
    "hills",
    "upland",
    "mountains",
    "high_mountains",
]
WATER_BANDS = {"deep_ocean", "open_ocean", "shallow_sea"}

OCEAN = "Ocean"


@dataclass(frozen=True)
class Grid:
    """Cell-centre grid at `step` degrees, row 0 = northernmost."""

    step: float

    @property
    def lats(self) -> np.ndarray:
        n = round(180 / self.step)
        return 90 - self.step / 2 - self.step * np.arange(n)

    @property
    def lons(self) -> np.ndarray:
        n = round(360 / self.step)
        return -180 + self.step / 2 + self.step * np.arange(n)

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.lats), len(self.lons)

    def points(self) -> list[tuple[float, float]]:
        """All (lat, lon) pairs in row-major order."""
        return [(float(lat), float(lon)) for lat in self.lats for lon in self.lons]

    @property
    def weights(self) -> np.ndarray:
        """Area weights (cos latitude), same shape as the grid."""
        w = np.cos(np.radians(self.lats))[:, None] * np.ones(len(self.lons))[None, :]
        return w


def point_id(lat: float, lon: float) -> str:
    return f"{lat:+.2f}_{lon:+.2f}"


def is_land(lat: float, lon: float) -> bool:
    return bool(globe.is_land(lat, lon))


@cache
def _etopo() -> tuple[np.ndarray, float, float, float]:
    """ETOPO1 (ice surface) subsampled to 0.25 degrees: (grid[lat_idx, lon_idx], lat0, lon0, step)."""
    npy = DATA / "etopo_q.npy"
    if not npy.exists():
        with open(DATA / "etopo_q.csv") as f:
            rows = csv.reader(f)
            next(rows), next(rows)
            alt = np.array([int(r[2]) for r in rows], dtype=np.int16)
        np.save(npy, alt.reshape(721, 1441))
    return np.load(npy), -90.0, -180.0, 0.25


def elevation(lat: float, lon: float) -> int:
    grid, lat0, lon0, step = _etopo()
    i = round((lat - lat0) / step)
    j = round((lon - lon0) / step)
    return int(grid[i, j])


def band(lat: float, lon: float) -> str:
    """Physical-map band: land/water from the 1-km mask, depth/height from ETOPO1."""
    e = elevation(lat, lon)
    if not is_land(lat, lon):
        if e <= -3000:
            return "deep_ocean"
        if e <= -200:
            return "open_ocean"
        return "shallow_sea"
    if e < 200:
        return "lowland"
    if e < 500:
        return "hills"
    if e < 1500:
        return "upland"
    if e < 3000:
        return "mountains"
    return "high_mountains"


@cache
def countries() -> tuple[list[str], list]:
    """Natural Earth 1:50m admin-0 units: (names, geometries)."""
    features = json.loads((DATA / "ne_50m_admin_0_countries.geojson").read_text())["features"]
    names = [f["properties"]["ADMIN"] for f in features]
    geoms = [shapely.geometry.shape(f["geometry"]) for f in features]
    return names, geoms


@cache
def _country_tree() -> shapely.STRtree:
    return shapely.STRtree(countries()[1])


def country_names() -> list[str]:
    return sorted(countries()[0])


def country_of(points: list[tuple[float, float]]) -> list[str]:
    """Country name for each (lat, lon), or OCEAN outside every admin-0 polygon."""
    names, _ = countries()
    geoms = shapely.points([(lon, lat) for lat, lon in points])
    pt_idx, geom_idx = _country_tree().query(geoms, predicate="intersects")
    out = [OCEAN] * len(points)
    for p, g in zip(pt_idx, geom_idx):
        out[p] = names[g]
    return out


def truth(grid: Grid) -> dict[str, np.ndarray]:
    """Ground-truth arrays for every grid point, cached under data/."""
    path = DATA / f"truth_{grid.step:g}.npz"
    if path.exists():
        z = np.load(path, allow_pickle=False)
        return {k: z[k] for k in z.files}
    pts = grid.points()
    land = np.array([is_land(lat, lon) for lat, lon in pts]).reshape(grid.shape)
    elev = np.array([elevation(lat, lon) for lat, lon in pts]).reshape(grid.shape)
    bands = np.array([band(lat, lon) for lat, lon in pts]).reshape(grid.shape)
    country = np.array(country_of(pts)).reshape(grid.shape)
    out = {"land": land, "elevation": elev, "band": bands, "country": country}
    np.savez_compressed(path, **out)
    return out


CONTINENTS = ["Africa", "Antarctica", "Asia", "Europe", "North America", "Oceania", "South America"]


@cache
def _continent_by_country() -> dict[str, str]:
    features = json.loads((DATA / "ne_50m_admin_0_countries.geojson").read_text())["features"]
    return {f["properties"]["ADMIN"]: f["properties"]["CONTINENT"] for f in features}


def continent_of(country: str, lon: float) -> str:
    """Continent for a Natural Earth country; Russia east of 60°E counts as Asia. '' for ocean / open-sea islands."""
    if country == OCEAN:
        return ""
    if country == "Russia":
        return "Asia" if lon > 60 else "Europe"
    c = _continent_by_country().get(country, "")
    return c if c in CONTINENTS else ""
