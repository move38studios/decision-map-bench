# Journal

Working notes for the jevmap experiment, kept as raw material for a blog post. Newest entries at the bottom. Numbers are area-weighted accuracies unless stated otherwise.

---

## 2026-10-02 — Setup

**Starting point.** A chart, "How 12 blind Claudes see the Earth": each Claude model asked "Land or Water?" at every 2° of the globe (16,200 points, no images, no tools), drawn as a white-land/black-water map and scored against a 1-km land mask, area-weighted. Scores run from 60.5% (Sonnet 4.5) to 99.0% (Opus 5.5). The question here: how well does Jev, TypeSafe's "System One" model, know the map?

**What Jev is.** Not a text generator. You send a `state` and typed questions; it returns structured answers:
- *Noul*: probability that a statement is true (0–1).
- *Choice*: one option from a set (up to 255), with a probability for every option and a confidence score.
- *Score*: a level on an ordered rubric.

Many questions can go in one request; each is evaluated in isolation against the same state. Billing is input tokens only, $0.042 per million.

**The docs flag a risk up front.** Jev "struggles with tasks that require numeric precision" and does better with semantic than numeric representations. A coordinate is pure number, so this experiment probes a known weak spot. That makes the coordinate format the first thing to tune.

**Plan.** Three maps:
1. Land/water — Noul.
2. Physical — Choice over 8 elevation/depth bands, asked two ways: (A) terrain names ("Mountains: land 1,500–3,000 m"), (B) atlas colour names ("brown"), to see if Jev "knows what an atlas looks like".
3. Political — Choice over all 242 Natural Earth admin-0 units plus "Ocean" (243 options, under the 255 limit). Colours are assigned in code.

Ground truth: `global-land-mask` (1-km GLOBE mask) for land/water, ETOPO1 for elevation/depth (pulled from NOAA ERDDAP at 0.25° spacing, which contains every grid used), Natural Earth 1:50m for countries.

Phases: hand-picked points → 10° grid prompt tuning → 5° → 2° headline → maybe 1°. Prompt frozen after the 10° phase so tuning doesn't leak into the headline.

**Connection test.** First call: `jev-latest` resolved to `jev-1.13.0`. `jev-preview` is also listed.

## Phase 0 — 22 hand-picked points

Points: mid-Pacific, Sahara, Amazon, Antarctic plateau, Greenland ice, Tibet, Kansas, Mediterranean, Black Sea, Caspian, Hudson Bay, Lake Victoria, Madagascar, Borneo, NZ South Island, Andes, Gulf of Mexico, etc.

**Token costs measured:**
| Experiment | Tokens per point |
|---|---|
| Land, one point per request | ~300 (≈250 fixed overhead per request) |
| Land, 22 points per request | ~47 |
| Physical, one per request | 365–525 |
| Political, 22 per request | ~1,960 (the 243-option list is repeated in each question) |

Batching 22 points into one request gave essentially the same answers as one point per request (0.27 vs 0.27, 0.44 vs 0.46, ...) — consistent with the docs' claim that questions are evaluated in isolation.

**First impressions:**
- Land/water probabilities are weakly separated. Deep ocean points come back 0.05–0.27; seas next to land come back high: Mediterranean 0.68–0.80, Gulf of Mexico 0.66–0.76, Black Sea 0.65–0.70. Jev appears to answer something closer to "is this near land".
- Political answers are strong on big unambiguous places: Kansas → USA (1.00), central Australia → Australia (1.00), Antarctic plateau → Antarctica (0.98), Greenland (0.92).
- Sea points are pulled to the neighbouring country: Black Sea → Turkey, Hudson Bay → Canada, Gulf of Mexico → USA, Southern Ocean at 60°S → Antarctica (0.94).
- Tibet → Nepal in one layout, China in the other (low confidence either way).

**Ground-truth quirk.** The 1-km land mask counts large lakes as land (Caspian Sea and Lake Victoria both come back `is_land = True`). Kept, because the Claude chart used a 1-km land mask too and comparability matters more. Affects a handful of points at 2°.

## Phase 1 — prompt tuning, 10° grid (648 points)

36 arms: coordinate format × layout × model.
- Formats: `latitude -35, longitude -175` (decimal), `35°S, 175°W` (hemi), `35 degrees south, 175 degrees west` (words).
- Layouts: coordinate in the `state` (one point per request) vs coordinate inside each question (100 points per request; 25 for political).
- Models: `jev-latest` vs `jev-preview`.

Cost of all 36 arms: **$0.64**. Three requests failed with a Cloudflare 520 and were re-asked on the next pass (the cache makes this free).

**Results, land/water (accuracy at p ≥ 0.5 → best possible single threshold):**
| Format | State layout | Question layout |
|---|---|---|
| decimal | 68.9% → 82.3% | 80.8% → 83.2% |
| hemi | 72.5% → 87.1% | 78.7% → 86.2% |
| words | 72.0% → 86.7% | 80.2% → 87.0% |

- Hemisphere letters (or words) beat signed decimals, as the docs' "semantic over numeric" advice predicts. Words ≈ hemi.
- Layout mostly moves the *calibration*, not the ranking: at the best threshold all hemi/words arms land at 86–87%. In the state layout Jev's land probabilities are shifted up (mean p for water points 0.43 vs 0.33–0.35).
- Best threshold is consistently around **0.65–0.70**, not 0.5. Jev leans "land".
- `jev-latest` and `jev-preview` are indistinguishable — both report `jev-1.13.0` in responses. Dropped preview.

**Physical (10°):** colour-named options score higher overall (58.0% vs 49.7%) because "dark blue" captures deep ocean well; terrain-named options do better on land points (31–35% vs 21–28%). Within-one-band ~78–83%.

**Political (10°):** hemi beats decimal clearly (land accuracy 73–75% vs 62–68%; top-3 93% vs 87%).

**Frozen config:** hemi format, coordinate-in-question layout, `jev-latest`. For land/water the headline uses p ≥ 0.5 (closest to asking yes/no); the threshold 0.70 tuned on the 10° grid is reported alongside. (The 10° grid points are a subset of the 2° grid — 648 of 16,200, 4% overlap — noted, small.)

## Phase 2 — 5° grid (2,592 points), $0.26

| Map | Result |
|---|---|
| Land/water | **77.4%** at 0.5; **84.7%** at the frozen 0.70 threshold. Land recall 92%, water recall 71%. |
| Physical, terrain names | 49.1% exact, 84.8% within one band, 86.5% land-vs-water |
| Physical, colour names | 56.2% exact, 77.0% within one band, 83.2% land-vs-water |
| Political | 72.4% of land points get the right country, 91.3% in top 3; only 34% of ocean points are called "Ocean" |

**What the land map looks like.** The broad layout is right — Pacific and Atlantic on the left, Indian Ocean under Asia, land across the north — but the continents are blobs: the Americas one mass, Africa + Eurasia another, the Atlantic too narrow, Australia a smear. The probability map has vertical stripes that line up with lines of longitude, suggesting coordinate confusion rather than geographic uncertainty. **Antarctica is mostly called water.**

**The colour-named physical map is the most map-like picture so far.** Asked "what colour is this on a classic physical atlas", Jev draws recognisable North America, South America, Africa, Eurasia and Australia — cleaner coastlines than its own land/water Noul map. But it misses Antarctica completely (all dark blue). The terrain-named version gets Antarctica right (a solid "high mountains / ice plateau" band) but blurs the continents and calls most deep ocean "Ocean" (200–3,000 m) rather than "Deep ocean".

**Political: Jev knows Antarctica after all.** Antarctica: 100% of its land points correct in the political map, while the land/water Noul calls most of it water. Same model, same coordinates, different question → different "knowledge".

**Political: oceans get claimed by the nearest country.** Of ocean points wrongly given a country: Antarctica 331, USA 121, Australia 66, Russia 64, Greenland 56, Canada 49, Japan 41, French Polynesia 36, American Samoa 31. The single "Ocean" option competes against 242 named places and loses. Scoring political on land points only was the right call.

**Per-country (5°):** USA 99%, Australia 100%, Greenland 100%, India 100%, Canada 87%, China 70%, Brazil 75%, Russia only 50% (confused with Mongolia, Kazakhstan, Japan), Iran 29%, Chad 0% (→ Libya), Mali 0% (→ Mauritania, Niger). Africa and the Middle East are where it breaks down — many mid-sized countries close together.

## Phase 3 — 2° grid (16,200 points), $1.60 — the headline

| Map | Result |
|---|---|
| Land/water (Noul) | **78.5%** at p ≥ 0.5; **85.3%** at the 0.70 threshold frozen from the 10° grid. Land recall 92%, water recall 73%. |
| Physical, terrain names | 49.8% exact band, 83.5% within one band, 86.0% land-vs-water |
| Physical, colour names | 56.7% exact band, 77.4% within one band, 84.7% land-vs-water |
| Political | **75.3%** of land points get the right country, 92.6% have it in the top 3. Ocean recall 33%. |

Cost breakdown: land $0.03, physical terrain $0.18, physical colour $0.07, political $1.33 (31.7M tokens — the 243-option list again). Political took 11 minutes, held back by the 100k tokens/second limit; everything else under a minute.

**Where this puts Jev against the Claudes:** 78.5% sits between Sonnet 4.5 (60.5%) and Haiku 4.5 (81.3%). With the tuned threshold (85.3%) it sits between Opus 4.5 (82.6%) and Sonnet 4.6 (89.1%). Far from the top models (Opus 5.5 at 99.0%), but Jev is a small, fast decision model and the whole map cost 2.5 cents.

**At 2° the land map is recognisable.** Americas, Africa, Eurasia all there. Australia weak. The probability map is the more honest picture: bright cores where Jev is sure, grey fog toward coasts.

**Antarctica stripes explained.** In the Noul map, Antarctica breaks into horizontal stripes. Row by row, Jev's mean p(land) south of 71°S sits at 0.43–0.64 — a coin flip — so small row-to-row shifts flip whole rows between land and water. Meanwhile:
- Political: Antarctica 100% correct (1,515 points).
- Continent question (phase 5): Antarctica 99.9% correct.
- Physical terrain: a clean "high mountains / ice plateau" band.

So Jev *knows* where Antarctica is; the "is this location on land" framing just doesn't reach that knowledge. Probably the ice: "on land, not in an ocean, sea or lake" is ambiguous for an ice sheet.

**The high Arctic goes the other way.** At 79–81°N Jev predicts land for 43–78% of points where the truth is 22%. Sea ice again, presumably.

**Political, per country (2°).** Antarctica 100%, Greenland 100%, Australia 99%, Libya 97%, India 96%, USA 95%, Canada 93%, Peru 93%; Russia 63% (→ Kazakhstan, Mongolia, Japan), Iran 39%, Ethiopia 30%.

**Three countries that Jev never picks anywhere on Earth.** Mali, Chad and Zambia score 0% — and across all 16,200 points Jev *never* chooses them, even though Zambia is in the top 10 for 2,807 points and Chad for 316. Same for Togo and Laos. They are permanent runners-up. Mali's points go to Mauritania/Niger/Algeria, Chad's to Libya/Sudan/Cameroon. Hypothesis (unverified): in a 243-way Choice some options are systematically suppressed; short names? (Peru and Cuba are short and do get picked, so not simply length.)

**Confidence works.** Political accuracy on land by confidence quintile: 46% → 68% → 93% → 99% → 100%. Gating at confidence ≥ 0.9 keeps 51% of land points at 98.3% accuracy; ≥ 0.7 keeps 69% at 92.8%. This is the "confidence-gated routing" pattern from the Jev docs, and it holds up here.

## Phase 5 — exploratory: other ways to ask land/water (2°), $0.14

Done after the headline was frozen, so these are post-hoc and labelled as such. Every Choice returns probabilities for all options, so "probability of land" can be read off several different questions:

| How land/water was obtained | Accuracy at 0.5 |
|---|---|
| Noul "this location is on land" (headline) | 78.5% |
| Continent-or-ocean Choice, P(any continent) | 77.2% |
| Land-vs-water two-option Choice, P(land) | 84.4% |
| Physical (colour names), P(land colours) | 84.6% |
| Average of Noul + both physical | 85.7% |
| **Physical (terrain names), P(land bands)** | **86.5%** |

- Asking about terrain gives a better land/water map than asking about land/water. Asking indirectly beats asking directly.
- The same question as a two-option Choice beats the Noul by ~6 points at 0.5 — mostly calibration (the Noul leans "land"); the docs warn that Noul and Choice answers are not interchangeable, and here that shows.

**The continent map is the best picture of Jev's "mental map".** Asked "which continent or ocean is this location in?", Jev draws the world as schematic blocks: Africa a rectangle, South America too big and pushed east, Australia a large square, Europe a small box, Antarctica a solid band. It gets the continent right for 92.2% of land points (Antarctica 99.9%, South America 98.3%, Oceania 93.9%, Africa 93.4%, Asia 93.2%, North America 88.4%, Europe 72.2%). But the coastlines are wrong, so land/water from this question is only 77%.

## Next, after Jev

George's idea: turn this into a small map benchmark for decision models of the same kind — Cloudflare's Clef (https://blog.cloudflare.com/clef-decision-models/), laya-typed-decisions, and OpenAI's announced research equivalent. The harness already separates grid / truth / prompts / runner / scoring, so a new model needs a runner adapter. Not started.

## Phase 4 — 1° grid (64,800 points), $1.69

Political skipped at 1° (the 243-option list would make it ~$5 and ~45 minutes for little new). One request (100 points) failed with a 520 and was filled on a re-run.

| How land/water was obtained | 2° | 1° |
|---|---|---|
| Noul, p ≥ 0.5 | 78.5% | 75.4% |
| Noul, best threshold | 85.4% | 84.7% (at 0.70 — the same threshold frozen from the 10° grid) |
| Land-vs-water Choice | 84.4% | 82.5% |
| Physical colour, P(land) | 84.6% | 83.2% |
| Continent Choice, P(land) | 77.2% | 75.3% |
| Physical terrain, P(land) | 86.5% | 86.0% |

A finer grid adds no detail. Accuracy holds or drops slightly; the maps look the same, just smoother. Jev's knowledge has a resolution of several degrees, so more points only sample the same blur more finely. (The Claude chart tells the opposite story for the top models, whose maps get sharper with more points.)

**The X at 0°N 0°E.** The 1° probability maps show a faint X centred on the Gulf of Guinea: two diagonal lines where |latitude| = |longitude| (`12.5°N, 12.5°E`, `20.5°S, 20.5°E`, ...). On African land points within 35° of the origin, mean p(land) by distance from the diagonal:

| abs(lat) − abs(lon) | Noul p(land) | Terrain P(land) |
|---|---|---|
| 0 (on the diagonal) | 0.74 | 0.64 |
| 1° | 0.76 | 0.62 |
| 2° | 0.79 | 0.64 |
| 3° | 0.80 | 0.68 |
| 4° | 0.80 | 0.70 |

About 0.06 lower when the two numbers are the same. A small effect, but a clean example of the docs' warning about numbers: the answer depends on how the coordinate *looks*, not only on where it is. The vertical/horizontal streaks in every probability map (whole rows and columns slightly lighter or darker) are probably the same thing: some latitude and longitude values carry a bias of their own.

## Totals

All Jev calls so far: phase 0 ≈ $0.01, phase 1 $0.64, phase 2 $0.26, phase 3 $1.60, phase 5 $0.14, phase 4 $1.69 — about **$4.35** in total, under the $5.50 estimate for phases 0–4 including the 1° grid.

## Write-up

HTML write-up built from the metrics files by `report/build.py` (template in `report/template.html`), published as a private page: https://claude.ai/artifact/51fsFbd9tDUHf1AFsdJZGj

What it includes: a swipe comparison of Jev's 2° land map against the truth; Jev's score among the 12 Claudes; the probability and error maps; calibration; five ways of asking land/water with a switchable map; physical, continent and political maps; per-country tables, countries Jev never picks, the confidence trade-off; the 1° grid and the diagonal artifact; prompt tuning; caveats.

**Calibration detail for the post:** above p = 0.7 Jev's land probability is close to calibrated (0.75 → 72% land, 0.84 → 82%, 0.92 → 91%). Between 0.3 and 0.7 it runs high: p ≈ 0.45 → 14% land, p ≈ 0.55 → 25%, p ≈ 0.65 → 41%. That is why 0.70 beats 0.5 as a cutoff.

**Candidate storylines for the blog post:**
1. Jev lands between Sonnet 4.5 and Haiku 4.5 (or between Opus 4.5 and Sonnet 4.6 with the tuned cutoff), and the land map cost 2.5 cents — headline comparison.
2. "Ask indirectly": the terrain question gives a better land map than the land question; knowledge about Antarctica shows up under "which country" but not under "is this land".
3. Jev's mental map: the continent blocks image.
4. Confidence works: ≥ 0.9 confidence → 98% right on half the land.
5. Jaggedness: countries that never win, the X at 0°N 0°E, row/column streaks.

## Prior work, and the original wording

The Claude chart is from @celestepoasts (Sep 24, 2026), amplified by Karpathy (Oct 2, 2026). The eval itself is from @arithmoquine, "How Does A Blind Model See The Earth?" (outsidetext.substack.com, Aug 2025): dozens of open and closed LLMs, P(Land) from the logprobs of 'Land' vs 'Water', 2° grid, no numeric scores. On Sep 24, 2026 the same author posted Jev maps (land probability, continents, 178-way countries at 1°), qualitatively, without scores. So Jev maps themselves are not new. Scores, calibration, wording sensitivity and a cross-model comparison of decision models are.

Original prompt: "If this location is over land, say 'Land'. If this location is over water, say 'Water'. Do not say anything else. x° S, y° W". Their Jev land map looked sharper than ours, with Antarctica as land, so I re-ran 2° with that wording:

| Wording / type / where the coordinate goes | p ≥ 0.5 | p ≥ 0.7 | best | Antarctica mean p | cost |
|---|---|---|---|---|---|
| Original, Choice Land/Water, coordinate as state | 83.3% | 85.7% | 86.0% | 0.64 | $0.21 |
| Original, Choice Land/Water, coordinate in question | 84.1% | 85.9% | 85.9% | 0.60 | $0.04 |
| "over land", Noul, coordinate as state | 78.9% | 85.2% | 85.3% | 0.50 | $0.19 |
| "over land", Noul, coordinate in question | 79.8% | 85.4% | 85.4% | 0.34 | $0.02 |
| Ours: "on land, not in an ocean, sea or lake", Noul (headline) | 78.5% | 85.3% | 85.4% | ~0.5 | $0.03 |

- At the best cutoff every variant lands at 85–86%. Wording barely matters for ranking; **question type sets the calibration**: Choice is roughly calibrated at 0.5, Noul leans land and needs ~0.7.
- Fair headline for comparison with the Claudes: **84.1%** (original wording, Choice, p ≥ 0.5), between Opus 4.5 (82.6%) and Sonnet 4.6 (89.1%).
- arithmoquine's sharper-looking map is probably a colour scale (blue–green saturates around 0.4–0.6) plus the Choice calibration, not better knowledge.

Clef check (Oct 2): works through the wrangler login, same request/response format as Jev. $0.24/M input tokens, ≤ 64 questions per request. Laya typed-decisions: ModernBERT-large, 843 MB, 1,024-token context, runs locally.

## Cross-model benchmark (Oct 2, afternoon)

Models: Jev 1.13 (TypeSafe API), Clef and Clef-flash (Cloudflare Workers AI), Laya (open weights, run on a Modal L4 GPU: typed-decisions, english, multilingual checkpoints). Same 2° grid, same prompts, coordinate in the question unless noted. Laya also run with the coordinate as the state (its batch API is built for that).

Implementation notes:
- Clef takes the same body as Jev, but question keys must match `^[A-Za-z0-9_.-]{1,100}$` (the point ids had `+`). Max 64 questions per request. Zero failures across ~2,000 requests.
- Clef auth via the wrangler OAuth token, refreshed by `wrangler whoami` before expiry.
- Laya on Modal: `laya.load(repo, subfolder=...)`; the PyPI release does not resolve short names like "typed-decisions". `predict_batch` does 16,200 states in 5–55 s on an L4. The political map (243 options) does not fit Laya's head budget (options beyond ~20 get truncated), so no Laya political run.
- Clef's tokenizer counts the 243-country list at about twice Jev's tokens: political cost $14.62 per Clef model vs $1.33 for Jev.

**Land/water, 2° (P(land) at 0.5 / AUC):**
| | “Land or Water?” Choice | best question type | AUC range over 7 question types |
|---|---|---|---|
| Jev | 84.1% / 0.926 | terrain 86.5% / 0.929 | 0.899–0.931 |
| Clef | 82.9% / 0.867 | “…is over land” 84.0% | 0.854–0.887 |
| Clef-flash | 73.3% / 0.746 | “…is over land” 75.7% | 0.713–0.775 |
| Laya typed | 29.0% / 0.689 | — | 0.42–0.69 |
| always "water" | 71.0% | | 0.5 |

- Jev ranks best (AUC 0.93), but its accuracy depends on how it is asked (77–87% at 0.5) because calibration shifts by question type. Clef is consistent: 80–84% for every question type, best threshold always ~0.5–0.6.
- Clef-flash is close to the water baseline. Laya is at or below it: no usable geography from coordinates in any checkpoint or layout.
- Continent of land points from coordinates: Jev 92.2%, Clef 70.8%, Clef-flash 70.4%, Laya 0% (always picks an ocean).
- Political, land points: Jev 75.3% (top-3 92.6%), Clef 58.3% (83.6%), Clef-flash 38.2% (60.6%). Clef calls ocean "Ocean" far more often (67.6% vs Jev 33.1%).
- Countries never chosen anywhere: Jev 27, Clef 48, Clef-flash 81.

**Names, not numbers.** 500 largest cities and all countries, asked by name (scripts/names.py):
| | city→continent | country→continent | north? | east of Greenwich? | lat band (6) | lon band (6) |
|---|---|---|---|---|---|---|
| Jev | 98.8% | 98.7% | 98.4% | 80.6% | 93.6% | 80.6% |
| Clef | 98.2% | 98.7% | 98.0% | 98.4% | 95.2% | 89.2% |
| Clef-flash | 97.0% | 97.4% | 94.4% | 76.4% | 78.4% | 64.0% |
| Laya typed | 45.0% | 32.6% | 17.0% | 52.2% | 3.2% | 28.2% |
| Laya english | 44.0% | 25.3% | 18.0% | 58.6% | 7.8% | 28.8% |
| Laya multilingual | 61.4% | 68.2% | 52.2% | 51.4% | 1.4% | 8.6% |
| majority answer | 46.6% | | 85.6% | 69.8% | 48.6% | 32.4% |

- Jev and Clef know geography by name almost perfectly. The gap between names (98%) and coordinates (Clef 71% continent) is the coordinate reading, not missing knowledge — especially for Clef.
- Laya does not know geography by name either. Its checkpoints are 322–421M-parameter encoders trained for text decisions; world knowledge is not in them.

**Determinism.** Same 648 “Land or Water?” questions, sent twice: Jev mean |Δp| 0.022, max 0.20, 17/648 answers flipped (2.6%). Clef and Clef-flash: identical to the last digit.

## Blog post draft (Oct 2, evening)

Title (George's): "How well do decision models know geography?" Built by `blog/build.py` from `results/metrics/bench_2deg.json` and `names.json`; maps from `scripts/bench_figures.py`. Published privately: https://claude.ai/artifact/N97JLSe5gNCKinS5ZVeEiF

Sections: summary, setup, land/water (sheet of maps, bar chart among the Claudes, probability maps), seven ways to ask (heat table), calibration (curves + ECE/Brier), names vs numbers (dumbbell + table), continents, countries (maps, confidence–coverage curve, per-country), physical map, cost/speed/determinism, method notes.

Fixes made while checking the draft against the data:
- Laya-multilingual is above baseline on continents by name (61–68% vs 47%); the first draft said all Laya checkpoints were at or below baseline.
- Clef's political confidence values are compressed (max ≈ 0.24), so fixed thresholds gave a three-point curve. Switched to ranking answers by confidence and stepping through coverage. Most confident 50% of land points: Jev ≈ 95–96% right, Clef 76%, Clef-flash 60%.

Other observations for the post:
- Clef's probability map has horizontal streaks (whole latitude rows shifted); Clef-flash has diagonal streaks. Tried to quantify streakiness (row/column jitter of residuals, neighbour differences) — the numbers did not separate the models cleanly at 2°, so the post describes the maps instead.
- Clef's continent map at 2°: same block shapes as Jev, noisier (70.8% vs 92.2%).
- Cost totals: Jev ≈ $5, Clef + Clef-flash ≈ $37.5 (most of it the two country maps at $14.62 each). Laya on Modal: a few minutes of L4 time.

Housekeeping: all Modal apps were ephemeral (`app.run()`), all stopped; the HF cache volume `jevmap-hf-cache` was deleted afterwards. Nothing left running.

Open items:
- Prompts were tuned on Jev only. A fairer comparison would tune format and wording per model on the 10° grid.
- OpenAI Decisions API: not yet published.
- Laya political map would need a two-step question (continent, then country) because of its option budget.

## Per-model prompt check for Clef (10° grid, “Land or Water?”)

| | format | coordinate in question: acc / AUC | coordinate as state: acc / AUC |
|---|---|---|---|
| Clef | decimal | 78.3% / 0.835 | 77.6% / 0.797 |
| Clef | hemi | 77.7% / 0.884 | **82.4% / 0.906** |
| Clef | words | 77.0% / 0.853 | 81.5% / 0.888 |
| Clef-flash | decimal | 66.5% / 0.631 | 76.8% / 0.784 |
| Clef-flash | hemi | 71.2% / 0.801 | **81.9% / 0.847** |
| Clef-flash | words | 69.7% / 0.729 | 74.8% / 0.775 |

Hemisphere letters win for Clef too. Unlike Jev (where layout only shifted calibration), both Clefs rank better with the coordinate as the whole state, one point per request. Clef-flash gains most. Running 2° in that layout for both Clefs so each model is reported in its better setting as well.

## Per-model layout at 2°, mirror test (Oct 2, evening)

“Land or Water?”, coordinate as the whole state (one point per request), 2°:
| | in question: acc / AUC / ECE | as state: acc / AUC / ECE |
|---|---|---|
| Jev | 84.1% / 0.926 / 0.094 | 83.3% / 0.926 / 0.133 |
| Clef | 82.9% / 0.867 / 0.076 | 83.8% / 0.901 / 0.030 |
| Clef-flash | 73.3% / 0.746 / 0.088 | 80.7% / 0.844 / 0.031 |
| Laya typed | 29.0% / 0.689 / 0.334 | 51.3% / 0.632 / 0.221 |

Cost: $0.56 per Clef model (16,200 requests, ~7 minutes each at ~37 req/s, no failures). In each model's better setting: Jev 84.1%, Clef 83.8%, Clef-flash 80.7%. Jev still ranks best (AUC 0.93 vs 0.90); both Clefs are far better calibrated (ECE 0.03).

The state-layout Clef maps have vertical streaks instead of horizontal ones, and the same faint X through 0°N 0°E that Jev shows at 1°. Clef-flash looks mirrored around Greenwich.

Mirror test (correlation of the P(land) map with its own mirror image; best layout):
| | east–west | north–south |
|---|---|---|
| real world | 0.30 | −0.18 |
| Jev | 0.35 | 0.00 |
| Clef | 0.42 | −0.01 |
| Clef-flash | 0.47 | 0.49 |

All models are more E/W-symmetric than the Earth; Clef-flash is close to symmetric N/S too — it partly ignores the hemisphere letters. Consistent with the names test (Clef-flash “east of Greenwich” 76%).

Blog draft updated to version 2 with these (same URL). Remaining caveat: continent, country and physical sections use the coordinate-in-question layout for every model, which understates Clef-flash in particular.

## Laya sanity check, and a Modal GPU limit (Oct 2, evening)

George asked whether Laya was broken. Check (`scripts/laya_sanity.py`): its own README example and questions whose answer is in the text.
- README ticket: all three checkpoints pick "billing" (0.81 / 0.99 / 1.00). churn_risk 0.77 / 0.88 / 0.04 (multilingual misses it).
- "The point is in the Sahara desert, in southern Algeria" → Land, Africa (all three). "...middle of the Pacific Ocean..." → Water (all three). "Our office is in Lima, Peru" → South America; "Nairobi, Kenya" → Africa.

So the pipeline is fine and Laya reads text correctly. It fails only when the answer needs world knowledge (a coordinate, or a bare city name like "Lagos"). Laya is a text classifier; Jev and Clef carry world knowledge.

Modal: George got a "workspace reached the limit of 10 GPUs" email from Modal. Cause: `laya_bench.py` used `.map()` over chunks, which fans out across containers. Fixed: `max_containers=1`, `scaledown_window=60` on the Laya class. Checked: no active containers, no running apps; cache volume deleted again (the sanity run had re-created it).

## Clef in its better layout for every section (Oct 2, night)

Re-ran continent, country, terrain and atlas colour for Clef and Clef-flash with the coordinate as the state (one point per request). No failures. Cost: country maps $14.87 each, terrain $1.42, colour $0.89 per model.

| | Clef: question → state | Clef-flash: question → state |
|---|---|---|
| continent (land) | 70.8% → 73.4% | 70.4% → 89.5% |
| ocean points called an ocean (continent question) | – → 90.0% | – → 63.8% (Jev 69.6%) |
| country (land) | 58.3% → 63.3% | 38.2% → 49.6% |
| country top-3 | 83.6% → 89.5% | 60.6% → 70.4% |
| terrain band exact | 50.8% → 58.8% | 29.8% → 50.4% |
| atlas colour exact | 52.3% → 54.7% | 31.8% → 39.2% |

- Clef now has the most exact terrain bands of any model (58.8% vs Jev 49.8%); Jev is still best within one band (83.5% vs 77.6%).
- Clef-flash's continent score jumps to 89.5%, partly by drawing oversized continents that cover ocean (only 63.8% of ocean points called ocean). Clef is the opposite: cautious on land, 90% right on ocean.
- Jev still leads on countries (75.3%) and continents from coordinates (92.2%).
- Clef's political confidence in the state layout reaches 0.75 (median 0.12; Jev median 0.62). The draft-3 sentence "never exceeds 0.25" was true only for the question layout; fixed.
- Laya's continent answers are only "Pacific Ocean" (7,568), "Oceania" (4,902), "Atlantic Ocean" (3,593), "Southern Ocean", "Arctic Ocean" — the earlier sentence "picks an ocean for every point" was wrong (Oceania is a continent option); fixed.

Throughput in this layout: ~10 requests/s per Clef model at concurrency 16; a country request (243 options, 3,824 Clef tokens) takes ~0.8–0.9 s.

Blog draft 4 published (same URL). Final API spend: ≈ $80 (Jev $4.81, Clef ≈ $38, Clef-flash ≈ $38), plus a few minutes of L4 time on Modal.

Repo goes public as move38studios/decision-map-bench (MIT, fresh single-commit history, journal included). Created private first; made public when the post is published.

## Laya label, social cards (Oct 2, night)

Laya's 29.0% on land/water is not anti-knowledge: its P(Land) stays in 0.57–0.67 at every point, so it says Land everywhere and scores the land share of the globe. AUC 0.69 is below a latitude-only predictor (0.75); with row means removed it is 0.63, so there is a faint longitude signal that never moves an answer. Bar chart and map sheet now label it "says Land everywhere".

Social cards (1200×630, IBM Plex Sans, `scripts/og_images.py`): `og_landwater` (truth + four P(Land) maps), `og_continents` (truth + Jev, Clef, Clef-flash continent blocks), `og_names` (continent from a city name vs from a coordinate). Copied into `blog/img/`.
