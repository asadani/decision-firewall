"""The refund reference domain running on the public, domain-neutral runtime."""

from datetime import UTC, datetime
from pathlib import Path

from ...core.contracts import Claim, Context, Decision, Evidence, ExecutionResult, Proposal
from ...core.plugins import DomainPack
from .contracts import Assessment as RefundAssessment
from .contracts import Policy
from .contracts import Proposal as RefundAction
from .policy import evaluate_policy
from .simulator import PaymentSimulator


class RefundExecutor:
    name = "simulated-refunds"
    version = "1"
    supported_constraints = frozenset({"original_destination", "exact_amount", "single_use"})

    def __init__(self, payments: PaymentSimulator, mode="success"):
        self.payments, self.mode = payments, mode

    def execute(self, key: str, proposal: Proposal, evidence: Evidence) -> ExecutionResult:
        action = {
            k: proposal.action[k] for k in ("payment_id", "amount_minor", "currency", "destination")
        }
        try:
            status = self.payments.execute(
                key, action, self.mode, expected_version=int(evidence.versions["payment"])
            )
        except ValueError as exc:
            return ExecutionResult(status="FAILED", detail={"reason": str(exc)})
        return ExecutionResult.model_validate(
            {"status": "UNKNOWN" if status == "PENDING" else status}
        )

    def reconcile(self, key: str) -> ExecutionResult:
        status = self.payments.lookup(key)
        # Local ledger absence is authoritative while the governance dispatch lock is held.
        return ExecutionResult.model_validate(
            {"status": "UNKNOWN" if status == "PENDING" else status or "FAILED"}
        )


def refund_domain(
    home: str | Path, *, policy: Policy | None = None, mode: str = "success"
) -> DomainPack:
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    payments = PaymentSimulator(home)
    policy = policy or Policy()

    def resolve(proposal: Proposal) -> Evidence:
        payment = payments.get(str(proposal.action["payment_id"]))
        return Evidence(
            facts={"payment": payment},
            versions={"payment": str(payment["version"])} if payment else {},
            missing=[] if payment else ["payment_not_found"],
        )

    def evaluate(context: Context) -> Decision:
        signal = context.assessment.signals.get("request_type")
        label = signal.value if signal else "unavailable"
        assessment = RefundAssessment.model_validate(
            {
                "provider": context.assessment.provider,
                "model": context.assessment.model,
                "revision": context.assessment.revision,
                "request_type": label,
            }
        )
        day = datetime.fromtimestamp(context.now, UTC).date().isoformat()
        balance_key = "payment:" + str(context.proposal.action["payment_id"])
        budget_key = "auto-budget:" + day
        review = context.review.decision if context.review else None
        old_context = {
            "proposal": context.proposal.action,
            "assessment": assessment.model_dump(),
            "payment": context.evidence.facts["payment"],
            "policy": policy.model_dump(),
            "reserved_minor": context.usage.get(balance_key, 0),
            "daily_used_minor": context.usage.get(budget_key, 0),
            "requester_active": True,
            "review": review,
        }
        result = evaluate_policy(old_context)
        claims = []
        if result.disposition in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and not result.errors:
            payment = context.evidence.facts["payment"]
            assert isinstance(payment, dict)
            action = RefundAction.model_validate(context.proposal.action)
            from .contracts import Payment

            record = Payment.model_validate(payment)
            claims.append(
                Claim(
                    key=balance_key,
                    units=action.amount_minor,
                    capacity=record.amount_minor - record.refunded_minor,
                )
            )
            if review != "approve":
                claims.append(
                    Claim(
                        key=budget_key,
                        units=action.amount_minor,
                        capacity=policy.daily_auto_limit_minor,
                        retain_on_success=True,
                        on_exhausted="REQUIRE_REVIEW",
                    )
                )
        return Decision.model_validate(
            {**result.model_dump(), "claims": [c.model_dump() for c in claims]}
        )

    return DomainPack(
        name="refunds",
        version="1",
        policy_version=policy.version,
        action_schema=RefundAction,
        resolve=resolve,
        evaluate=evaluate,
        executor=RefundExecutor(payments, mode),
        policy_config=policy.model_dump(),
        authorization_seconds=policy.authorization_seconds,
    )
