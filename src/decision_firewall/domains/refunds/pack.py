"""Named refund rules; pack_v1 retains historical evaluation semantics."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ...core.rules import Rule, RuleResult, RuleSet
from .contracts import Payment, Policy, Proposal
from .pack_v1 import RefundExecutor
from .pack_v1 import refund_domain as refund_domain_v1


def refund_domain(home: str | Path, *, policy: Policy | None = None, mode="success"):
    config = policy or Policy()
    pack = refund_domain_v1(home, policy=config, mode=mode)

    def values(context):
        return Proposal.model_validate(context.proposal.action), Payment.model_validate(
            context.evidence.facts["payment"]
        )

    def binding(context, config):
        p, payment = values(context)
        if p.customer_id != payment.customer_id:
            return RuleResult(status="deny", reasons=["customer_mismatch"])
        if p.currency != payment.currency or p.destination != payment.destination:
            return RuleResult(status="deny", reasons=["destination_or_currency_mismatch"])
        return RuleResult()

    def balance(context, config):
        p, payment = values(context)
        if p.amount_minor > payment.amount_minor - payment.refunded_minor - context.usage.get(
            "payment:" + p.payment_id, 0
        ):
            return RuleResult(status="deny", reasons=["exceeds_refundable_balance"])
        return RuleResult()

    def eligibility(context, config):
        p, payment = values(context)
        if p.requested_reason == "duplicate":
            if payment.duplicate_verified is None:
                return RuleResult(status="evidence", reasons=["duplicate_evidence_missing"])
            if not payment.duplicate_verified:
                return RuleResult(status="deny", reasons=["duplicate_not_verified"])
        elif p.requested_reason == "cancellation":
            if payment.age_days is None or payment.unused is None:
                return RuleResult(status="evidence", reasons=["usage_or_age_missing"])
            if payment.age_days > config.cancellation_days or not payment.unused:
                return RuleResult(status="deny", reasons=["cancellation_ineligible"])
        return RuleResult()

    def available(context, config):
        signal = context.assessment.signals.get("request_type")
        if signal is None or signal.value == "unavailable":
            return RuleResult(status="review", reasons=["assessment_unavailable"])
        return RuleResult()

    def intake(context, config):
        p, _ = values(context)
        signal = context.assessment.signals.get("request_type")
        if p.requested_reason == "other" or signal is None or signal.value != p.requested_reason:
            return RuleResult(
                status="review", reasons=["manual_eligibility_or_intake_disagreement"]
            )
        return RuleResult()

    def limits(context, config):
        p, _ = values(context)
        day = datetime.fromtimestamp(context.now, UTC).date().isoformat()
        if (
            p.amount_minor > config.auto_amount_minor
            or context.usage.get("auto-budget:" + day, 0) + p.amount_minor
            > config.daily_auto_limit_minor
        ):
            return RuleResult(status="review", reasons=["automatic_amount_or_budget_limit"])
        return RuleResult()

    rules = RuleSet(
        [
            Rule(
                "payment_binding", "1", "Bind customer, destination and currency", binding, config
            ),
            Rule(
                "remaining_balance",
                "1",
                "Never exceed remaining refundable balance",
                balance,
                config,
            ),
            Rule(
                "refund_eligibility",
                "1",
                "Duplicate or unused timely cancellation",
                eligibility,
                config,
            ),
            Rule(
                "assessment_available",
                "1",
                "An unavailable classification cannot be approved away",
                available,
                config,
            ),
            Rule(
                "customer_intent",
                "1",
                "Review other requests and model disagreements",
                intake,
                config,
                kind="review",
            ),
            Rule(
                "automation_limits",
                "1",
                "Review refunds above configured automated limits",
                limits,
                config,
                kind="review",
            ),
        ],
        finalize=pack.evaluate,
    )
    return replace(pack, version="2", policy_version=config.version + "-rules-v2", evaluate=rules)


__all__ = ["RefundExecutor", "refund_domain"]


def refund_preparation():
    """Reuse checks independent of assessment/resource state; retain model intake comparison."""
    from ...core.preparation import PreparationSpec

    return PreparationSpec(
        name="refund-preparation",
        mandatory_rules=["payment_binding", "refund_eligibility"],
    )
