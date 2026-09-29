from dataclasses import replace

import pytest

from decision_firewall import (
    Assessment,
    ContextItem,
    DecisionFirewall,
    PreparationSpec,
    Proposal,
    RenderedPreparedModel,
)
from decision_firewall.adapters.models import CallableModel
from decision_firewall.core import verify_receipt
from decision_firewall.domains.access.pack import access_domain, access_preparation


def setup(tmp_path, directory=None, observer=None):
    domain = access_domain(tmp_path, directory=directory)
    fw = DecisionFirewall(tmp_path, [domain], observer=observer)
    p = Proposal(
        domain="access",
        message="Please grant access",
        action={
            "employee": "alice",
            "resource": "engineering-docs",
            "hours": 4,
        },
    )
    return fw, p


def test_deterministic_route_has_no_authority_and_final_evidence_is_fresh(tmp_path):
    directory = {"alice": {"active": True, "resources": ["engineering-docs"], "version": 1}}
    fw, p = setup(tmp_path, directory)
    prepared = fw.prepare(p, access_preparation(structured=True))
    assert prepared.route == "READY_FOR_DETERMINISTIC_EVALUATION"
    a = fw.assess_prepared(prepared.id)
    with fw.store.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM permits").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
    directory["alice"]["active"] = False
    directory["alice"]["version"] = 2
    rid = fw.submit(prepared.proposal, a)
    evaluated = fw.evaluate(rid)
    assert evaluated["authorization"] is None
    assert evaluated["result"]["disposition"] == "DENY"
    assert verify_receipt(fw.receipt(), fw.store.public)


@pytest.mark.parametrize(
    "directory,route",
    [
        ({}, "REQUIRE_INPUT_OR_EVIDENCE"),
        ({"alice": {"active": False, "resources": [], "version": 1}}, "BLOCKED_BY_MANDATORY_CHECK"),
    ],
)
def test_blocked_routes_never_call_model(tmp_path, directory, route):
    fw, p = setup(tmp_path, directory)
    prepared = fw.prepare(p, access_preparation())
    assert prepared.route == route
    with pytest.raises(ValueError, match="not ready"):
        fw.assess_prepared(prepared.id)


def test_budget_preserves_message_omits_whole_optional_context(tmp_path):
    fw, p = setup(tmp_path)
    prepared = fw.prepare(
        p,
        PreparationSpec(
            max_input_characters=30,
            optional_context=[
                ContextItem(name="policy-description", version="1", content="x" * 100),
            ],
        ),
    )
    assert prepared.input.message == p.message
    assert prepared.omitted == ["policy-description"]
    assert prepared.input.optional_context == []
    assert fw.prepare(p, PreparationSpec(max_input_characters=2)).route == "ERROR"


def test_opt_in_model_context_and_assessment_linkage(tmp_path):
    fw, p = setup(tmp_path)
    prepared = fw.prepare(p, PreparationSpec(evidence_keys=["employee"]))
    seen = []

    def classify(text):
        seen.append(text)
        return Assessment(provider="test", model="fixture", revision="1").model_dump()

    a = fw.assess_prepared(prepared.id, RenderedPreparedModel(CallableModel(classify)))
    assert p.message in seen[0] and "engineering-docs" in seen[0]
    assert a.metadata["preparation"]["id"] == prepared.id
    assert fw.inspect_preparation(prepared.id) == prepared
    rid = fw.submit(p, a)
    assert fw.evaluate(rid)["authorization"]


def test_errors_and_stale_preparation_fail_closed(tmp_path):
    fw, p = setup(tmp_path)
    assert fw.prepare(p, PreparationSpec(mandatory_rules=["access_duration"])).route == "ERROR"
    prepared = fw.prepare(p, access_preparation(structured=True))
    fw.domains["access"] = replace(fw.domains["access"], policy_version="changed")
    with pytest.raises(ValueError, match="domain changed"):
        fw.assess_prepared(prepared.id)


def test_audit_outage_and_requester_checks(tmp_path):
    fw, p = setup(tmp_path)

    def unavailable(*args):
        raise OSError("audit unavailable")

    fw.store.event = unavailable
    with pytest.raises(OSError):
        fw.prepare(p)
    with fw.store.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0
    fw, p = setup(tmp_path / "second")
    fw.configure_identity("requester", "requester", active=False)
    with pytest.raises(ValueError, match="requester"):
        fw.prepare(p)


def test_model_failure_does_not_create_favorable_assessment(tmp_path):
    fw, p = setup(tmp_path)
    prepared = fw.prepare(p)

    def fail(text):
        raise RuntimeError("model unavailable")

    with pytest.raises(RuntimeError):
        fw.assess_prepared(prepared.id, RenderedPreparedModel(CallableModel(fail)))


def test_expiry_and_evidence_change_require_repreparation(tmp_path):
    directory = {"alice": {"active": True, "resources": ["engineering-docs"], "version": 1}}
    fw, p = setup(tmp_path, directory)
    fw.clock = lambda: 1000
    prepared = fw.prepare(p, access_preparation(structured=True))
    fw.clock = lambda: 1301
    with pytest.raises(ValueError, match="expired"):
        fw.assess_prepared(prepared.id)
    fw.clock = lambda: 1001
    directory["alice"]["version"] = 2
    with pytest.raises(ValueError, match="evidence changed"):
        fw.assess_prepared(prepared.id)


def test_observer_runs_outside_transactions_and_excludes_content(tmp_path):
    import sqlite3

    class Observer:
        def __init__(self):
            self.events = []

        def emit(self, event):
            with sqlite3.connect(tmp_path / "governance.db", timeout=0) as db:
                db.execute("BEGIN IMMEDIATE")
                db.rollback()
            self.events.append(event)

    observer = Observer()
    fw, p = setup(tmp_path, observer=observer)
    prepared = fw.prepare(p, access_preparation(structured=True))
    a = fw.assess_prepared(prepared.id)
    fw.submit(p, a)
    routes = [e for e in observer.events if e.name == "preparation.route"]
    assert len(routes) == 1 and routes[0].correlation_id == prepared.id
    assert routes[0].status == "READY_FOR_DETERMINISTIC_EVALUATION"
    assert p.message not in str(observer.events)
    assert not any("evidence_context" in str(e.attributes) for e in observer.events)


def test_selected_rule_exception_cannot_skip_model_or_authorize(tmp_path):
    from decision_firewall.rules import Rule, RuleSet

    fw, p = setup(tmp_path)
    original = fw.domains["access"].evaluate.rules[0]

    def fail(context, config):
        raise RuntimeError("missing dependency")

    rules = RuleSet([Rule("broken", "1", "broken check", fail, original.config)])
    fw.domains["access"] = replace(fw.domains["access"], evaluate=rules)
    result = fw.prepare(p, PreparationSpec(mandatory_rules=["broken"]))
    assert result.route == "ERROR"
    assert result.rule_results[0]["status"] == "error"


@pytest.mark.parametrize(
    "verified,route",
    [
        (True, "READY_FOR_MODEL"),
        (False, "BLOCKED_BY_MANDATORY_CHECK"),
        (None, "REQUIRE_INPUT_OR_EVIDENCE"),
    ],
)
def test_refund_prechecks_reuse_eligibility_without_skipping_intake(tmp_path, verified, route):
    from decision_firewall.domains.refunds.contracts import Payment
    from decision_firewall.domains.refunds.pack import refund_domain, refund_preparation
    from decision_firewall.domains.refunds.simulator import PaymentSimulator

    pack = refund_domain(tmp_path)
    PaymentSimulator(tmp_path).seed(
        Payment(
            payment_id="p",
            customer_id="c",
            amount_minor=10000,
            destination="original",
            duplicate_verified=verified,
        )
    )
    fw = DecisionFirewall(tmp_path, [pack])
    p = Proposal(
        domain="refunds",
        message="This was charged twice",
        action={
            "payment_id": "p",
            "customer_id": "c",
            "amount_minor": 1000,
            "destination": "original",
            "message": "This was charged twice",
            "requested_reason": "duplicate",
        },
    )
    prepared = fw.prepare(p, refund_preparation())
    assert prepared.route == route
    assert prepared.spec.deterministic_assessment is None


def test_returned_mutations_do_not_rewrite_recorded_model_input(tmp_path):
    fw, p = setup(tmp_path)
    prepared = fw.prepare(p, PreparationSpec(evidence_keys=["employee"]))
    prepared.input.evidence_context["employee"] = "mutated"
    seen = []

    def classify(text):
        seen.append(text)
        return Assessment(provider="test", model="test", revision="1").model_dump()

    fw.assess_prepared(prepared.id, RenderedPreparedModel(CallableModel(classify)))
    assert "mutated" not in seen[0]
