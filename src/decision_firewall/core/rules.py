"""Optional explicit rule composition. No rule can grant execution authority."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .contracts import Claim, Context, Decision, Disposition, Record


class RuleResult(Record):
    name: str = ""
    version: str = ""
    status: Literal["pass", "deny", "evidence", "review", "error", "satisfied_by_review"] = "pass"
    reasons: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    duration_ms: float = 0.0


class PolicyReport(Record):
    decision: Decision
    rules: list[RuleResult] = Field(default_factory=list)


@dataclass(frozen=True)
class Rule:
    name: str
    version: str
    description: str
    check: Callable[[Context, BaseModel], RuleResult]
    config: BaseModel
    kind: Literal["mandatory", "review"] = "mandatory"

    def __post_init__(self):
        if not self.name or not self.version or self.kind not in {"mandatory", "review"}:
            raise ValueError("Named/versioned rule and valid kind required")
        type(self.config).model_validate(self.config.model_dump())

    def manifest(self):
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "kind": self.kind,
            "config": self.config.model_dump(mode="json"),
        }


class RuleSet:
    def __init__(self, rules: list[Rule], *, finalize: Callable[[Context], Decision] | None = None):
        if not rules or len({r.name for r in rules}) != len(rules):
            raise ValueError("A rule set needs unique named rules")
        self.rules = tuple(sorted(rules, key=lambda r: r.kind != "mandatory"))
        self.finalize = finalize

    def manifest(self):
        return [rule.manifest() for rule in self.rules]

    def __call__(self, context: Context) -> Decision:
        return self.evaluate_report(context).decision

    def evaluate_report(self, context: Context) -> PolicyReport:
        results = []
        for rule in self.rules:
            start = time.perf_counter()
            try:
                if (
                    rule.kind == "review"
                    and context.review
                    and context.review.decision == "approve"
                ):
                    result = RuleResult(status="satisfied_by_review")
                else:
                    # Each rule gets its own validated copy; one rule cannot mutate another's facts.
                    result = RuleResult.model_validate(
                        rule.check(
                            Context.model_validate(context.model_dump()),
                            type(rule.config).model_validate(rule.config.model_dump()),
                        ).model_dump()
                    )
                    if rule.kind == "review" and result.status not in {"pass", "review", "error"}:
                        raise ValueError("Hard constraints must be mandatory rules")
            except Exception as exc:  # noqa: BLE001 -- any rule failure prevents authorization
                result = RuleResult(status="error", reasons=[type(exc).__name__])
            results.append(
                result.model_copy(
                    update={
                        "name": rule.name,
                        "version": rule.version,
                        "duration_ms": (time.perf_counter() - start) * 1000,
                    }
                )
            )
        for status, disposition in [
            ("error", None),
            ("deny", Disposition.DENY),
            ("evidence", Disposition.REQUIRE_EVIDENCE),
            ("review", Disposition.REQUIRE_REVIEW),
        ]:
            matches = [r for r in results if r.status == status]
            if matches:
                reasons = [f"{r.name}:{reason}" for r in matches for reason in r.reasons] or [
                    status
                ]
                return PolicyReport(
                    decision=Decision(
                        disposition=disposition,
                        reasons=[] if status == "error" else reasons,
                        errors=reasons if status == "error" else [],
                    ),
                    rules=results,
                )
        try:
            final = (
                self.finalize(context) if self.finalize else Decision(disposition=Disposition.ALLOW)
            )
            constraints = list(
                dict.fromkeys([*final.constraints, *(c for r in results for c in r.constraints)])
            )
            claims = [*final.claims, *(c for r in results for c in r.claims)]
            if len({c.key for c in claims}) != len(claims):
                raise ValueError("Conflicting resource claim definitions")
            decision = Decision.model_validate(
                {
                    **final.model_dump(),
                    "constraints": constraints,
                    "claims": [c.model_dump() for c in claims],
                    "disposition": Disposition.ALLOW_WITH_CONSTRAINTS
                    if constraints and final.disposition == Disposition.ALLOW
                    else final.disposition,
                }
            )
        except Exception as exc:  # noqa: BLE001 -- final assembly also fails closed
            decision = Decision(disposition=None, errors=[str(exc)])
        return PolicyReport(decision=decision, rules=results)
