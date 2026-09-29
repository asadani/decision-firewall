"""Named access rules; v0.2 implementation remains available in pack_v1."""

from dataclasses import replace
from pathlib import Path

from pydantic import Field

from ...core.contracts import Decision, Disposition, Record
from ...core.rules import Rule, RuleResult, RuleSet
from .pack_v1 import AccessAction
from .pack_v1 import access_domain as access_domain_v1


class AccessPolicy(Record):
    automatic_max_hours: int = Field(default=8, ge=0, le=168)


def access_domain(
    home: str | Path,
    *,
    directory: dict | None = None,
    mode="success",
    policy: AccessPolicy | None = None,
):
    pack = access_domain_v1(home, directory=directory, mode=mode)
    config = policy or AccessPolicy()

    def restrictions(context, config):
        action = AccessAction.model_validate(context.proposal.action)
        employee = context.evidence.facts["employee"]
        if not employee["active"] or action.resource not in employee["resources"]:
            return RuleResult(status="deny", reasons=["directory_prohibits_access"])
        return RuleResult()

    def duration(context, config):
        if context.proposal.action["hours"] > config.automatic_max_hours:
            return RuleResult(status="review", reasons=["extended_access_requires_review"])
        return RuleResult()

    rules = RuleSet(
        [
            Rule(
                "directory_access",
                "1",
                "Employee must be active and resource permitted",
                restrictions,
                config,
            ),
            Rule(
                "access_duration",
                "1",
                "Extended duration requires review",
                duration,
                config,
                kind="review",
            ),
        ],
        finalize=lambda context: Decision(
            disposition=Disposition.ALLOW_WITH_CONSTRAINTS,
            reasons=["directory_permits_access"],
            constraints=["exact_action", "single_use"],
        ),
    )
    return replace(
        pack,
        version="2",
        policy_version="access-demo-v2",
        evaluate=rules,
        policy_config={**config.model_dump(), "simulated": True},
    )


__all__ = ["AccessAction", "AccessPolicy", "access_domain"]


def access_preparation(*, structured: bool = False):
    """Explicit host opt-in: structured access actions need no language classification."""
    from ...core.contracts import Assessment, Signal
    from ...core.preparation import PreparationSpec

    return PreparationSpec(
        name="access-preparation",
        mandatory_rules=["directory_access"],
        deterministic_assessment=Assessment(
            provider="deterministic",
            model="structured-access",
            revision="1",
            signals={"intent": Signal(kind="choice", value="access")},
        )
        if structured
        else None,
    )
