"""Assessment providers never receive a Firewall or execution credential."""

import time
from typing import Any, Literal, Protocol

from .contracts import Assessment

LAYA_MODEL = "convaiinnovations/laya-typed-decisions"
LAYA_REVISION = "1a793eb568e6718f15941d08f85432581df534e3"
QUESTIONS: dict[str, Any] = {
    "request_type": {
        "type": "choice",
        "instructions": "What is the customer's main billing request?",
        "criteria": {
            "duplicate": "Refund a duplicate charge or being billed twice",
            "cancellation": "Cancel a subscription and refund its charge",
            "other": "Any other request or complaint",
        },
    },
    "refund_requested": {
        "type": "noul",
        "instructions": "Does the customer explicitly ask for a refund or their money back?",
    },
}


class Provider(Protocol):
    def assess(self, message: str) -> Assessment: ...


class FixtureProvider:
    def __init__(self, label="duplicate", refund_requested=True):
        self.label = label
        self.refund_requested = refund_requested

    def assess(self, message: str) -> Assessment:
        return Assessment(
            provider="fixture",
            model="oracle-fixture",
            revision="1",
            request_type=self.label,
            probabilities={self.label: 1.0},
            refund_requested_probability=float(self.refund_requested),
            calibration="synthetic_oracle",
            metadata={"latency_ms": 0.0, "device": "none"},
        )


class BaselineProvider:
    def assess(self, message: str) -> Assessment:
        start = time.perf_counter()
        text = message.lower()
        label: Literal["duplicate", "cancellation", "other"] = (
            "duplicate"
            if any(w in text for w in ("twice", "duplicate", "double charge"))
            else "cancellation"
            if "cancel" in text
            else "other"
        )
        return Assessment(
            provider="baseline",
            model="keyword-rules",
            revision="1",
            request_type=label,
            probabilities={label: 1.0},
            refund_requested_probability=float("refund" in text or "money back" in text),
            calibration="not_calibrated",
            metadata={"latency_ms": (time.perf_counter() - start) * 1000, "device": "cpu"},
        )


class LayaProvider:
    """v0.1 refund-specific facade over the reusable Laya adapter."""

    def __init__(self, device="auto", model=LAYA_MODEL, revision=LAYA_REVISION):
        from ...adapters.laya import LayaModel

        self.adapter = LayaModel(QUESTIONS, device=device, model=model, revision=revision)

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def assess(self, message: str) -> Assessment:
        result = self.adapter.assess(message)
        choice = result.signals["request_type"]
        return Assessment.model_validate(
            {
                "provider": result.provider,
                "model": result.model,
                "revision": result.revision,
                "request_type": choice.value,
                "probabilities": choice.probabilities,
                "refund_requested_probability": result.signals["refund_requested"].value,
                "metadata": result.metadata,
            }
        )
