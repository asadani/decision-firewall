"""Optional pinned local Laya adapter with application-defined typed questions."""

import gc
import json
import os
import threading
import time

from ..core.contracts import Assessment, Signal

LAYA_MODEL = "convaiinnovations/laya-typed-decisions"
LAYA_REVISION = "1a793eb568e6718f15941d08f85432581df534e3"


class LazyLayaModel:
    """Load at first inference; release between sequential experiment variants."""

    def __init__(self, questions, device="auto"):
        self.questions, self.device = questions, device
        self.loaded = None
        self.seed = 42

    def set_seed(self, seed):
        self.seed = seed

    def _load(self):
        if self.loaded is None:
            import torch

            torch.manual_seed(self.seed)
            self.loaded = LayaModel(self.questions, device=self.device)
        return self.loaded

    def assess(self, message):
        return self._load().assess(message)

    def assess_context(self, input):
        return self._load().assess_context(input)

    def measure_input(self, message):
        return self._load().measure_input(message)

    def release(self):
        if self.loaded is not None:
            self.loaded.release()
            self.loaded = None


class LayaModel:
    def __init__(self, questions: dict, device="auto", model=LAYA_MODEL, revision=LAYA_REVISION):
        self.questions = json.loads(json.dumps(questions))
        if not self.questions:
            raise ValueError("At least one typed decision question is required")
        os.environ["USE_TF"] = "0"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        import laya
        import torch

        if laya.__version__ != "0.3.20":
            raise RuntimeError("This adapter requires laya==0.3.20")
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.lock = threading.Lock()
        self.model_id, self.revision = model, revision
        self.requested_device = device
        self.fallback: str | None = None
        target = (
            "cuda"
            if device == "auto" and torch.cuda.is_available()
            else "cpu"
            if device == "auto"
            else device
        )
        if device == "auto" and target == "cpu":
            self.fallback = "CUDA unavailable"
        start = time.perf_counter()
        from huggingface_hub import snapshot_download

        snapshot = snapshot_download(
            model,
            revision=revision,
            allow_patterns=[
                "rl_agent_config.json",
                "model.safetensors",
                "tokenizer/*",
                "encoder/*",
            ],
        )
        try:
            self.agent = laya.Agent(snapshot, device=target, fast=False, compile=False)
        except RuntimeError as exc:
            if target != "cuda":
                raise
            self.fallback = "CUDA loading failure: " + str(exc)
            gc.collect()
            torch.cuda.empty_cache()
            self.agent = laya.Agent(snapshot, device="cpu", fast=False, compile=False)
        self.agent.amp_enabled = False
        self.agent.dtype = torch.float32
        self.agent.model.float()
        self.device = str(self.agent.device)
        if self.device != target:
            self.fallback = f"SDK could not load on {target}"
        self.cold_load_ms = (time.perf_counter() - start) * 1000

    def measure_input(self, message: str) -> int:
        from laya.common import serialize_state

        return len(self.agent.tok.encode(serialize_state(message), add_special_tokens=True))

    def release(self):
        import torch

        del self.agent
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def assess_context(self, input) -> Assessment:
        return self.assess(input.render())

    def assess(self, message: str) -> Assessment:
        import torch
        from laya.common import serialize_state

        with self.lock:
            # A conservative short-state cap leaves room for each question and option head.
            token_count = len(
                self.agent.tok.encode(serialize_state(message), add_special_tokens=True)
            )
            if token_count > 256:
                raise ValueError("Input exceeds the 256-token evidence-preserving state limit")
            if (
                len(self.agent.tok.encode(serialize_state(self.questions), add_special_tokens=True))
                > 192
            ):
                raise ValueError("Decision questions exceed the 192-token template limit")
            start = time.perf_counter()
            try:
                raw = self.agent.predict(message, self.questions, max_len=512)
            except RuntimeError as exc:
                if self.agent.device.type != "cuda":
                    raise
                self.fallback = str(exc)
                self.agent.deaccelerate()
                self.agent.model.cpu()
                self.agent.device = torch.device("cpu")
                self.agent.dtype = torch.float32
                self.agent.amp_enabled = False
                gc.collect()
                torch.cuda.empty_cache()
                raw = self.agent.predict(message, self.questions, max_len=512)
            self.device = str(self.agent.device)
            answers = raw["answers"]
            signals = {}
            for name, answer in answers.items():
                kind = answer["type"]
                if kind == "choice":
                    signals[name] = Signal(
                        kind="choice", value=answer["choice"], probabilities=answer["probabilities"]
                    )
                elif kind == "score":
                    signals[name] = Signal(
                        kind="ordinal", value=answer["score"], probabilities=answer["probabilities"]
                    )
                elif kind == "noul":
                    signals[name] = Signal(kind="probability", value=answer["noul"])
                else:
                    raise ValueError(f"Unsupported Laya answer type: {kind}")
            if set(signals) != set(self.questions):
                raise ValueError("Incomplete model answer")
            return Assessment(
                provider="laya",
                model=self.model_id,
                revision=self.revision,
                signals=signals,
                metadata={
                    "device": self.device,
                    "precision": "fp32",
                    "input_tokens": token_count,
                    "latency_ms": (time.perf_counter() - start) * 1000,
                    "cold_load_ms": self.cold_load_ms,
                    "fallback": self.fallback,
                    "raw": raw,
                },
            )
