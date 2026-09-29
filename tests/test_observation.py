"""Core observer safety is tested even when no telemetry extra is installed."""

import sqlite3

import pytest

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.core import verify_receipt
from decision_firewall.core.observation import diagnostics
from decision_firewall.domains.access.pack import access_domain


def test_observer_failure_runs_outside_transaction_and_cannot_change_decision(tmp_path):
    events = []

    class Observer:
        def emit(self, event):
            # This fails immediately if an export callback runs inside a write transaction.
            with sqlite3.connect(tmp_path / "governance.db", timeout=0) as db:
                db.execute("BEGIN IMMEDIATE")
                db.rollback()
            events.append(event)
            raise RuntimeError("offline telemetry exporter")

    previous = diagnostics["observer_errors"]
    fw = DecisionFirewall(tmp_path, [access_domain(tmp_path)], observer=Observer())
    rid = fw.submit(
        Proposal(
            domain="access",
            message="Private request never exported",
            action={"employee": "alice", "resource": "engineering-docs", "hours": 4},
        ),
        Assessment(provider="fixture", model="safe", revision="1"),
    )
    evaluation = fw.evaluate(rid)
    fw = DecisionFirewall(tmp_path, [access_domain(tmp_path)], observer=Observer())
    assert fw.execute(evaluation["authorization"])["status"] == "SUCCEEDED"
    assert verify_receipt(fw.receipt(), fw.store.public)
    assert diagnostics["observer_errors"] > previous
    assert events and all(e.correlation_id == rid for e in events)
    assert "Private request" not in repr(events)
    assert any(e.name == "evidence.resolve" for e in events)
    assert fw.detail(rid)["policy_reports"]


def test_malformed_identifiers_and_tokens_are_not_telemetry_content(tmp_path):
    events = []

    class Observer:
        def emit(self, event):
            events.append(event)

    fw = DecisionFirewall(tmp_path, [access_domain(tmp_path)], observer=Observer())
    for action in (lambda: fw.evaluate("SECRET-IN-IDENTIFIER"), lambda: fw.execute("SECRET-TOKEN")):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            action()
    assert len(events) == 2 and "SECRET" not in repr(events)
