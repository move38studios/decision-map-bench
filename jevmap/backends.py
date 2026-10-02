"""Clients for the decision models, all returning Jev-shaped responses.

- jev:        TypeSafe SDK (api.typesafe.ai)
- clef, clef-flash: Cloudflare Workers AI REST, same request/response body as Jev
- laya-*:     the open Laya checkpoints, run in a Modal GPU function (see modal_laya.py)
"""

import asyncio
import datetime as dt
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv

load_dotenv()

CF_ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
WRANGLER_CONFIG = Path.home() / "Library/Preferences/.wrangler/config/default.toml"
PRICE_PER_MTOK = {"jev": 0.042, "clef": 0.24, "clef-flash": 0.24}


def _ns(answer: dict) -> SimpleNamespace:
    return SimpleNamespace(
        type=answer["type"],
        noul=answer.get("noul"),
        choice=answer.get("choice"),
        probabilities=answer.get("probabilities", {}),
        confidence=answer.get("confidence"),
    )


def to_response(body: dict) -> SimpleNamespace:
    usage = body.get("usage") or {}
    return SimpleNamespace(
        model=body.get("model", ""),
        answers={k: _ns(v) for k, v in body.get("answers", {}).items()},
        usage=SimpleNamespace(input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens")),
    )


class CloudflareToken:
    """The wrangler OAuth token; refreshed through `wrangler whoami` shortly before it expires."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.token, self.expires = self._read()

    @staticmethod
    def _read() -> tuple[str, dt.datetime]:
        if os.environ.get("CLOUDFLARE_API_TOKEN"):
            return os.environ["CLOUDFLARE_API_TOKEN"], dt.datetime.max.replace(tzinfo=dt.timezone.utc)
        text = WRANGLER_CONFIG.read_text()
        token = re.search(r'^oauth_token\s*=\s*"(.*)"', text, re.M).group(1)
        exp = re.search(r'^expiration_time\s*=\s*"(.*)"', text, re.M).group(1)
        return token, dt.datetime.fromisoformat(exp.replace("Z", "+00:00"))

    async def get(self, force: bool = False) -> str:
        async with self.lock:
            now = dt.datetime.now(dt.timezone.utc)
            if force or self.expires - now < dt.timedelta(minutes=3):
                await asyncio.to_thread(
                    subprocess.run, ["npx", "--yes", "wrangler", "whoami"], capture_output=True, timeout=120
                )
                self.token, self.expires = self._read()
            return self.token


class CloudflareClient:
    def __init__(self, model: str, timeout: float = 120.0) -> None:
        if not CF_ACCOUNT:
            raise RuntimeError("Set CLOUDFLARE_ACCOUNT_ID (and CLOUDFLARE_API_TOKEN, or log in with wrangler).")
        self.model = model
        self.url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/run/@cf/cloudflare/{model}"
        self.http = httpx.AsyncClient(timeout=timeout)
        self.token = CloudflareToken()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.http.aclose()

    async def system_one(self, state, questions: dict) -> SimpleNamespace:
        body = {
            "state": state,
            "questions": {k: (q.model_dump(mode="json") if hasattr(q, "model_dump") else q) for k, q in questions.items()},
        }
        delay = 1.0
        for attempt in range(10):
            token = await self.token.get(force=attempt > 0 and delay > 8)
            try:
                r = await self.http.post(self.url, json=body, headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError as e:
                err = repr(e)
            else:
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        return to_response(data["result"])
                    err = str(data.get("errors"))
                else:
                    err = f"{r.status_code} {r.text[:300]}"
                if r.status_code == 401:
                    await self.token.get(force=True)
                elif r.status_code in (400, 413, 422):
                    raise RuntimeError(f"Cloudflare {self.model}: {err}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
        raise RuntimeError(f"Cloudflare {self.model}: gave up after retries: {err}")
