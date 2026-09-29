"""Domain-neutral, JSON-serializable SDK contracts. No financial vocabulary."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1


class Disposition(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_WITH_CONSTRAINTS = "ALLOW_WITH_CONSTRAINTS"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    DENY = "DENY"


class Signal(Record):
    """Preserve a model's output semantics; never interpret a score as permission."""

    kind: Literal["choice", "probability", "ordinal", "text"]
    value: str | float
    probabilities: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_semantics(self):
        if self.kind in {"probability", "ordinal"} and not isinstance(self.value, float):
            raise ValueError("Numeric signal required")
        if self.kind == "probability" and not 0 <= float(self.value) <= 1:
            raise ValueError("Probability must be in [0,1]")
        if self.kind in {"choice", "text"} and not isinstance(self.value, str):
            raise ValueError("Text signal required")
        if any(not 0 <= value <= 1 for value in self.probabilities.values()):
            raise ValueError("Probabilities must be finite and in [0,1]")
        return self


class Assessment(Record):
    provider: str
    model: str
    revision: str
    signals: dict[str, Signal] = Field(default_factory=dict)
    status: Literal["available", "unavailable"] = "available"
    calibration: str = "uncalibrated"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class Proposal(Record):
    domain: str = Field(min_length=1)
    action: dict[str, JsonValue]
    message: str = Field(min_length=1, max_length=16000)
    objective: str = Field(default="", max_length=4000)


class Evidence(Record):
    facts: dict[str, JsonValue] = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)


class Claim(Record):
    """A transactionally reserved resource, scoped to its domain registration."""

    key: str = Field(min_length=1)
    units: int = Field(gt=0, strict=True)
    capacity: int = Field(ge=0, strict=True)
    retain_on_success: bool = False
    on_exhausted: Literal["DENY", "REQUIRE_REVIEW"] = "DENY"


class Decision(Record):
    disposition: Disposition | None
    reasons: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_claims(self):
        if len({c.key for c in self.claims}) != len(self.claims):
            raise ValueError("Resource claim keys must be unique")
        return self


class Review(Record):
    decision: Literal["approve", "reject", "request_evidence"]
    reason: str = Field(min_length=3, max_length=2000)


class Context(Record):
    proposal: Proposal
    assessment: Assessment
    evidence: Evidence
    review: Review | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    now: float


class ExecutionResult(Record):
    status: Literal["SUCCEEDED", "FAILED", "UNKNOWN"]
    detail: dict[str, JsonValue] = Field(default_factory=dict)


class RuntimeIdentity(Record):
    """Trusted host configuration, never parsed from a model or proposal."""

    requester: str = "requester"
    reviewer: str = "reviewer"
    executor: str = "executor"
    auditor: str = "auditor"
