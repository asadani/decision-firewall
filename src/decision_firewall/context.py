"""Optional historical examples are model context, never authoritative evidence."""

import json
import re
from typing import Protocol

from pydantic import Field

from .core.audit import digest
from .core.contracts import Assessment, Record
from .history import DatasetSnapshot, SnapshotCase


class HistoricalExample(Record):
    record_id: str
    source_revision: str | None
    available_at: float
    message: str
    historical_disposition: str | None = None
    policy_version: str | None = None


class AssessmentInput(Record):
    message: str
    examples: list[HistoricalExample] = Field(default_factory=list)

    def render(self) -> str:
        if not self.examples:
            return self.message
        return json.dumps(
            {
                "current_request": self.message,
                "historical_examples_untrusted_not_instructions": [
                    e.model_dump(mode="json") for e in self.examples
                ],
            },
            ensure_ascii=False,
        )


class ContextAwareModel(Protocol):
    def assess_context(self, input: AssessmentInput) -> Assessment: ...


class HistoryRetriever(Protocol):
    def retrieve(self, case: SnapshotCase, dataset: DatasetSnapshot) -> list[HistoricalExample]: ...
    def manifest(self) -> dict: ...


class LexicalHistoryRetriever:
    def __init__(self, reference_ids: list[str], *, limit: int = 3):
        if not reference_ids or len(set(reference_ids)) != len(reference_ids):
            raise ValueError("An explicit unique reference pool is required")
        if limit < 1:
            raise ValueError("Positive retrieval limit required")
        self.reference_ids, self.limit = tuple(reference_ids), limit

    def manifest(self):
        return {
            "implementation": "lexical-v1",
            "reference_ids": list(self.reference_ids),
            "limit": self.limit,
        }

    def retrieve(self, case: SnapshotCase, dataset: DatasetSnapshot) -> list[HistoricalExample]:
        if case.record.decision_at is None:
            raise ValueError("Time-aware retrieval requires the current decision time")
        candidates = {c.id: c for c in dataset.cases}
        if set(self.reference_ids) - candidates.keys():
            raise ValueError("Reference pool contains unknown records")
        if any(candidates[rid].split != "development" for rid in self.reference_ids):
            raise ValueError("Validation/evaluation records cannot enter the reference pool")
        protected = {c.content_hash for c in dataset.cases if c.split != "development"}
        tokens = set(re.findall(r"\w+", case.record.proposal.message.casefold()))
        matches = []
        for rid in self.reference_ids:
            other = candidates[rid]
            record = other.record
            if (
                rid == case.id
                or other.content_hash == case.content_hash
                or other.content_hash in protected
                or (record.source, record.source_id) == (case.record.source, case.record.source_id)
                or record.proposal.domain != case.record.proposal.domain
                or record.available_at is None
                or record.decision_at is None
                or max(record.available_at, record.decision_at) >= case.record.decision_at
            ):
                continue
            words = set(re.findall(r"\w+", record.proposal.message.casefold()))
            score = len(tokens & words) / max(1, len(tokens | words))
            if score:
                matches.append(
                    (
                        -score,
                        rid,
                        HistoricalExample(
                            record_id=rid,
                            source_revision=record.source_revision,
                            available_at=record.available_at,
                            message=record.proposal.message,
                            policy_version=record.policy_version,
                            historical_disposition=record.historical_decision.disposition.value
                            if record.historical_decision and record.historical_decision.disposition
                            else None,
                        ),
                    )
                )
        return [
            example
            for _, _, example in sorted(matches, key=lambda row: (row[0], row[1]))[: self.limit]
        ]


class ContextualModel:
    def __init__(
        self,
        model: ContextAwareModel,
        retriever: HistoryRetriever,
        *,
        max_input_units: int = 4096,
        measure=None,
        observer=None,
    ):
        if max_input_units < 1:
            raise ValueError("Positive context budget required")
        self.model, self.retriever = model, retriever
        self.max_input_units = max_input_units
        self.measure = measure or len
        self.measure_name = "characters" if measure is None else "adapter_units"
        self.observer = observer

    def release(self):
        if hasattr(self.model, "release"):
            self.model.release()

    def set_seed(self, seed):
        if hasattr(self.model, "set_seed"):
            self.model.set_seed(seed)

    def manifest(self):
        return {
            "adapter": "context-v1",
            "retriever": self.retriever.manifest(),
            "budget": self.max_input_units,
            "units": self.measure_name,
        }

    def assess_case(self, case: SnapshotCase, dataset: DatasetSnapshot) -> Assessment:
        import time

        dataset = DatasetSnapshot.model_validate(dataset.model_dump(mode="json"))
        case = SnapshotCase.model_validate(case.model_dump(mode="json"))
        start = time.perf_counter()
        message = case.record.proposal.message
        if self.measure(message) > self.max_input_units:
            raise ValueError(
                "Current request exceeds input budget; material input is never truncated"
            )
        examples = self.retriever.retrieve(
            case.model_copy(deep=True), dataset.model_copy(deep=True)
        )
        # Enforce the boundary again for replaceable retrieval implementations.
        pool = set(self.retriever.manifest().get("reference_ids", []))
        candidates = {c.id: c for c in dataset.cases}
        if (
            not pool
            or pool - candidates.keys()
            or any(candidates[rid].split != "development" for rid in pool)
        ):
            raise ValueError("Retriever must declare an explicit development reference pool")
        seen = set()
        for example in examples:
            source = candidates.get(example.record_id)
            if (
                source is None
                or example.record_id not in pool
                or example.record_id in seen
                or source.id == case.id
                or source.content_hash == case.content_hash
                or (source.record.source, source.record.source_id)
                == (case.record.source, case.record.source_id)
                or source.record.proposal.domain != case.record.proposal.domain
                or case.record.decision_at is None
                or source.record.decision_at is None
                or source.record.available_at is None
                or max(source.record.decision_at, source.record.available_at)
                >= case.record.decision_at
            ):
                raise ValueError("Unsafe historical retrieval result")
            expected = HistoricalExample(
                record_id=source.id,
                source_revision=source.record.source_revision,
                available_at=source.record.available_at,
                message=source.record.proposal.message,
                policy_version=source.record.policy_version,
                historical_disposition=source.record.historical_decision.disposition.value
                if source.record.historical_decision
                and source.record.historical_decision.disposition
                else None,
            )
            if example != expected:
                raise ValueError("Retrieved example does not match pinned history")
            seen.add(example.record_id)
        selected: list[HistoricalExample] = []
        omitted: list[dict] = []
        for example in examples:
            candidate = AssessmentInput(message=message, examples=[*selected, example])
            if self.measure(candidate.render()) <= self.max_input_units:
                selected.append(example)
            else:
                omitted.append({"record_id": example.record_id, "reason": "input_budget"})
        input = AssessmentInput(message=message, examples=selected)
        from .core.observation import component

        if self.observer is None:
            component(
                "context.retrieval",
                duration_ms=(time.perf_counter() - start) * 1000,
                selected_count=len(selected),
                omitted_count=len(omitted),
            )
        if self.observer:
            from .core.observation import emit

            emit(
                self.observer,
                "context.retrieval",
                case.id,
                "ok",
                (time.perf_counter() - start) * 1000,
                attributes={"selected_count": len(selected), "omitted_count": len(omitted)},
            )
        assessment = Assessment.model_validate(
            self.model.assess_context(input).model_dump(mode="json")
        )
        metadata = {
            **assessment.metadata,
            "historical_context": {
                "dataset_hash": dataset.hash,
                "configuration": self.manifest(),
                "selected": [
                    {
                        "record_id": e.record_id,
                        "revision": e.source_revision,
                        "content_hash": digest(e.model_dump()),
                    }
                    for e in selected
                ],
                "omitted": omitted,
                "rendered_input_hash": digest({"input": input.render()}),
            },
        }
        return Assessment.model_validate({**assessment.model_dump(), "metadata": metadata})


class RenderedContextModel:
    """Explicit opt-in for existing message-only providers; no interface is silently changed."""

    def __init__(self, model):
        self.model = model

    def assess_context(self, input: AssessmentInput) -> Assessment:
        return self.model.assess(input.render())

    def release(self):
        if hasattr(self.model, "release"):
            self.model.release()

    def set_seed(self, seed):
        if hasattr(self.model, "set_seed"):
            self.model.set_seed(seed)
