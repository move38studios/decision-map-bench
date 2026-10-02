"""Run an experiment over a set of points against Jev, caching every answer to JSONL."""

import asyncio
import gzip
import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeError

from jevmap import backends, geo, prompts

load_dotenv()

RAW = geo.ROOT / "results" / "raw"
PRICE_PER_MTOK = 0.042

EXPERIMENTS = ("land", "physical_terrain", "physical_colour", "political", "continent", "land_choice", "orig_choice", "orig_noul")


@dataclass(frozen=True)
class RunSpec:
    name: str
    experiment: str
    coord_style: str = "hemi"
    layout: str = "question"  # "state" or "question"
    model: str = "jev-latest"
    batch: int = 100  # points per request when layout == "question"
    backend: str = "jev"  # "jev", "clef", "clef-flash"; Laya runs through scripts/modal_laya.py

    def __post_init__(self) -> None:
        assert self.experiment in EXPERIMENTS, self.experiment
        assert self.layout in ("state", "question"), self.layout


def _question(spec: RunSpec, coord: str | None):
    exp = spec.experiment
    if exp == "land":
        if coord is None:
            return prompts.Noul(instructions=prompts.LAND_QUESTION_GENERIC)
        return prompts.land_question_point(coord)
    if exp.startswith("physical_"):
        return prompts.physical_question(exp.removeprefix("physical_"), coord)
    if exp == "continent":
        return prompts.continent_question(coord)
    if exp == "land_choice":
        return prompts.land_choice_question(coord)
    if exp == "orig_choice":
        return prompts.orig_choice_question(coord)
    if exp == "orig_noul":
        return prompts.orig_noul_question(coord)
    return prompts.political_question(coord)


def build_requests(spec: RunSpec, points: list[tuple[float, float]]) -> list[tuple[object, dict, list[str]]]:
    """(state, questions, point ids) per request."""
    reqs = []
    if spec.layout == "state":
        q = _question(spec, None)
        for lat, lon in points:
            coord = prompts.fmt_coord(lat, lon, spec.coord_style)
            state = coord if spec.experiment.startswith("orig_") else prompts.land_state_point(coord)
            reqs.append((state, {"q": q}, [geo.point_id(lat, lon)]))
        return reqs
    for i in range(0, len(points), spec.batch):
        chunk = points[i : i + spec.batch]
        qs, ids = {}, []
        for k, (lat, lon) in enumerate(chunk):
            qs[f"q{k}"] = _question(spec, prompts.fmt_coord(lat, lon, spec.coord_style))
            ids.append(geo.point_id(lat, lon))
        reqs.append((prompts.LAND_STATE_GENERIC, qs, ids))
    return reqs


def _record(answer, top_k: int | None) -> dict:
    if answer.type == "noul":
        return {"p": answer.noul}
    probs = dict(sorted(answer.probabilities.items(), key=lambda kv: -kv[1]))
    if top_k is not None:
        probs = dict(list(probs.items())[:top_k])
    return {"choice": answer.choice, "confidence": answer.confidence, "probs": probs}


class Limiter:
    """Sliding one-second window over request count and estimated input tokens."""

    def __init__(self, rps: float, tps: float) -> None:
        self.rps, self.tps = rps, tps
        self.window: deque[tuple[float, int]] = deque()
        self.lock = asyncio.Lock()

    async def acquire(self, tokens: int) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.window and now - self.window[0][0] > 1.0:
                    self.window.popleft()
                used = sum(t for _, t in self.window)
                if len(self.window) < self.rps and (used + tokens <= self.tps or not self.window):
                    self.window.append((now, tokens))
                    return
                await asyncio.sleep(0.02)


def paths(name: str) -> tuple[Path, Path, Path]:
    return RAW / f"{name}.jsonl", RAW / f"{name}.usage.jsonl", RAW / f"{name}.meta.json"


def has(name: str) -> bool:
    out_path = paths(name)[0]
    return out_path.exists() or out_path.with_suffix(".jsonl.gz").exists()


def load(name: str) -> dict[str, dict]:
    """Cached answers for a run. Large runs are stored gzipped (.jsonl.gz); new answers append to .jsonl."""
    out_path, _, _ = paths(name)
    out = {}
    gz = out_path.with_suffix(".jsonl.gz")
    texts = []
    if gz.exists():
        texts.append(gzip.decompress(gz.read_bytes()).decode())
    if out_path.exists():
        texts.append(out_path.read_text())
    for text in texts:
        for line in text.splitlines():
            rec = json.loads(line)
            out[rec["id"]] = rec
    return out


def usage(name: str) -> dict:
    _, usage_path, meta_path = paths(name)
    backend = json.loads(meta_path.read_text()).get("backend", "jev") if meta_path.exists() else "jev"
    price = backends.PRICE_PER_MTOK.get(backend, 0.0)
    rows = [json.loads(l) for l in usage_path.read_text().splitlines()] if usage_path.exists() else []
    tokens = sum(r["input_tokens"] or 0 for r in rows)
    return {
        "requests": len(rows),
        "input_tokens": tokens,
        "cost_usd": tokens / 1e6 * price,
        "seconds": sum(r["seconds"] for r in rows),
    }


async def run(
    spec: RunSpec,
    points: list[tuple[float, float]],
    *,
    concurrency: int = 16,
    rps: float = 30,
    tps: float = 80_000,
) -> dict:
    """Ask every point not already cached for this run; returns the usage summary."""
    RAW.mkdir(parents=True, exist_ok=True)
    out_path, usage_path, meta_path = paths(spec.name)
    meta_path.write_text(json.dumps(asdict(spec), indent=2))
    done = set(load(spec.name))
    todo = [p for p in points if geo.point_id(*p) not in done]
    lat_lon = {geo.point_id(*p): p for p in points}
    reqs = build_requests(spec, todo)
    top_k = 10 if spec.experiment == "political" else None
    print(f"[{spec.name}] {len(points)} points, {len(done)} cached, {len(reqs)} requests to send")
    if not reqs:
        return usage(spec.name)

    limiter = Limiter(rps, tps)
    sem = asyncio.Semaphore(concurrency)
    failures = 0
    finished = 0
    t_start = time.monotonic()

    if spec.backend == "jev":
        client_cm = AsyncTypeSafeClient(model=spec.model, retry=RetryPolicy(max_retries=8, backoff_max=20.0), timeout=120.0)
    else:
        client_cm = backends.CloudflareClient(spec.backend)
    async with client_cm as client:
        with open(out_path, "a") as out, open(usage_path, "a") as uout:

            async def one(state, questions, ids):
                nonlocal failures, finished
                body = json.dumps(
                    {k: q.model_dump(mode="json") for k, q in questions.items()}, ensure_ascii=False
                )
                est = (len(body) + len(json.dumps(state))) // 3 + 300
                async with sem:
                    await limiter.acquire(est)
                    t0 = time.monotonic()
                    try:
                        resp = await client.system_one(state=state, questions=questions)
                    except (TypeSafeError, RuntimeError) as e:
                        failures += 1
                        print(f"  request failed ({len(ids)} points): {type(e).__name__}: {e}")
                        return
                    dt = time.monotonic() - t0
                for key, pid in zip(questions, ids):
                    ans = resp.answers.get(key)
                    if ans is None:
                        continue
                    lat, lon = lat_lon[pid]
                    rec = {"id": pid, "lat": lat, "lon": lon, "model": resp.model, **_record(ans, top_k)}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                uout.write(
                    json.dumps(
                        {
                            "points": len(ids),
                            "input_tokens": resp.usage.input_tokens,
                            "output_tokens": resp.usage.output_tokens,
                            "seconds": dt,
                            "est_tokens": est,
                        }
                    )
                    + "\n"
                )
                out.flush()
                uout.flush()
                finished += 1
                if finished % max(1, len(reqs) // 10) == 0:
                    print(f"  {finished}/{len(reqs)} requests, {time.monotonic() - t_start:.0f}s")

            await asyncio.gather(*(one(*r) for r in reqs))

    summary = usage(spec.name)
    print(f"[{spec.name}] done in {time.monotonic() - t_start:.0f}s, failures={failures}, {summary}")
    return summary


def run_sync(spec: RunSpec, points, **kw) -> dict:
    return asyncio.run(run(spec, points, **kw))
