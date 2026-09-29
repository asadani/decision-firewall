"""Non-financial example: temporary access requests, simulated grants only."""

from pathlib import Path

from pydantic import Field

from ...adapters.simulator import SimulatedExecutor
from ...core.contracts import Context, Decision, Disposition, Evidence, Record
from ...core.plugins import DomainPack


class AccessAction(Record):
    employee: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    hours: int = Field(gt=0, le=168, strict=True)


def access_domain(
    home: str | Path, *, directory: dict | None = None, mode: str = "success"
) -> DomainPack:
    # Application-owned trusted directory, not model-supplied claims.
    directory = (
        directory
        if directory is not None
        else {"alice": {"active": True, "resources": ["engineering-docs"], "version": 1}}
    )

    def resolve(proposal):
        entry = directory.get(proposal.action["employee"])
        return Evidence(
            facts={"employee": entry},
            versions={"directory": str(entry["version"])} if entry else {},
            missing=[] if entry else ["employee_record_missing"],
        )

    def evaluate(context: Context) -> Decision:
        action = AccessAction.model_validate(context.proposal.action)
        entry = context.evidence.facts["employee"]
        assert isinstance(entry, dict)
        resources = entry["resources"]
        assert isinstance(resources, list)
        if not entry["active"] or action.resource not in resources:
            return Decision(disposition=Disposition.DENY, reasons=["directory_prohibits_access"])
        if action.hours > 8 and not (context.review and context.review.decision == "approve"):
            return Decision(
                disposition=Disposition.REQUIRE_REVIEW, reasons=["extended_access_requires_review"]
            )
        return Decision(
            disposition=Disposition.ALLOW_WITH_CONSTRAINTS,
            reasons=["directory_permits_access"],
            constraints=["exact_action", "single_use"],
        )

    return DomainPack(
        name="access",
        version="1",
        policy_version="access-demo-v1",
        action_schema=AccessAction,
        resolve=resolve,
        evaluate=evaluate,
        executor=SimulatedExecutor(Path(home) / "access-effects.db", mode=mode),
        policy_config={"automatic_max_hours": 8, "simulated": True},
    )
