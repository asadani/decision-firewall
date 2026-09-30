"""Third-domain checks; no model, network or core business-logic changes."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.core import Review, verify_receipt
from decision_firewall.core.audit import connect
from decision_firewall.core.runtime import FirewallError
from decision_firewall.domains.deployments.pack import DeploymentSimulator, deployment_domain

ARTIFACT = "sha256:" + "a" * 64


def setup(home, *, mode="success", environment="staging", clock=None):
    ledger = DeploymentSimulator(home, mode=mode)
    ledger.register(
        "artifact",
        ARTIFACT,
        {
            "service": "orders",
            "approved": True,
            "environments": ["staging", "production"],
        },
    )
    ledger.register("environment", environment, {"enabled": True})
    fw = DecisionFirewall(
        home, [deployment_domain(home, mode=mode)], **({"clock": clock} if clock else {})
    )
    proposal = Proposal(
        domain="deployments",
        message="Deploy reviewed release",
        action={"service": "orders", "artifact": ARTIFACT, "environment": environment},
    )
    assessment = Assessment(provider="fixture", model="structured", revision="1")
    rid = fw.submit(proposal, assessment)
    return fw, ledger, rid, proposal, assessment


def test_production_review_receipt_replay(tmp_path):
    fw, _, rid, _, _ = setup(tmp_path, environment="production")
    seen = fw.evaluate(rid)
    assert seen["result"]["disposition"] == "REQUIRE_REVIEW"
    result = fw.review(
        rid,
        Review(decision="approve", reason="Release approved"),
        revision=1,
        evaluation_id=seen["evaluation_id"],
    )
    assert fw.execute(result["authorization"])["status"] == "SUCCEEDED"
    assert fw.replay(result["evaluation_id"])["matches"]
    assert verify_receipt(fw.receipt(), fw.store.public)


@pytest.mark.parametrize("change", ["unapproved", "service", "environment", "frozen", "missing"])
def test_review_cannot_waive_registry_restrictions(tmp_path, change):
    fw, ledger, rid, proposal, assessment = setup(tmp_path, environment="production")
    seen = fw.evaluate(rid)
    assert seen["result"]["disposition"] == "REQUIRE_REVIEW"
    if change == "frozen":
        ledger.register("environment", "production", {"enabled": False})
    elif change == "missing":
        proposal = proposal.model_copy(
            update={"action": {**proposal.action, "artifact": "sha256:" + "b" * 64}}
        )
        rid = fw.submit(proposal, assessment)
        seen = fw.evaluate(rid)
        assert seen["result"]["disposition"] == "REQUIRE_EVIDENCE"
    else:
        ledger.register(
            "artifact",
            ARTIFACT,
            {
                "service": "other" if change == "service" else "orders",
                "approved": change != "unapproved",
                "environments": ["staging"] if change == "environment" else ["production"],
            },
        )
    if change != "missing":
        with pytest.raises(FirewallError, match="snapshot changed"):
            fw.review(
                rid,
                Review(decision="approve", reason="Attempt override"),
                revision=1,
                evaluation_id=seen["evaluation_id"],
            )
        result = fw.evaluate(rid)
    else:
        result = fw.review(
            rid,
            Review(decision="approve", reason="Attempt override"),
            revision=1,
            evaluation_id=seen["evaluation_id"],
        )
    assert result["authorization"] is None
    assert result["result"]["disposition"] == (
        "REQUIRE_EVIDENCE" if change == "missing" else "DENY"
    )


@pytest.mark.parametrize("change", ["expired", "registry", "revision", "revoked"])
def test_stale_authorization(tmp_path, change):
    now = [1000.0]
    fw, ledger, rid, proposal, assessment = setup(tmp_path, clock=lambda: now[0])
    token = fw.evaluate(rid)["authorization"]
    if change == "expired":
        now[0] += 121
    elif change == "registry":
        ledger.register("environment", "staging", {"enabled": False})
    elif change == "revision":
        fw.revise(rid, proposal.model_copy(update={"message": "Changed release"}), assessment)
    else:
        fw.revoke(token["payload"]["id"])
    with pytest.raises(FirewallError):
        fw.execute(token)
    with closing(connect(ledger.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM deployments").fetchone()[0] == 0


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("success", "SUCCEEDED"),
        ("fail", "FAILED"),
        ("delayed", "UNKNOWN"),
        ("response_loss", "UNKNOWN"),
    ],
)
def test_restart_and_exactly_one_record(tmp_path, mode, expected):
    fw, ledger, rid, _, _ = setup(tmp_path, mode=mode)
    token = fw.evaluate(rid)["authorization"]
    result = fw.execute(token)
    assert result["status"] == expected
    restarted = DecisionFirewall(tmp_path, [deployment_domain(tmp_path)])
    if expected == "UNKNOWN":
        if mode == "delayed":
            assert restarted.reconcile(token["payload"]["id"])["status"] == "UNKNOWN"
            ledger.settle(result["attempt_id"])
        assert restarted.reconcile(token["payload"]["id"])["status"] == "SUCCEEDED"
    with pytest.raises(FirewallError):
        restarted.execute(token)
    with closing(connect(ledger.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM deployments").fetchone()[0] == 1


def test_pending_deployment_reserves_slot_until_reconciliation(tmp_path):
    fw, ledger, rid, proposal, assessment = setup(tmp_path, mode="delayed")
    other = fw.submit(proposal, assessment)
    tokens = [fw.evaluate(item)["authorization"] for item in (rid, other)]

    def execute(token):
        try:
            return fw.execute(token)
        except FirewallError:
            return {"status": "BLOCKED"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, tokens))
    assert sorted(r["status"] for r in results) == ["BLOCKED", "UNKNOWN"]
    index = next(i for i, r in enumerate(results) if r["status"] == "UNKNOWN")
    assert fw.reconcile(tokens[index]["payload"]["id"])["status"] == "UNKNOWN"
    blocked = (rid, other)[1 - index]
    assert fw.evaluate(blocked)["authorization"] is None
    ledger.settle(results[index]["attempt_id"])
    assert fw.reconcile(tokens[index]["payload"]["id"])["status"] == "SUCCEEDED"
    assert fw.evaluate(blocked)["authorization"] is not None


def test_executor_rechecks_atomic_registry_snapshot_and_idempotency(tmp_path):
    _, ledger, _, proposal, _ = setup(tmp_path)
    evidence = ledger.resolve(proposal)
    ledger.register("environment", "staging", {"enabled": False})
    assert ledger.execute("key", proposal, evidence).status == "FAILED"
    ledger.register("environment", "staging", {"enabled": True})
    assert ledger.execute("key", proposal, ledger.resolve(proposal)).status == "FAILED"
    changed = proposal.model_copy(update={"message": "Different payload"})
    with pytest.raises(ValueError, match="Idempotency"):
        ledger.execute("key", changed, ledger.resolve(changed))


def test_crash_before_dispatch_releases_only_after_authoritative_lookup(tmp_path):
    fw, _, rid, _, _ = setup(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    with pytest.raises(RuntimeError):
        fw.execute(token, crash_after_reserve=True)
    restarted = DecisionFirewall(tmp_path, [deployment_domain(tmp_path)])
    assert restarted.reconcile(token["payload"]["id"])["status"] == "FAILED"
    assert restarted.evaluate(rid)["authorization"] is not None


def test_change_after_runtime_revalidation_is_blocked_by_executor(tmp_path, monkeypatch):
    fw, ledger, rid, _, _ = setup(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    executor = fw.domains["deployments"].executor
    original = executor.execute

    def freeze_before_commit(key, proposal, evidence):
        ledger.register("environment", "staging", {"enabled": False})
        return original(key, proposal, evidence)

    monkeypatch.setattr(executor, "execute", freeze_before_commit)
    assert fw.execute(token)["status"] == "FAILED"
    with closing(connect(ledger.path)) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM deployments WHERE status='SUCCEEDED'").fetchone()[0]
            == 0
        )


def test_downstream_also_serializes_pending_jobs(tmp_path):
    _, ledger, _, proposal, _ = setup(tmp_path, mode="delayed")
    evidence = ledger.resolve(proposal)
    assert ledger.execute("first", proposal, evidence).status == "UNKNOWN"
    assert ledger.execute("second", proposal, evidence).status == "FAILED"
    ledger.settle("first")
    # A definitively failed key never becomes a new effect after the slot frees.
    assert ledger.execute("second", proposal, evidence).status == "FAILED"
    assert ledger.execute("third", proposal, evidence).status == "UNKNOWN"
