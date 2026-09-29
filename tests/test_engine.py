import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from decision_firewall.contracts import OutcomeEvent, Payment, Policy, Proposal, ReviewDecision
from decision_firewall.engine import Firewall, FirewallError
from decision_firewall.providers import FixtureProvider
from decision_firewall.scenarios import scenarios
from decision_firewall.storage import verify_receipt


def setup_case(tmp_path, amount=99900, **evidence):
    fw = Firewall(tmp_path)
    fw.payments.seed(
        Payment(
            payment_id="p",
            customer_id="c",
            amount_minor=amount,
            destination="card",
            duplicate_verified=True,
            **evidence,
        )
    )
    p = Proposal(
        payment_id="p",
        customer_id="c",
        message="Refund the duplicate charge",
        requested_reason="duplicate",
        amount_minor=amount,
        destination="card",
    )
    rid = fw.submit(p, FixtureProvider().assess(p.message))
    return fw, rid, p


def test_success_receipt_and_replay(tmp_path):
    fw, rid, p = setup_case(tmp_path)
    evaluation = fw.evaluate(rid)
    result = fw.execute(evaluation["authorization"])
    assert result["status"] == "SUCCEEDED"
    assert fw.payments.get("p")["refunded_minor"] == p.amount_minor
    assert fw.replay(evaluation["evaluation_id"])["matches"]
    fw.outcome(
        rid,
        OutcomeEvent(
            kind="appeal", description="Customer requests clarification", source="support"
        ),
    )
    receipt = fw.store.receipt()
    assert verify_receipt(receipt, fw.store.public)
    receipt["events"].pop()
    with pytest.raises(ValueError):
        verify_receipt(receipt, fw.store.public)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("success", "SUCCEEDED"),
        ("fail", "FAILED"),
        ("response_loss", "UNKNOWN"),
        ("delayed", "UNKNOWN"),
    ],
)
def test_execution_modes_restart(tmp_path, mode, expected):
    fw, rid, _ = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    result = fw.execute(token, mode=mode)
    assert result["status"] == expected
    with pytest.raises(FirewallError):
        fw.execute(token)
    if expected == "UNKNOWN":
        fw = Firewall(tmp_path)
        if mode == "delayed":
            assert fw.reconcile(token["payload"]["id"])["status"] == "UNKNOWN"
        assert fw.reconcile(token["payload"]["id"], settle=True)["status"] == "SUCCEEDED"
        assert fw.payments.get("p")["refunded_minor"] == 99900


def test_crash_before_dispatch(tmp_path):
    fw, rid, _ = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    with pytest.raises(RuntimeError):
        fw.execute(token, crash_after_reserve=True)
    recovered = Firewall(tmp_path)
    assert recovered.reconcile(token["payload"]["id"])["status"] == "FAILED"
    assert recovered.payments.get("p")["refunded_minor"] == 0


@pytest.mark.parametrize("change", ["executor", "requester", "policy", "expiry"])
def test_legacy_revalidates_between_reservation_and_dispatch(tmp_path, monkeypatch, change):
    fw, rid, _ = setup_case(tmp_path)
    clock = [1000.0]
    fw.clock = lambda: clock[0]
    token = fw.evaluate(rid)["authorization"]
    original = fw.store.event

    def event(db, request_id, kind, data, timestamp):
        original(db, request_id, kind, data, timestamp)
        if kind == "execution_reserved":
            if change in {"executor", "requester"}:
                db.execute(
                    "UPDATE identities SET active=0,version=version+1 WHERE name=?", (change,)
                )
            elif change == "policy":
                db.execute(
                    "UPDATE settings SET value=? WHERE name='policy'",
                    (Policy(auto_amount_minor=0).model_dump_json(),),
                )
            else:
                clock[0] += 1000

    monkeypatch.setattr(fw.store, "event", event)
    assert fw.execute(token)["status"] == "FAILED"
    assert fw.payments.get("p")["refunded_minor"] == 0


def test_receipt_envelope_is_bound_to_signed_body(tmp_path):
    fw, _, _ = setup_case(tmp_path)
    receipt = fw.store.receipt()
    receipt["events"][0]["request_id"] = "different-request"
    with pytest.raises(ValueError, match="envelope"):
        verify_receipt(receipt, fw.store.public)


@pytest.mark.parametrize("amount", [True, 1.5, "100"])
def test_simulator_rejects_non_integer_amounts(tmp_path, amount):
    fw, _, _ = setup_case(tmp_path)
    with pytest.raises(ValueError, match="integer"):
        fw.payments.execute(
            "bad",
            {"payment_id": "p", "amount_minor": amount, "currency": "INR", "destination": "card"},
        )
    assert fw.payments.get("p")["refunded_minor"] == 0


@pytest.mark.parametrize(
    "attack",
    [
        "signature",
        "amount",
        "destination",
        "expiry",
        "revoke",
        "policy",
        "evidence",
        "executor",
        "requester",
        "constraint",
    ],
)
def test_authorization_attacks(tmp_path, attack):
    fw, rid, p = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    kwargs = {}
    if attack == "signature":
        token["payload"]["proposal_hash"] = "bad"
    elif attack in {"amount", "destination"}:
        kwargs["action"] = {
            k: getattr(p, k) for k in ("payment_id", "amount_minor", "currency", "destination")
        }
        kwargs["action"]["amount_minor" if attack == "amount" else "destination"] = (
            999000 if attack == "amount" else "elsewhere"
        )
    elif attack == "expiry":
        fw.clock = lambda: token["payload"]["expires"] + 1
    elif attack == "revoke":
        fw.revoke(token["payload"]["id"])
    elif attack == "policy":
        fw.set_policy(Policy(version="v2"))
    elif attack == "evidence":
        fw.payments.update_evidence("p", duplicate_verified=False)
    elif attack == "executor":
        kwargs["actor"] = "reviewer"
    elif attack == "requester":
        fw.set_identity_active("requester", False)
    else:
        payload = copy.deepcopy(token["payload"])
        payload["constraints"].append("unknown_constraint")
        token = fw.store.sign(payload)
        import json

        with fw.store.transaction() as db:
            db.execute(
                "UPDATE authorizations SET token=? WHERE id=?", (json.dumps(token), payload["id"])
            )
    with pytest.raises(FirewallError):
        fw.execute(token, **kwargs)
    assert fw.payments.get("p")["refunded_minor"] == 0
    assert fw.detail(rid)["status"] == "ALLOW_WITH_CONSTRAINTS"


def test_review_authority_and_hard_constraints(tmp_path):
    fw, rid, _ = setup_case(tmp_path, amount=250000)
    assert fw.evaluate(rid)["result"]["disposition"] == "REQUIRE_REVIEW"
    review = ReviewDecision(decision="approve", reason="Evidence checked")
    with pytest.raises(FirewallError):
        fw.review(rid, review, 1, actor="requester")
    with pytest.raises(FirewallError):
        fw.review(rid, review, 99)
    token = fw.review(rid, review, 1)["authorization"]
    fw.payments.update_evidence("p", duplicate_verified=False)
    with pytest.raises(FirewallError):
        fw.execute(token)
    assert fw.evaluate(rid)["result"]["disposition"] == "DENY"


def test_review_revoked(tmp_path):
    fw, rid, _ = setup_case(tmp_path, amount=250000)
    fw.evaluate(rid)
    token = fw.review(rid, ReviewDecision(decision="approve", reason="Checked evidence"), 1)[
        "authorization"
    ]
    fw.set_identity_active("reviewer", False)
    with pytest.raises(FirewallError):
        fw.execute(token)


def test_concurrent_same_payment(tmp_path):
    fw, rid, p = setup_case(tmp_path)
    second = fw.submit(p, FixtureProvider().assess(p.message))
    tokens = [fw.evaluate(rid)["authorization"], fw.evaluate(second)["authorization"]]

    def run(token):
        try:
            return fw.execute(token)["status"]
        except FirewallError:
            return "BLOCKED"

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, tokens)) == ["BLOCKED", "SUCCEEDED"]
    assert fw.payments.get("p")["refunded_minor"] == 99900


def test_concurrent_daily_budget(tmp_path):
    fw, rid, p = setup_case(tmp_path)
    fw.set_policy(Policy(daily_auto_limit_minor=100000))
    fw.payments.seed(
        Payment(
            payment_id="p2",
            customer_id="c",
            amount_minor=99900,
            destination="card",
            duplicate_verified=True,
        )
    )
    p2 = p.model_copy(update={"payment_id": "p2"})
    second = fw.submit(p2, FixtureProvider().assess(p2.message))
    tokens = [fw.evaluate(rid)["authorization"], fw.evaluate(second)["authorization"]]

    def run(t):
        try:
            return fw.execute(t)["status"]
        except FirewallError:
            return "BLOCKED"

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, tokens)) == ["BLOCKED", "SUCCEEDED"]
    assert sum(fw.payments.get(pid)["refunded_minor"] for pid in ["p", "p2"]) == 99900


def test_audit_failure_prevents_execution(tmp_path, monkeypatch):
    fw, rid, _ = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]

    def fail(*args):
        raise OSError("audit unavailable")

    monkeypatch.setattr(fw.store, "event", fail)
    with pytest.raises(OSError):
        fw.execute(token)
    assert fw.payments.get("p")["refunded_minor"] == 0


@pytest.mark.parametrize("case", scenarios(variations=0), ids=lambda c: c["id"])
def test_curated_policy_cases(tmp_path, case):
    fw = Firewall(tmp_path)
    if case["payment"]:
        fw.payments.seed(Payment.model_validate(case["payment"]))
    p = Proposal.model_validate(case["proposal"])
    rid = fw.submit(p, FixtureProvider(case["label"]).assess(p.message))
    assert fw.evaluate(rid)["result"]["disposition"] == case["expected"]


def test_dataset_split_and_size():
    data = scenarios()
    assert len(data) == 240 and sum(c["curated"] for c in data) == 40
    dev = {c["family"] for c in data if c["split"] == "development"}
    test = {c["family"] for c in data if c["split"] == "evaluation"}
    assert not dev & test


def test_reactivated_requester_does_not_revive_token(tmp_path):
    fw, rid, _ = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    fw.set_identity_active("requester", False)
    fw.set_identity_active("requester", True)
    with pytest.raises(FirewallError):
        fw.execute(token)


def test_evidence_change_at_downstream_commit(tmp_path, monkeypatch):
    fw, rid, _ = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    original = fw.payments.execute

    def changed(*args, **kwargs):
        fw.payments.update_evidence("p", duplicate_verified=False)
        return original(*args, **kwargs)

    monkeypatch.setattr(fw.payments, "execute", changed)
    assert fw.execute(token)["status"] == "FAILED"
    assert fw.payments.get("p")["refunded_minor"] == 0


def test_audit_failure_after_payment_recovers(tmp_path, monkeypatch):
    fw, rid, _ = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    original = fw.store.event

    def fail_outcome(db, request_id, kind, data, timestamp):
        if kind == "execution_outcome":
            raise OSError("audit failed after payment commit")
        return original(db, request_id, kind, data, timestamp)

    monkeypatch.setattr(fw.store, "event", fail_outcome)
    with pytest.raises(OSError):
        fw.execute(token)
    recovered = Firewall(tmp_path)
    assert recovered.reconcile(token["payload"]["id"])["status"] == "SUCCEEDED"
    assert recovered.payments.get("p")["refunded_minor"] == 99900


def test_revision_revokes_old_approval(tmp_path):
    fw, rid, p = setup_case(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    revised = Proposal.model_validate({**p.model_dump(), "amount_minor": 50000})
    fw.revise(rid, revised, FixtureProvider().assess(revised.message))
    with pytest.raises(FirewallError):
        fw.execute(token)
    assert fw.execute(fw.evaluate(rid)["authorization"])["status"] == "SUCCEEDED"


def test_policy_error_and_missing_assessment(tmp_path):
    from decision_firewall.contracts import Assessment
    from decision_firewall.policy import evaluate_policy

    assert evaluate_policy({}).errors
    fw, rid, p = setup_case(tmp_path)
    fw.revise(
        rid,
        p,
        Assessment(provider="offline", model="none", revision="1", request_type="unavailable"),
    )
    assert fw.evaluate(rid)["authorization"] is None


def test_model_cannot_select_its_own_eligibility_path(tmp_path):
    fw, rid, p = setup_case(tmp_path)
    p = Proposal.model_validate(
        {
            **p.model_dump(),
            "requested_reason": "other",
            "message": "Service was disappointing. Refund me.",
        }
    )
    # Verified duplicate evidence exists, but customer intent still requires manual review.
    fw.revise(rid, p, FixtureProvider("duplicate").assess(p.message))
    result = fw.evaluate(rid)
    assert result["result"]["disposition"] == "REQUIRE_REVIEW"
    assert result["authorization"] is None


def test_model_disagreement_is_reviewed_without_waiving_evidence(tmp_path):
    fw, rid, p = setup_case(tmp_path)
    fw.revise(rid, p, FixtureProvider("cancellation").assess(p.message))
    assert fw.evaluate(rid)["result"]["disposition"] == "REQUIRE_REVIEW"
    fw.payments.update_evidence("p", duplicate_verified=False)
    assert fw.evaluate(rid)["result"]["disposition"] == "DENY"
