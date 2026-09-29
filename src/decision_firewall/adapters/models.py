"""Bring any decision model through one small, validated interface."""

from collections.abc import Callable

from ..core.contracts import Assessment


class FixtureModel:
    def __init__(self, assessment: Assessment):
        self._assessment = assessment.model_dump(mode="json")

    def assess(self, message: str) -> Assessment:
        return Assessment.model_validate(self._assessment)


class CallableModel:
    """Wrap an SDK/HTTP client supplied by the application; no provider dependency."""

    def __init__(self, call: Callable[[str], dict]):
        self.call = call

    def assess(self, message: str) -> Assessment:
        return Assessment.model_validate(self.call(message))


class RefundModelAdapter:
    """Adapt the existing fixture, keyword and pinned Laya refund providers."""

    def __init__(self, provider):
        self.provider = provider

    def assess(self, message: str) -> Assessment:
        from ..core.contracts import Signal

        result = self.provider.assess(message)
        signals = {
            "request_type": Signal(
                kind="choice", value=result.request_type, probabilities=result.probabilities
            )
        }
        if result.refund_requested_probability is not None:
            signals["refund_requested"] = Signal(
                kind="probability", value=result.refund_requested_probability
            )
        if result.ordinal_score is not None:
            signals["ordinal"] = Signal(kind="ordinal", value=result.ordinal_score)
        return Assessment(
            provider=result.provider,
            model=result.model,
            revision=result.revision,
            status="unavailable" if result.request_type == "unavailable" else "available",
            calibration=result.calibration,
            signals=signals,
            metadata=result.metadata,
        )
