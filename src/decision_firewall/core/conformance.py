"""Reusable simulated-adapter checks. Factories and oracles are trusted test code."""

import platform
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .audit import verify_receipt
from .contracts import Assessment, Proposal, Review
from .plugins import DomainPack
from .runtime import DecisionFirewall, FirewallError


@dataclass
class ConformanceFixture:
    domain: DomainPack
    proposal: Proposal
    assessment: Assessment
    effects: Callable[[], int]
    restart: Callable[[], DomainPack]
    deny: Callable[[], None] | None = None
    missing: Callable[[], None] | None = None
    stale: Callable[[], None] | None = None
    settle: Callable[[str], None] | None = None
    resource_contention: bool = False


CHECKS = (
    "success",
    "duplicate",
    "tampered",
    "expired",
    "revoked",
    "deny",
    "missing",
    "stale",
    "review",
    "review_cannot_override",
    "failure",
    "response_loss",
    "delayed",
    "crash_before_dispatch",
    "receipt_replay",
    "adapter_idempotency",
    "resource_contention",
)


class ConformanceFailure(Exception):
    """A failed harness assertion with a safe diagnostic message."""


def require(condition, message):
    if not condition:
        raise ConformanceFailure(message)


def run_conformance(factory: Callable[[Path, str], ConformanceFixture]) -> dict:
    """Factory(home, scenario) must create fresh simulated data, or raise NotImplementedError.

    No existing application directory is accepted. Effects are asserted through the
    supplied authoritative oracle, not inferred from the framework's own status.
    """
    results = []
    fingerprints: set[str] = set()
    for check in CHECKS:
        try:
            with TemporaryDirectory(prefix="firewall-conformance-") as directory:
                home = Path(directory)
                try:
                    fixture = factory(home, check)
                except NotImplementedError:
                    results.append({"check": check, "status": "UNSUPPORTED"})
                    continue
                fingerprints.add(fixture.domain.fingerprint)
                now = [1000.0]
                fw = DecisionFirewall(home, [fixture.domain], clock=lambda now=now: now[0])
                require(fixture.effects() == 0, "Fixture must start without effects")
                rid = fw.submit(fixture.proposal, fixture.assessment)
                if check == "resource_contention":
                    if not fixture.resource_contention or fixture.settle is None:
                        results.append({"check": check, "status": "UNSUPPORTED"})
                        continue
                    other = fw.submit(fixture.proposal, fixture.assessment)
                    tokens = [fw.evaluate(item)["authorization"] for item in (rid, other)]
                    require(all(tokens), "Both resource requests must initially be eligible")

                    def dispatch(token, fw=fw):
                        try:
                            return fw.execute(token)
                        except FirewallError:
                            return {"status": "BLOCKED"}

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        outcomes = list(pool.map(dispatch, tokens))
                    require(
                        sorted(o["status"] for o in outcomes) == ["BLOCKED", "UNKNOWN"],
                        "Contention must admit only one unresolved action",
                    )
                    winner = next(i for i, o in enumerate(outcomes) if o["status"] == "UNKNOWN")
                    restarted = DecisionFirewall(
                        home, [fixture.restart()], clock=lambda now=now: now[0]
                    )
                    require(
                        restarted.reconcile(tokens[winner]["payload"]["id"])["status"] == "UNKNOWN",
                        "Unknown action resolved prematurely",
                    )
                    require(
                        restarted.evaluate((rid, other)[1 - winner])["authorization"] is None,
                        "Unknown action released resource reservation",
                    )
                    fixture.settle(outcomes[winner]["attempt_id"])
                    require(
                        restarted.reconcile(tokens[winner]["payload"]["id"])["status"]
                        == "SUCCEEDED",
                        "Settlement did not reconcile",
                    )
                    require(fixture.effects() == 1, "Contention produced duplicate effects")
                    results.append({"check": check, "status": "PASS"})
                    continue
                if check == "adapter_idempotency":
                    executor = fixture.domain.executor
                    evidence = fixture.domain.resolve(fixture.proposal)
                    for _ in range(2):
                        require(
                            executor.execute("same-key", fixture.proposal, evidence).status
                            == "SUCCEEDED",
                            "Adapter retry not idempotent",
                        )
                    require(fixture.effects() == 1, "Adapter retry duplicated effects")
                    changed = fixture.proposal.model_copy(update={"message": "Changed payload"})
                    try:
                        rejected = executor.execute("same-key", changed, evidence)
                    except ValueError:
                        require(fixture.effects() == 1, "Rejected conflict changed effect count")
                    else:
                        require(
                            rejected.status == "FAILED", "Adapter accepted key with changed payload"
                        )
                    require(fixture.effects() == 1, "Conflicting key produced another effect")
                    results.append({"check": check, "status": "PASS"})
                    continue
                hook_name = {
                    "deny": "deny",
                    "missing": "missing",
                    "stale": "stale",
                    "review_cannot_override": "deny",
                }.get(check)
                hook = getattr(fixture, hook_name) if hook_name else None
                if hook_name and hook is None:
                    results.append({"check": check, "status": "UNSUPPORTED"})
                    continue
                if check in {"deny", "missing"}:
                    assert hook is not None
                    hook()
                    result = fw.evaluate(rid)
                    expected = "DENY" if check == "deny" else "REQUIRE_EVIDENCE"
                    require(result["result"]["disposition"] == expected, "Wrong disposition")
                    require(result["authorization"] is None, "Blocked case issued authority")
                else:
                    result = fw.evaluate(rid)
                    if check in {"review", "review_cannot_override"}:
                        require(
                            result["result"]["disposition"] == "REQUIRE_REVIEW",
                            "Fixture must require review",
                        )
                        if hook:
                            hook()
                        result = fw.review(
                            rid, Review(decision="approve", reason="Test approval"), revision=1
                        )
                        if check == "review_cannot_override":
                            require(result["authorization"] is None, "Approval waived hard rule")
                    if check != "review_cannot_override":
                        token = result["authorization"]
                        require(token is not None, "Eligible fixture must issue authority")
                        if check in {"tampered", "expired", "revoked", "stale"}:
                            if check == "tampered":
                                token["payload"]["executor"] = "unauthorized"
                            elif check == "expired":
                                now[0] += fixture.domain.authorization_seconds + 1
                            elif check == "revoked":
                                fw.revoke(token["payload"]["id"])
                            else:
                                assert hook is not None
                                hook()
                            try:
                                fw.execute(token)
                            except FirewallError:
                                pass
                            else:
                                raise ConformanceFailure("Invalid authorization was dispatched")
                        elif check == "crash_before_dispatch":
                            try:
                                fw.execute(token, crash_after_reserve=True)
                            except RuntimeError:
                                pass
                            restarted = DecisionFirewall(
                                home, [fixture.restart()], clock=lambda now=now: now[0]
                            )
                            require(
                                restarted.reconcile(token["payload"]["id"])["status"] == "FAILED",
                                "Absent synchronous dispatch must resolve as failed",
                            )
                        else:
                            outcome = fw.execute(token)
                            expected = (
                                "FAILED"
                                if check == "failure"
                                else "UNKNOWN"
                                if check in {"response_loss", "delayed"}
                                else "SUCCEEDED"
                            )
                            require(outcome["status"] == expected, "Wrong execution status")
                            if check in {"response_loss", "delayed"}:
                                restarted = DecisionFirewall(
                                    home, [fixture.restart()], clock=lambda now=now: now[0]
                                )
                                if check == "delayed":
                                    require(
                                        restarted.reconcile(token["payload"]["id"])["status"]
                                        == "UNKNOWN",
                                        "Ambiguous outcome released prematurely",
                                    )
                                    require(
                                        fixture.settle is not None,
                                        "Delayed fixture needs settlement",
                                    )
                                    assert fixture.settle is not None
                                    fixture.settle(outcome["attempt_id"])
                                require(
                                    restarted.reconcile(token["payload"]["id"])["status"]
                                    == "SUCCEEDED",
                                    "Original execution did not reconcile",
                                )
                            if check == "duplicate":
                                try:
                                    fw.execute(token)
                                except FirewallError:
                                    pass
                                else:
                                    raise ConformanceFailure("Consumed authorization reused")
                            if check == "receipt_replay":
                                require(
                                    fw.replay(result["evaluation_id"])["matches"], "Replay mismatch"
                                )
                                require(
                                    verify_receipt(fw.receipt(), fw.store.public), "Receipt failed"
                                )
                effects = (
                    1
                    if check
                    in {
                        "success",
                        "duplicate",
                        "review",
                        "response_loss",
                        "delayed",
                        "receipt_replay",
                    }
                    else 0
                )
                require(fixture.effects() == effects, "Authoritative effect count mismatch")
                results.append({"check": check, "status": "PASS"})
        except Exception as exc:  # noqa: BLE001 -- retain failures and continue other checks
            results.append(
                {
                    "check": check,
                    "status": "FAIL",
                    "error_type": type(exc).__name__,
                    "reason": str(exc)
                    if isinstance(exc, ConformanceFailure)
                    else "Fixture or runtime raised; inspect the local test implementation",
                }
            )
    counts = {
        status: sum(r["status"] == status for r in results)
        for status in ("PASS", "FAIL", "UNSUPPORTED")
    }
    return {
        "schema_version": 1,
        "suite_version": "1",
        "python": platform.python_version(),
        "platform": platform.system(),
        "domain_fingerprints": sorted(fingerprints),
        "checks": results,
        "counts": counts,
        "passed": counts["FAIL"] == 0 and counts["UNSUPPORTED"] == 0,
        "scope": "Simulated lifecycle checks; trusted fixture/oracle, not production certification",
    }
