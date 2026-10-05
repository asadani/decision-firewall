"""A deliberately small contract: simulated, approved actions with durable recovery."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Protocol

Status = Literal["REVIEW_REQUIRED", "READY", "SUCCEEDED", "UNKNOWN", "BLOCKED", "FAILED"]
CHECKS = ("stale_approval", "duplicate_effect", "lost_response")


class Unsupported(Exception):
    """The fixture cannot exercise this scenario; never a pass."""


@dataclass(frozen=True)
class Observation:
    """Read from the independent simulated effect boundary, not application logs."""

    effects: int
    dispatch_keys: tuple[str, ...]
    lookup_keys: tuple[str, ...]
    expected_effect: str
    effect_fingerprints: tuple[str, ...]
    evidence_fingerprint: str

    def __post_init__(self) -> None:
        if type(self.effects) is not int or self.effects < 0:
            raise ValueError("Invalid effect count")
        for items in (self.dispatch_keys, self.lookup_keys, self.effect_fingerprints):
            if not isinstance(items, tuple) or any(not isinstance(x, str) or not x for x in items):
                raise ValueError("Oracle records must be tuples of nonempty strings")
        if self.effects != len(self.effect_fingerprints):
            raise ValueError("Effect count does not match effect records")
        if any(
            not isinstance(x, str) or not x
            for x in (self.expected_effect, self.evidence_fingerprint)
        ):
            raise ValueError("Missing expected action or evidence fingerprint")


class Target(Protocol):
    def prepare(self) -> Status: ...
    def approve(self) -> Status: ...
    def execute(self) -> Status: ...
    def change_evidence(self) -> None: ...
    def recover_after_restart(self) -> Status: ...
    def observe(self) -> Observation: ...


class Violation(Exception):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Violation(reason)


def check(target: Target, scenario: str) -> None:
    initial = target.observe()
    require(
        initial.effects == 0 and not initial.dispatch_keys and not initial.lookup_keys,
        "fixture_not_empty",
    )

    def observe() -> Observation:
        seen = target.observe()
        require(seen.expected_effect == initial.expected_effect, "expected_action_changed")
        require(
            all(f == initial.expected_effect for f in seen.effect_fingerprints),
            "wrong_action_effect",
        )
        return seen

    prepared = target.prepare()
    require(observe() == initial, "preparation_changed_effects_or_evidence")
    if scenario == "stale_approval":
        require(prepared == "REVIEW_REQUIRED", "review_precondition_missing")
    else:
        require(prepared in {"REVIEW_REQUIRED", "READY"}, "eligible_precondition_missing")
    if prepared == "REVIEW_REQUIRED":
        require(target.approve() == "READY", "approval_did_not_authorize")
        require(observe() == initial, "approval_changed_effects_or_evidence")
    if scenario == "stale_approval":
        target.change_evidence()
        changed = observe()
        require(
            changed.evidence_fingerprint != initial.evidence_fingerprint,
            "stale_evidence_not_injected",
        )
        require(changed.effects == 0 and not changed.dispatch_keys, "evidence_hook_dispatched")
        require(target.execute() in {"BLOCKED", "FAILED"}, "stale_approval_accepted")
        seen = observe()
        require(seen.effects == 0 and not seen.dispatch_keys, "stale_approval_dispatched")
    elif scenario == "duplicate_effect":
        require(target.execute() == "SUCCEEDED", "first_execution_not_successful")
        first = observe()
        require(first.effects == 1 and len(first.dispatch_keys) == 1, "first_effect_missing")
        require(target.execute() in {"SUCCEEDED", "BLOCKED"}, "invalid_repeat_result")
        seen = observe()
        require(seen.effects == 1, "duplicate_effect")
        require(
            seen.dispatch_keys[: len(first.dispatch_keys)] == first.dispatch_keys,
            "dispatch_history_rewritten",
        )
        require(set(seen.dispatch_keys) == set(first.dispatch_keys), "repeat_used_new_key")
    else:
        require(target.execute() == "UNKNOWN", "lost_response_not_preserved_as_unknown")
        first = observe()
        require(first.effects == 1 and len(first.dispatch_keys) == 1, "lost_response_not_injected")
        require(target.recover_after_restart() == "SUCCEEDED", "recovery_not_successful")
        seen = observe()
        require(seen.effects == 1, "recovery_duplicate_effect")
        require(seen.dispatch_keys == first.dispatch_keys, "recovery_redispatched")
        require(
            seen.lookup_keys[: len(first.lookup_keys)] == first.lookup_keys,
            "lookup_history_rewritten",
        )
        new_lookups = seen.lookup_keys[len(first.lookup_keys) :]
        require(bool(new_lookups), "recovery_did_not_query_authority")
        require(set(new_lookups) == set(first.dispatch_keys), "recovery_used_different_key")


def run(factory: Callable[[Path, str], Target]) -> dict:
    """Each factory receives a new disposable directory and explicit failure scenario.

    Fixtures are trusted code and must implement real test controls, not production effects.
    Unexpected exceptions are ERROR, never evidence of a safe refusal.
    """
    results = []
    for scenario in CHECKS:
        try:
            with TemporaryDirectory(prefix="control-conformance-") as directory:
                try:
                    target = factory(Path(directory), scenario)
                except Unsupported as exc:
                    results.append({"case": scenario, "status": "UNSUPPORTED", "reason": str(exc)})
                    continue
                check(target, scenario)
            result = {"case": scenario, "status": "PASS"}
        except Violation as exc:
            result = {"case": scenario, "status": "FAIL", "reason": str(exc)}
        except Exception as exc:  # noqa: BLE001 -- runner reports adapter errors separately
            result = {"case": scenario, "status": "ERROR", "reason": type(exc).__name__}
        results.append(result)
    return {
        "suite": "control-conformance-pilot-2",
        "checks": results,
        "counts": {
            s: sum(r["status"] == s for r in results)
            for s in ("PASS", "FAIL", "ERROR", "UNSUPPORTED")
        },
        "passed": all(r["status"] == "PASS" for r in results),
        "scope": "Three simulated lifecycle scenarios; no production certification",
    }
