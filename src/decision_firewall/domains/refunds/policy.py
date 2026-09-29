"""Pure deterministic evaluator; inputs are persisted for historical replay."""

from .contracts import Assessment, Evaluation, Payment, Policy, Proposal
from .contracts import Disposition as D


def evaluate_policy(context: dict) -> Evaluation:
    try:
        p = Proposal.model_validate(context["proposal"])
        a = Assessment.model_validate(context["assessment"])
        policy = Policy.model_validate(context["policy"])
        raw = context["payment"]
        if raw is None:
            return Evaluation(disposition=D.REQUIRE_EVIDENCE, reasons=["payment_not_found"])
        evidence = Payment.model_validate(raw)
        if p.customer_id != evidence.customer_id:
            return Evaluation(disposition=D.DENY, reasons=["customer_mismatch"])
        if p.destination != evidence.destination or p.currency != evidence.currency:
            return Evaluation(disposition=D.DENY, reasons=["destination_or_currency_mismatch"])
        remaining = evidence.amount_minor - evidence.refunded_minor - context["reserved_minor"]
        if p.amount_minor > remaining:
            return Evaluation(disposition=D.DENY, reasons=["exceeds_refundable_balance"])
        if not context["requester_active"]:
            return Evaluation(disposition=D.DENY, reasons=["requester_revoked"])
        review = context.get("review")
        if review == "reject":
            return Evaluation(disposition=D.DENY, reasons=["review_rejected"])
        if review == "request_evidence":
            return Evaluation(disposition=D.REQUIRE_EVIDENCE, reasons=["review_requested_evidence"])
        if a.request_type == "unavailable":
            return Evaluation(disposition=D.REQUIRE_REVIEW, reasons=["assessment_unavailable"])
        if p.requested_reason == "duplicate":
            if evidence.duplicate_verified is None:
                return Evaluation(
                    disposition=D.REQUIRE_EVIDENCE, reasons=["duplicate_evidence_missing"]
                )
            if not evidence.duplicate_verified:
                return Evaluation(disposition=D.DENY, reasons=["duplicate_not_verified"])
        elif p.requested_reason == "cancellation":
            if evidence.age_days is None or evidence.unused is None:
                return Evaluation(disposition=D.REQUIRE_EVIDENCE, reasons=["usage_or_age_missing"])
            if evidence.age_days > policy.cancellation_days or not evidence.unused:
                return Evaluation(disposition=D.DENY, reasons=["cancellation_ineligible"])
        elif review != "approve":
            return Evaluation(
                disposition=D.REQUIRE_REVIEW, reasons=["manual_eligibility_assessment"]
            )
        if a.request_type != p.requested_reason and review != "approve":
            return Evaluation(
                disposition=D.REQUIRE_REVIEW, reasons=["assessment_intake_disagreement"]
            )
        reasons = []
        if p.amount_minor > policy.auto_amount_minor:
            reasons.append("above_automatic_amount")
        if context["daily_used_minor"] + p.amount_minor > policy.daily_auto_limit_minor:
            reasons.append("daily_automatic_limit")
        if reasons and review != "approve":
            return Evaluation(disposition=D.REQUIRE_REVIEW, reasons=reasons)
        return Evaluation(
            disposition=D.ALLOW_WITH_CONSTRAINTS,
            reasons=["review_approved" if review == "approve" else "eligible"],
            constraints=["original_destination", "exact_amount", "single_use"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        return Evaluation(disposition=None, reasons=[], errors=[f"evaluation_error: {exc}"])
