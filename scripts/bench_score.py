"""Score every model on every question at 2 degrees; writes results/metrics/bench_2deg.json."""

import json

import numpy as np

from jevmap import bench, geo, runner, score

GRID = geo.Grid(2)
METRICS = geo.ROOT / "results" / "metrics"

# (model key, backend, layout) — Laya is scored in both layouts, the others with the coordinate in the question.
ENTRIES = [
    ("jev", "jev", "question"),
    ("clef", "clef", "question"),
    ("clef-flash", "clef-flash", "question"),
    ("laya-typed", "laya-typed", "question"),
    ("laya-typed-state", "laya-typed", "state"),
    ("clef-state", "clef", "state"),
    ("clef-flash-state", "clef-flash", "state"),
]


def exists(name: str) -> bool:
    """Only complete runs are scored."""
    return runner.has(name) and len(runner.load(name)) == GRID.shape[0] * GRID.shape[1]


def main() -> dict:
    t = geo.truth(GRID)
    w = GRID.weights
    out: dict = {"water_baseline": bench.water_baseline(GRID), "models": {}}
    for key, backend, layout in ENTRIES:
        m: dict = {"land": {}, "cost_usd": 0.0, "tokens": 0}
        for exp in bench.LAND_SOURCES:
            name = bench.run_name(backend, exp, layout)
            if not exists(name):
                continue
            p = bench.p_land(name, exp, GRID)
            m["land"][exp] = bench.land_metrics(p, GRID)
            u = runner.usage(name)
            m["cost_usd"] += u["cost_usd"]
            m["tokens"] += u["input_tokens"]
        # Continent of land points (coordinate -> continent).
        name = bench.run_name(backend, "continent", layout)
        if exists(name):
            recs = runner.load(name)
            pred = np.full(GRID.shape, "", dtype=object)
            for i, lat in enumerate(GRID.lats):
                for j, lon in enumerate(GRID.lons):
                    r = recs.get(geo.point_id(lat, lon))
                    if r:
                        pred[i, j] = r["choice"]
            true_c = np.array([[geo.continent_of(c, lon) for c, lon in zip(row, GRID.lons)] for row in t["country"]], dtype=object)
            mask = true_c != ""
            m["continent_accuracy"] = float(((pred == true_c) * w)[mask].sum() / w[mask].sum())
            sea = t["country"] == geo.OCEAN
            from jevmap import prompts as _p
            m["continent_ocean_recall"] = float((np.isin(pred, _p.OCEANS) * w)[sea].sum() / w[sea].sum())
            m["continent_by"] = {
                c: float(((pred == true_c) * w)[true_c == c].sum() / w[true_c == c].sum()) for c in geo.CONTINENTS
            }
        # Physical bands.
        for v in ("terrain", "colour"):
            name = bench.run_name(backend, f"physical_{v}", layout)
            if exists(name):
                s = score.score(name, GRID, f"physical_{v}")
                m[f"physical_{v}"] = {k: s[k] for k in ("accuracy", "within_one", "land_only_accuracy", "water_only_accuracy")}
        # Political.
        name = bench.run_name(backend, "political", layout)
        if exists(name):
            s = score.score(name, GRID, "political")
            m["political"] = {k: s[k] for k in ("accuracy_land", "top3_land", "ocean_recall", "accuracy_all")}
            m["cost_usd"] += runner.usage(name)["cost_usd"]
            m["tokens"] += runner.usage(name)["input_tokens"]
            g = score.to_grid(name, GRID, "political")
            on_land = (t["country"] != geo.OCEAN) & g["have"]
            correct = g["pred"] == t["country"]
            curve = []
            conf = np.where(on_land, np.nan_to_num(g["conf"], nan=-1.0), -1.0)
            order = np.argsort(-conf, axis=None)
            n_land = int(on_land.sum())
            wf, cf = w.ravel()[order][:n_land], correct.ravel()[order][:n_land]
            for q in np.arange(0.05, 1.0001, 0.05):
                k = max(1, int(round(q * n_land)))
                curve.append({"coverage": float(wf[:k].sum() / wf.sum()), "accuracy": float((cf[:k] * wf[:k]).sum() / wf[:k].sum()),
                              "confidence_at": float(np.sort(conf.ravel())[::-1][k - 1])})
            m["political"]["confidence_curve"] = curve
            pcs = score.per_country(name, GRID)
            m["political"]["per_country"] = pcs
            recs = runner.load(name)
            chosen = {r["choice"] for r in recs.values()}
            present = {r["country"] for r in pcs}
            m["political"]["never_chosen"] = sorted(present - chosen)
        out["models"][key] = m
    # "Land or Water?" with the coordinate as the state (one point per request), for every model that has it.
    out["state_layout"] = {}
    for key, name in [("jev", "g2_orig_choice_state"), ("clef", "clef_g2_orig_choice_state"),
                      ("clef-flash", "clef-flash_g2_orig_choice_state"), ("laya-typed", "laya-typed_g2_orig_choice_state")]:
        if exists(name):
            out["state_layout"][key] = bench.land_metrics(bench.p_land(name, "orig_choice", GRID), GRID)
            out["state_layout"][key]["cost_usd"] = runner.usage(name)["cost_usd"]
    (METRICS / "bench_2deg.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    out = main()
    print(f"water baseline {out['water_baseline']:.1%}")
    for k, m in out["models"].items():
        print(f"\n== {k}  cost ${m['cost_usd']:.2f}")
        for exp, s in m["land"].items():
            print(f"  {exp:17} acc={s['accuracy']:.1%} best={s['best_accuracy']:.1%}@{s['best_threshold']} auc={s['auc']:.3f} ece={s['ece']:.3f} brier={s['brier']:.3f}")
        if "continent_accuracy" in m:
            print(f"  continent on land: {m['continent_accuracy']:.1%}")
        for v in ("terrain", "colour"):
            if f"physical_{v}" in m:
                print(f"  physical_{v}: " + ", ".join(f"{a}={b:.1%}" for a, b in m[f'physical_{v}'].items()))
        if "political" in m:
            p = m["political"]
            print(f"  political land={p['accuracy_land']:.1%} top3={p['top3_land']:.1%} ocean={p['ocean_recall']:.1%} never_chosen={len(p['never_chosen'])}")
