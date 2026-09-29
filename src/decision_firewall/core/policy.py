"""Shared deterministic gate; offline evaluation never resolves evidence or executes."""

from .contracts import Context, Decision, Disposition
from .observation import component
from .rules import PolicyReport

ALLOWED = {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}


def evaluate_context(domain, context, reports=None):
    # Pydantic frozen records do not freeze nested dictionaries. Policies must not
    # mutate the snapshot used for authorization bindings, replay or later variants.
    context = Context.model_validate(context.model_dump(mode="json"))
    if context.evidence.missing:
        return Decision(disposition=Disposition.REQUIRE_EVIDENCE, reasons=context.evidence.missing)
    if context.review and context.review.decision == "reject":
        return Decision(disposition=Disposition.DENY, reasons=["review_rejected"])
    if context.review and context.review.decision == "request_evidence":
        return Decision(
            disposition=Disposition.REQUIRE_EVIDENCE, reasons=["review_requested_evidence"]
        )
    if context.assessment.status != "available":
        return Decision(disposition=Disposition.REQUIRE_REVIEW, reasons=["assessment_unavailable"])
    report = (
        domain.evaluate.evaluate_report(context)
        if hasattr(domain.evaluate, "evaluate_report")
        else PolicyReport(
            decision=Decision.model_validate(domain.evaluate(context).model_dump(mode="json"))
        )
    )
    if reports is not None:
        reports.extend(report.rules)
    for rule in report.rules:
        component(
            "policy.rule",
            rule.status,
            rule.duration_ms,
            rule_name=rule.name,
            rule_version=rule.version,
        )
    result = report.decision
    if result.disposition in ALLOWED and not result.errors:
        if set(result.constraints) - domain.supported_constraints:
            return Decision(disposition=None, errors=["unsupported_constraint"])
        for claim in result.claims:
            if context.usage.get(claim.key, 0) + claim.units > claim.capacity:
                return Decision(
                    disposition=Disposition(claim.on_exhausted),
                    reasons=["resource_exhausted:" + claim.key],
                )
    return result
