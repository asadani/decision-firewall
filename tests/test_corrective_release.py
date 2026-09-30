"""Independent-review regressions; assertions target core, not downstream defenses."""

from dataclasses import replace

import pytest

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.core import (
    Claim,
    Decision,
    Disposition,
    ExecutionResult,
    Review,
    RuntimeIdentity,
)
from decision_firewall.core.audit import connect, verify_receipt
from decision_firewall.core.runtime import FirewallError
from decision_firewall.domains.access.pack import access_domain


def fixture(home, *, hours=24, mode="success"):
    directory = {"alice": {"active": True, "resources": ["docs"], "version": 1}}
    pack = access_domain(home, directory=directory, mode=mode)
    now = [1000.0]
    fw = DecisionFirewall(home, [pack], clock=lambda: now[0])
    p = Proposal(
        domain="access",
        message="Review access",
        action={
            "employee": "alice",
            "resource": "docs",
            "hours": hours,
        },
    )
    a = Assessment(provider="fixture", model="test", revision="1")
    rid = fw.submit(p, a)
    return fw, rid, pack, directory, now, p, a


def approve(fw, rid):
    seen = fw.evaluate(rid)
    return fw.review(
        rid,
        Review(decision="approve", reason="Inspected snapshot"),
        revision=1,
        evaluation_id=seen["evaluation_id"],
    )


@pytest.mark.parametrize("change", ["evidence", "missing_id", "superseded", "wrong_request"])
def test_approval_requires_exact_inspected_evaluation(tmp_path, change):
    fw, rid, _, directory, _, p, a = fixture(tmp_path)
    seen = fw.evaluate(rid)
    eid = seen["evaluation_id"]
    if change == "evidence":
        directory["alice"]["version"] = 2
    elif change == "missing_id":
        eid = None
    elif change == "superseded":
        fw.evaluate(rid)
    else:
        eid = fw.evaluate(fw.submit(p, a))["evaluation_id"]
    with pytest.raises(FirewallError):
        fw.review(
            rid,
            Review(decision="approve", reason="Viewed old facts"),
            revision=1,
            evaluation_id=eid,
        )
    assert not fw.detail(rid)["executions"]
    assert not any(e["kind"] == "review_recorded" for e in fw.detail(rid)["events"])


@pytest.mark.parametrize("change", ["deactivate", "generation", "expiry", "evidence_restored"])
def test_rejection_never_resurrects_prior_approval(tmp_path, change):
    fw, rid, pack, directory, now, p, a = fixture(tmp_path)
    prior = approve(fw, rid)
    fw.revoke(prior["authorization"]["payload"]["id"])
    directory["alice"]["version"] = 2
    fw.evaluate(rid)
    fw.configure_identity("bob", "reviewer")
    bob = DecisionFirewall(
        tmp_path, [pack], identity=RuntimeIdentity(reviewer="bob"), clock=lambda: now[0]
    )
    assert (
        bob.review(rid, Review(decision="reject", reason="Access rejected"), revision=1)["result"][
            "disposition"
        ]
        == "DENY"
    )
    directory["alice"]["version"] = 1
    if change == "deactivate":
        fw.configure_identity("bob", "reviewer", active=False)
    elif change == "generation":
        fw.configure_identity("bob", "reviewer")
    elif change == "expiry":
        now[0] += 4000
    result = fw.evaluate(rid)
    assert result["result"]["disposition"] == "DENY"
    assert result["authorization"] is None
    assert fw.revise(rid, p, a) == 2
    assert fw.evaluate(rid)["result"]["disposition"] == "REQUIRE_REVIEW"


@pytest.mark.parametrize("change", ["evidence", "expiry", "generation"])
def test_approval_invalidated_before_new_permit(tmp_path, change):
    fw, rid, _, directory, now, _, _ = fixture(tmp_path)
    approve(fw, rid)
    if change == "evidence":
        directory["alice"]["version"] = 2
    elif change == "expiry":
        now[0] += 3601
    else:
        fw.configure_identity("reviewer", "reviewer")
    result = fw.evaluate(rid)
    assert result["result"]["disposition"] == "REQUIRE_REVIEW"
    assert result["authorization"] is None


def test_core_second_validation_prevents_dispatch(tmp_path):
    fw, rid, pack, _, _, _, _ = fixture(tmp_path, hours=4)
    calls = [0]

    def resolve(proposal):
        calls[0] += 1
        ev = pack.resolve(proposal)
        return ev.model_copy(update={"versions": {"directory": str(calls[0] >= 3)}})

    fw.domains["access"] = replace(pack, resolve=resolve)
    token = fw.evaluate(rid)["authorization"]
    assert fw.execute(token)["status"] == "FAILED"
    db = connect(pack.executor.path)
    try:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone()[0] == 0
    finally:
        db.close()


def test_reconcile_requires_original_pack(tmp_path):
    fw, rid, pack, _, _, _, _ = fixture(tmp_path, hours=4, mode="response_loss")
    token = fw.evaluate(rid)["authorization"]
    assert fw.execute(token)["status"] == "UNKNOWN"
    fw.domains["access"] = replace(pack, policy_version="changed")
    with pytest.raises(FirewallError, match="original"):
        fw.reconcile(token["payload"]["id"])


def test_evaluation_refuses_unresolved_execution(tmp_path):
    fw, rid, _, _, _, _, _ = fixture(tmp_path, hours=4, mode="response_loss")
    token = fw.evaluate(rid)["authorization"]
    assert fw.execute(token)["status"] == "UNKNOWN"
    with pytest.raises(FirewallError, match="existing execution"):
        fw.evaluate(rid)


@pytest.mark.parametrize("invalid", ["expired", "revoked"])
def test_invalid_permit_does_not_dispatch(tmp_path, invalid):
    fw, rid, pack, _, now, _, _ = fixture(tmp_path, hours=4)
    token = fw.evaluate(rid)["authorization"]
    if invalid == "expired":
        now[0] += pack.authorization_seconds + 1
    else:
        fw.revoke(token["payload"]["id"])
    with pytest.raises(FirewallError):
        fw.execute(token)


def test_unknown_claims_remain_reserved(tmp_path):
    fw, rid, pack, _, _, p, a = fixture(tmp_path, hours=4, mode="delayed")
    fw.domains["access"] = replace(
        pack,
        evaluate=lambda _: Decision(
            disposition=Disposition.ALLOW, claims=[Claim(key="slot", units=1, capacity=1)]
        ),
    )
    token = fw.evaluate(rid)["authorization"]
    assert fw.execute(token)["status"] == "UNKNOWN"
    assert fw.evaluate(fw.submit(p, a))["authorization"] is None


@pytest.mark.parametrize("response_loss", [False, True])
def test_large_adapter_integer_does_not_wedge_effect(tmp_path, response_loss):
    fw, rid, pack, _, _, _, _ = fixture(
        tmp_path, hours=4, mode="response_loss" if response_loss else "success"
    )
    original_execute, original_reconcile = pack.executor.execute, pack.executor.reconcile
    detail = {"ids": [2**60 + 7, -(2**60 + 7)], "safe": 2**53 - 1, "flag": True}

    def execute(*args):
        return original_execute(*args).model_copy(update={"detail": detail})

    def reconcile(key):
        return original_reconcile(key).model_copy(update={"detail": detail})

    pack.executor.execute, pack.executor.reconcile = execute, reconcile
    token = fw.evaluate(rid)["authorization"]
    result = fw.execute(token)
    if response_loss:
        assert result["status"] == "UNKNOWN"
        restarted = DecisionFirewall(tmp_path, [pack])
        result = restarted.reconcile(token["payload"]["id"])
    assert result["status"] == "SUCCEEDED"
    assert result["detail"]["value"]["ids"] == [str(2**60 + 7), str(-(2**60 + 7))]
    assert result["detail"]["integer_paths"] == [["ids", 0], ["ids", 1]]
    assert fw.detail(rid)["status"] == "COMPLETED"
    assert verify_receipt(fw.receipt(), fw.store.public)
    with pytest.raises(FirewallError):
        fw.execute(token)


def test_unencodable_detail_is_explicitly_omitted():
    from decision_firewall.core.outcomes import audit_outcome

    result = audit_outcome(ExecutionResult(status="FAILED", detail={"bad": "\ud800"}))
    assert result.status == "FAILED"
    assert result.detail["audit_detail_omitted"] is True


def test_old_unbound_approval_cannot_authorize_after_upgrade(tmp_path, monkeypatch):
    fw, rid, _, _, _, _, _ = fixture(tmp_path)
    original = fw.store.event

    def old_event(db, request, kind, data, timestamp):
        if kind == "review_recorded":
            data = {
                k: v
                for k, v in data.items()
                if k not in {"approval_id", "evaluation_id", "evidence_hash"}
            }
        return original(db, request, kind, data, timestamp)

    monkeypatch.setattr(fw.store, "event", old_event)
    assert approve(fw, rid)["authorization"] is None
    old_receipt = fw.receipt()
    monkeypatch.setattr(fw.store, "event", original)
    assert fw.evaluate(rid)["result"]["disposition"] == "REQUIRE_REVIEW"
    assert approve(fw, rid)["authorization"] is not None
    assert verify_receipt(old_receipt, fw.store.public)


def test_evidence_request_remains_effective_without_approval_snapshot_id(tmp_path):
    fw, rid, _, _, _, _, _ = fixture(tmp_path)
    fw.evaluate(rid)
    result = fw.review(
        rid, Review(decision="request_evidence", reason="Need justification"), revision=1
    )
    assert result["authorization"] is None
    assert result["result"]["disposition"] == "REQUIRE_EVIDENCE"
