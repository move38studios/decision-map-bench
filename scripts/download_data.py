"""Download the ground-truth data into data/ (about 25 MB).

Usage: uv run python -m scripts.download_data

- Natural Earth 1:50m admin-0 countries and populated places (public domain)
- ETOPO1 ice-surface elevation, subsampled to 0.25°, from NOAA ERDDAP (public domain)
- IBM Plex Sans, for the social-card images (SIL Open Font License)
The 1-km land mask ships inside the `global-land-mask` package.
"""

import urllib.request

from jevmap import geo

NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
FILES = {
    "ne_50m_admin_0_countries.geojson": NE + "ne_50m_admin_0_countries.geojson",
    "ne_50m_populated_places_simple.geojson": NE + "ne_50m_populated_places_simple.geojson",
    "fonts/IBMPlexSans-Regular.ttf": "https://github.com/IBM/plex/raw/master/packages/plex-sans/fonts/complete/ttf/IBMPlexSans-Regular.ttf",
    "fonts/IBMPlexSans-SemiBold.ttf": "https://github.com/IBM/plex/raw/master/packages/plex-sans/fonts/complete/ttf/IBMPlexSans-SemiBold.ttf",
    "etopo_q.csv": "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv?altitude%5B(-90.0):15:(90.0)%5D%5B(-180.0):15:(180.0)%5D",
}

if __name__ == "__main__":
    geo.DATA.mkdir(exist_ok=True)
    for name, url in FILES.items():
        path = geo.DATA / name
        if path.exists():
            print("have", name)
            continue
        print("downloading", name)
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, path)
    print("done")
