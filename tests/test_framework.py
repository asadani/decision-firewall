import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from pydantic import ValidationError

from decision_firewall import Assessment, DecisionFirewall, Proposal, Signal
from decision_firewall.adapters.models import CallableModel, RefundModelAdapter
from decision_firewall.core import Decision, Disposition, Review, RuntimeIdentity, verify_receipt
from decision_firewall.core.runtime import FirewallError
from decision_firewall.domains.access.pack import access_domain
from decision_firewall.domains.refunds.contracts import Payment, Policy
from decision_firewall.domains.refunds.pack import refund_domain
from decision_firewall.domains.refunds.providers import FixtureProvider
from decision_firewall.domains.refunds.scenarios import scenarios
from decision_firewall.domains.refunds.simulator import PaymentSimulator


def assessment():
    return Assessment(
        provider="test",
        model="fixture",
        revision="1",
        signals={"intent": Signal(kind="choice", value="access")},
    )


def access(tmp_path, hours=4, mode="success", clock=None):
    domain = access_domain(tmp_path, mode=mode)
    fw = DecisionFirewall(tmp_path, [domain], **({"clock": clock} if clock else {}))
    proposal = Proposal(
        domain="access",
        action={"employee": "alice", "resource": "engineering-docs", "hours": hours},
        message="Please grant temporary access",
    )
    return fw, fw.submit(proposal, assessment()), domain, proposal


def test_non_financial_lifecycle(tmp_path):
    fw, rid, domain, _ = access(tmp_path, hours=24)
    assert fw.evaluate(rid)["result"]["disposition"] == "REQUIRE_REVIEW"
    evaluated = fw.review(
        rid, Review(decision="approve", reason="Temporary on-call duty"), revision=1
    )
    assert fw.execute(evaluated["authorization"])["status"] == "SUCCEEDED"
    assert fw.detail(rid)["status"] == "COMPLETED"
    assert fw.replay(evaluated["evaluation_id"])["matches"]
    fw.outcome(rid, "Access completed", kind="outcome")
    fw.outcome(rid, "Clarified business justification", kind="correction")
    assert verify_receipt(fw.receipt(), fw.store.public)
    with pytest.raises(FirewallError):
        fw.execute(evaluated["authorization"])
    changed = replace(domain, policy_version="2")
    with pytest.raises(FirewallError, match="recorded"):
        fw.replay(evaluated["evaluation_id"], domain=changed)


@pytest.mark.parametrize("case", scenarios(variations=0), ids=lambda c: c["id"])
def test_refunds_use_shared_runtime_without_policy_regression(tmp_path, case):
    domain = refund_domain(tmp_path)
    ledger = PaymentSimulator(tmp_path)
    if case["payment"]:
        ledger.seed(Payment.model_validate(case["payment"]))
    fw = DecisionFirewall(tmp_path, [domain])
    p = Proposal(domain="refunds", action=case["proposal"], message=case["proposal"]["message"])
    a = RefundModelAdapter(FixtureProvider(case["label"], case["refund_requested"])).assess(
        p.message
    )
    rid = fw.submit(p, a)
    evaluated = fw.evaluate(rid)
    assert evaluated["result"]["disposition"] == case["expected"]
    if evaluated["authorization"]:
        assert fw.execute(evaluated["authorization"])["status"] == "SUCCEEDED"
    assert fw.replay(evaluated["evaluation_id"])["matches"]


@pytest.mark.parametrize(
    "change",
    ["tamper", "expired", "revoke", "executor", "requester", "policy", "evidence", "revision"],
)
def test_stale_authority_does_not_execute(tmp_path, change):
    now = [1000.0]
    fw, rid, domain, p = access(tmp_path, clock=lambda: now[0])
    token = fw.evaluate(rid)["authorization"]
    if change == "tamper":
        token = copy.deepcopy(token)
        token["payload"]["executor"] = "attacker"
    elif change == "expired":
        now[0] += 1000
    elif change == "revoke":
        fw.revoke(token["payload"]["id"])
    elif change in {"executor", "requester"}:
        fw.configure_identity(change, change, active=False)
        fw.configure_identity(change, change, active=True)
    elif change == "policy":
        fw.domains["access"] = replace(domain, policy_version="2")
    elif change == "evidence":

        def modified(proposal):
            ev = domain.resolve(proposal)
            return ev.model_copy(update={"versions": {"directory": "2"}})

        fw.domains["access"] = replace(domain, resolve=modified)
    elif change == "revision":
        fw.revise(rid, p.model_copy(update={"message": "Updated justification"}), assessment())
    with pytest.raises(FirewallError):
        fw.execute(token)
    assert not any(e["status"] == "SUCCEEDED" for e in fw.detail(rid)["executions"])


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("success", "SUCCEEDED"),
        ("fail", "FAILED"),
        ("response_loss", "UNKNOWN"),
        ("delayed", "UNKNOWN"),
    ],
)
def test_adapter_outcomes_restart_and_no_duplicate(tmp_path, mode, expected):
    fw, rid, domain, _ = access(tmp_path, mode=mode)
    token = fw.evaluate(rid)["authorization"]
    result = fw.execute(token)
    assert result["status"] == expected
    if expected == "UNKNOWN":
        restarted = DecisionFirewall(tmp_path, [access_domain(tmp_path)])
        if mode == "delayed":
            assert restarted.reconcile(token["payload"]["id"])["status"] == "UNKNOWN"
            domain.executor.settle(result["attempt_id"])
        assert restarted.reconcile(token["payload"]["id"])["status"] == "SUCCEEDED"
    with pytest.raises(FirewallError):
        fw.execute(token)


def test_crash_before_dispatch_and_after_effect(tmp_path, monkeypatch):
    fw, rid, _, _ = access(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    with pytest.raises(RuntimeError):
        fw.execute(token, crash_after_reserve=True)
    assert fw.reconcile(token["payload"]["id"])["status"] == "FAILED"
    token = fw.evaluate(rid)["authorization"]
    original = fw.store.event

    def fail(db, request, kind, data, timestamp):
        if kind == "execution_outcome":
            raise OSError("Audit unavailable after downstream commit")
        return original(db, request, kind, data, timestamp)

    monkeypatch.setattr(fw.store, "event", fail)
    with pytest.raises(OSError):
        fw.execute(token)
    monkeypatch.setattr(fw.store, "event", original)
    assert fw.reconcile(token["payload"]["id"])["status"] == "SUCCEEDED"


def test_review_cannot_override_hard_constraints(tmp_path):
    directory = {"alice": {"active": True, "resources": ["docs"], "version": 1}}
    domain = access_domain(tmp_path, directory=directory)
    fw = DecisionFirewall(tmp_path, [domain])
    p = Proposal(
        domain="access",
        action={"employee": "alice", "resource": "docs", "hours": 24},
        message="Access",
    )
    rid = fw.submit(p, assessment())
    fw.evaluate(rid)
    directory["alice"]["active"] = False
    assert (
        fw.review(rid, Review(decision="approve", reason="Attempted override"), revision=1)[
            "authorization"
        ]
        is None
    )
    assert fw.detail(rid)["status"] == "DENY"


@pytest.mark.parametrize("failure", ["evidence", "policy", "constraint", "model"])
def test_fail_closed_plugins(tmp_path, failure):
    fw, rid, domain, _ = access(tmp_path)

    def broken(_):
        raise OSError("Plugin unavailable")

    if failure == "evidence":
        fw.domains["access"] = replace(domain, resolve=broken)
    elif failure == "policy":
        fw.domains["access"] = replace(domain, evaluate=broken)
    elif failure == "constraint":
        fw.domains["access"] = replace(
            domain,
            evaluate=lambda _: Decision(
                disposition=Disposition.ALLOW_WITH_CONSTRAINTS, constraints=["unknown-control"]
            ),
        )
    else:
        with pytest.raises(OSError):
            fw.assess(CallableModel(broken), "message")
        return
    evaluated = fw.evaluate(rid)
    assert evaluated["authorization"] is None and evaluated["result"]["errors"]
    assert fw.detail(rid)["status"] == "EVALUATION_ERROR"


@pytest.mark.parametrize("resource", ["balance", "budget"])
def test_concurrent_refund_reservations_and_daily_limit(tmp_path, resource):
    ledger = PaymentSimulator(tmp_path)
    domain = refund_domain(
        tmp_path,
        policy=Policy(daily_auto_limit_minor=150000 if resource == "budget" else 1000000),
        mode="delayed",
    )
    fw = DecisionFirewall(tmp_path, [domain])
    tokens = []
    for index in range(2):
        payment = Payment(
            payment_id=f"p{index}" if resource == "budget" else "shared",
            customer_id="c",
            amount_minor=100000,
            destination="card",
            duplicate_verified=True,
        )
        if resource == "budget" or index == 0:
            ledger.seed(payment)
        p = Proposal(
            domain="refunds",
            message="Refund duplicate",
            action={
                "payment_id": payment.payment_id,
                "customer_id": "c",
                "amount_minor": 100000,
                "destination": "card",
                "message": "Refund duplicate",
                "requested_reason": "duplicate",
            },
        )
        rid = fw.submit(p, RefundModelAdapter(FixtureProvider()).assess(p.message))
        tokens.append(fw.evaluate(rid)["authorization"])

    def run(token):
        try:
            return fw.execute(token)["status"]
        except FirewallError:
            return "BLOCKED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, tokens)) == ["BLOCKED", "UNKNOWN"]
    first = next(
        token
        for token in tokens
        if fw.detail(token["payload"]["request_id"])["status"] == "AWAITING_RECONCILIATION"
    )
    assert fw.reconcile(first["payload"]["id"])["status"] == "UNKNOWN"


def test_arbitrary_exception_after_effect_keeps_uncertainty(tmp_path, monkeypatch):
    fw, rid, domain, _ = access(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    original = domain.executor.execute

    def fail_after_commit(key, proposal, evidence):
        original(key, proposal, evidence)
        raise ValueError("Malformed provider response after success")

    monkeypatch.setattr(domain.executor, "execute", fail_after_commit)
    assert fw.execute(token)["status"] == "UNKNOWN"
    assert fw.reconcile(token["payload"]["id"])["status"] == "SUCCEEDED"


def test_model_identity_and_invalid_signals(tmp_path):
    with pytest.raises(ValidationError):
        Assessment.model_validate({**assessment().model_dump(), "executor": "executor"})
    with pytest.raises(ValidationError):
        Signal(kind="probability", value=2.0)
    with pytest.raises(ValidationError):
        Signal(kind="choice", value="yes", probabilities={"yes": float("nan")})
    fw, rid, _, _ = access(tmp_path, hours=24)
    fw.evaluate(rid)
    bad = DecisionFirewall(
        tmp_path, list(fw.domains.values()), identity=RuntimeIdentity(reviewer="requester")
    )
    with pytest.raises(FirewallError):
        bad.review(rid, Review(decision="approve", reason="Unauthorized review"), revision=1)


def test_core_does_not_import_domains_or_optional_runtimes():
    import ast
    from pathlib import Path

    import decision_firewall.core

    for file in Path(decision_firewall.core.__file__).parent.glob("*.py"):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                names = [module, *(alias.name for alias in node.names)]
                assert not any(
                    part in name.split(".")
                    for name in names
                    for part in ["domains", "refunds", "torch", "laya", "fastapi", "typer"]
                )
