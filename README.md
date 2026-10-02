# decision-map-bench

How well do decision models know geography?

Decision models answer typed questions (yes/no, multiple choice) with probabilities instead of generating text. This repo asks four of them about every point of a 2° grid of the globe, and about 500 cities by name, and scores the answers against real geodata.

- **Blog post:** [How well do decision models know geography?](https://move38labs.com/decision-models-geography/)
- **Models:** [Jev 1.13](https://docs.typesafe.ai) (TypeSafe), [Clef and Clef-flash](https://blog.cloudflare.com/clef-decision-models/) (Cloudflare Workers AI), [Laya](https://github.com/NandhaKishorM/laya) (open weights)
- **Based on:** the "Land or Water?" eval from [How Does A Blind Model See The Earth?](https://outsidetext.substack.com/p/how-does-a-blind-model-see-the-earth)

## Results (2° grid, 16,200 points)

| | Land/water accuracy | AUC | Continent, from coordinate | Continent, from city name | Country, land points |
|---|---|---|---|---|---|
| Jev 1.13 | 84.1% | 0.93 | 92.2% | 98.8% | 75.3% |
| Clef | 83.8% | 0.90 | 73.4% | 98.2% | 63.3% |
| Clef-flash | 80.7% | 0.84 | 89.5% | 97.0% | 49.6% |
| Laya typed-decisions | 29.0% | 0.69 | 0% | 45.0% | – |
| Baseline | 71.0% (all "water") | 0.50 | | 46.6% (most common) | |

Land/water: "If this location is over land, say 'Land'. If this location is over water, say 'Water'.", P(Land) ≥ 0.5, area-weighted. Each model in its better layout: Jev with the coordinate in the question (100 per request), Clef and Clef-flash with the coordinate as the state (one per request).

Full numbers: `results/metrics/bench_2deg.json`, `results/metrics/names.json`.

## Reproduce

```
uv sync
cp .env.example .env        # fill in keys
uv run python -m scripts.download_data
uv run python -m scripts.check_connection
```

Every answer is cached in `results/raw/`, so scoring and figures run without any API calls:

```
uv run python -m scripts.bench_score      # -> results/metrics/bench_2deg.json
uv run python -m scripts.names_score      # -> results/metrics/names.json
uv run python -m scripts.bench_figures    # -> results/maps/bench_*.png
uv run python -m blog.build               # -> blog/index.html
```

To ask the models again (costs money; delete or rename the cached runs first):

```
uv run python -m scripts.bench jev|clef|clef-flash      # 2° suite, coordinate in the question
uv run python -m scripts.laya_bench laya-typed 2 state  # Laya on a Modal GPU
uv run python -m scripts.names <model>                  # place-name test
```

Approximate cost of one 2° land/water map: Jev $0.04, Clef $0.34–0.56. The 243-option country map: Jev $1.33, Clef $14.62–14.87.

## Layout

```
jevmap/
  geo.py        grids, ground truth (land mask, ETOPO1 bands, Natural Earth countries, continents)
  prompts.py    question wording and coordinate formats
  runner.py     batched async runs with a per-point answer cache (results/raw/*.jsonl[.gz])
  backends.py   Clef / Clef-flash client (Cloudflare Workers AI REST)
  bench.py      cross-model scoring: P(land) from any question, AUC, calibration
  score.py      per-experiment metrics; render.py: map images
scripts/
  bench.py, laya_bench.py, modal_laya.py, names.py      run the cross-model study
  bench_score.py, names_score.py, bench_figures.py      score and draw
  og_images.py                                          1200x630 social cards (og_physical is the main one)
  phase0.py, phase1.py, main_runs.py, explore.py,
  phase4.py, original_prompt.py, analysis.py            the earlier Jev-only study (10°, 5°, 2°, 1° grids)
  laya_sanity.py                                        checks that Laya is run correctly
  download_data.py, check_connection.py
results/
  raw/          every answer from every model (JSONL; large runs gzipped)
  metrics/      scores
  maps/         rendered maps
blog/           the post (template.html + build.py -> index.html)
report/         first write-up, Jev only
JOURNAL.md      working notes, in order, including dead ends
```

## Data

- Land/water: 1-km GLOBE land mask via [global-land-mask](https://github.com/toddkarin/global-land-mask). Large lakes count as land.
- Elevation and depth: ETOPO1 (NOAA), ice surface, via [ERDDAP](https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.html). Public domain.
- Countries and cities: [Natural Earth](https://www.naturalearthdata.com/) 1:50m. Public domain.
- Claude scores in the post are read from [this chart](https://x.com/celestepoasts/status/2103232383139057950).

## License

MIT, see `LICENSE`. The ground-truth data has its own terms (all public domain, see above).
