"""Laya checkpoints on a Modal GPU. Takes Jev-shaped requests, returns Jev-shaped answers.

Used by scripts/laya_bench.py; not run directly.
"""

import modal

app = modal.App("jevmap-laya")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("laya==0.3.23", "hf_transfer")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
hf_cache = modal.Volume.from_name("jevmap-hf-cache", create_if_missing=True)


@app.cls(image=image, gpu="L4", volumes={"/root/.cache/huggingface": hf_cache}, timeout=3600, scaledown_window=60, max_containers=1)
class Laya:
    checkpoint: str = modal.parameter()

    @modal.enter()
    def load(self) -> None:
        import laya

        repo, sub = {
            "english": ("convaiinnovations/laya", None),
            "multilingual": ("convaiinnovations/laya", "multilingual"),
            "typed-decisions": ("convaiinnovations/laya-typed-decisions", None),
        }[self.checkpoint]
        self.agent = laya.load(repo, subfolder=sub, device="cuda")
        hf_cache.commit()

    @modal.method()
    def same_questions(self, states: list, questions: dict) -> list[dict]:
        """Many states, one question set (coordinate in the state)."""
        out = self.agent.predict_batch(states, questions, batch_size=128)
        return [{"answers": r["answers"]} for r in out]

    @modal.method()
    def one_each(self, requests: list[tuple]) -> list[dict]:
        """Independent (state, questions) requests (coordinate in the questions)."""
        return [{"answers": self.agent.system_one(state, qs)["answers"]} for state, qs in requests]
