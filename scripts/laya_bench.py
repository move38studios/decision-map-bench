"""Run the benchmark suite on a Laya checkpoint (on Modal) and cache answers like the other backends.

Usage: uv run python -m scripts.laya_bench laya-typed [step] [layout] [experiments...]
  backend: laya-english | laya-multilingual | laya-typed
  layout:  question (default; coordinate in each question, 64 per request) | state (coordinate as the state)
"""

import json
import sys
import time
from dataclasses import asdict

import modal

from jevmap import backends, geo, prompts, runner
from jevmap.runner import RunSpec
from scripts.bench import SUITE
from scripts.modal_laya import Laya, app

CHECKPOINT = {"laya-english": "english", "laya-multilingual": "multilingual", "laya-typed": "typed-decisions"}


def dump(questions: dict) -> dict:
    return {k: q.model_dump(mode="json") for k, q in questions.items()}


def main(backend: str, step: float, layout: str, exps: list[str]) -> None:
    grid = geo.Grid(step)
    pts = grid.points()
    lat_lon = {geo.point_id(*p): p for p in pts}
    model = Laya(checkpoint=CHECKPOINT[backend])
    for exp in exps:
        suffix = "" if layout == "question" else "_state"
        spec = RunSpec(f"{backend}_g{step:g}_{exp}{suffix}", exp, layout=layout, batch=64, backend=backend)
        out_path, usage_path, meta_path = runner.paths(spec.name)
        runner.RAW.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(asdict(spec), indent=2))
        done = set(runner.load(spec.name))
        todo = [p for p in pts if geo.point_id(*p) not in done]
        print(f"[{spec.name}] {len(todo)} points to ask")
        if not todo:
            continue
        reqs = runner.build_requests(spec, todo)
        top_k = 10 if exp == "political" else None
        t0 = time.monotonic()
        results: list[tuple[list[str], dict, dict]] = []  # (ids, question keys -> answer)
        if layout == "state":
            qs = dump(reqs[0][1])
            states = [r[0] for r in reqs]
            ids = [r[2][0] for r in reqs]
            chunk = 2000
            parts = model.same_questions.map(
                [states[i : i + chunk] for i in range(0, len(states), chunk)], kwargs={"questions": qs}
            )
            k = 0
            for part in parts:
                for res in part:
                    results.append(([ids[k]], ["q"], res["answers"]))
                    k += 1
        else:
            payload = [(state, dump(qs)) for state, qs, _ in reqs]
            chunk = 20
            parts = model.one_each.map([payload[i : i + chunk] for i in range(0, len(payload), chunk)])
            k = 0
            for part in parts:
                for res in part:
                    _, qs, ids = reqs[k]
                    results.append((ids, list(qs), res["answers"]))
                    k += 1
        dt = time.monotonic() - t0
        with open(out_path, "a") as out:
            for ids, keys, answers in results:
                for key, pid in zip(keys, ids):
                    ans = answers.get(key)
                    if ans is None:
                        continue
                    lat, lon = lat_lon[pid]
                    rec = {"id": pid, "lat": lat, "lon": lon, "model": backend, **runner._record(backends._ns(ans), top_k)}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with open(usage_path, "a") as u:
            u.write(json.dumps({"points": len(todo), "input_tokens": 0, "output_tokens": 0, "seconds": dt}) + "\n")
        print(f"[{spec.name}] done in {dt:.0f}s")


if __name__ == "__main__":
    backend = sys.argv[1]
    step = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    layout = sys.argv[3] if len(sys.argv) > 3 else "question"
    exps = sys.argv[4:] or [e for e in SUITE if e != "political"]
    with modal.enable_output(), app.run():
        main(backend, step, layout, exps)
