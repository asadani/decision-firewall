"""Versioned boundary types. Money is always integer minor units."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1


class Disposition(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_WITH_CONSTRAINTS = "ALLOW_WITH_CONSTRAINTS"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    DENY = "DENY"


class Assessment(Record):
    provider: str
    model: str
    revision: str
    request_type: Literal["duplicate", "cancellation", "other", "unavailable"]
    probabilities: dict[str, float] = Field(default_factory=dict)
    refund_requested_probability: float | None = Field(default=None, ge=0, le=1)
    ordinal_score: float | None = None
    calibration: str = "uncalibrated"
    metadata: dict = Field(default_factory=dict)


class Proposal(Record):
    payment_id: str
    customer_id: str
    message: str = Field(min_length=1, max_length=16000)
    amount_minor: int = Field(gt=0, strict=True)
    currency: Literal["INR"] = "INR"
    destination: str
    requested_reason: Literal["duplicate", "cancellation", "other"] = "other"
    objective: str = "Resolve the customer request under the published refund policy"
    incentives: dict = Field(default_factory=dict)


class Payment(Record):
    payment_id: str
    customer_id: str
    amount_minor: int = Field(gt=0, strict=True)
    refunded_minor: int = Field(default=0, ge=0, strict=True)
    destination: str
    currency: Literal["INR"] = "INR"
    duplicate_verified: bool | None = None
    age_days: int | None = Field(default=None, ge=0)
    unused: bool | None = None
    version: int = Field(default=1, ge=1)


class Policy(Record):
    version: str = "refund-demo-v1"
    auto_amount_minor: int = Field(default=100000, ge=0)
    daily_auto_limit_minor: int = Field(default=1000000, ge=0)
    cancellation_days: int = Field(default=7, ge=0)
    authorization_seconds: int = Field(default=300, gt=0)


class Evaluation(Record):
    disposition: Disposition | None
    reasons: list[str]
    errors: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class ReviewDecision(Record):
    decision: Literal["approve", "reject", "request_evidence"]
    reason: str = Field(min_length=3, max_length=2000)


class OutcomeEvent(Record):
    kind: Literal["outcome", "appeal", "correction"]
    description: str = Field(min_length=3, max_length=4000)
    source: str = Field(min_length=1)
