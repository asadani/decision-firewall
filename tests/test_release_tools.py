import base64
import copy
import json
from dataclasses import replace

import pytest
from cryptography.exceptions import InvalidSignature
from typer.testing import CliRunner

from decision_firewall.cli import app
from decision_firewall.conformance_fixtures import access, deployments
from decision_firewall.core import DecisionFirewall, Review
from decision_firewall.core.conformance import CHECKS, run_conformance
from decision_firewall.core.investigation import investigate


@pytest.mark.parametrize("factory,unsupported", [(deployments, 0), (access, 1)])
def test_reference_conformance(factory, unsupported):
    report = run_conformance(factory)
    assert report["counts"] == {
        "PASS": len(CHECKS) - unsupported,
        "FAIL": 0,
        "UNSUPPORTED": unsupported,
    }
    assert report["passed"] is (unsupported == 0)


def test_suite_detects_missing_effect_and_does_not_hide_unsupported():
    def broken(home, scenario):
        if scenario != "success":
            raise NotImplementedError
        return replace(deployments(home, scenario), effects=lambda: 0)

    report = run_conformance(broken)
    assert report["counts"] == {"PASS": 0, "FAIL": 1, "UNSUPPORTED": len(CHECKS) - 1}
    assert not report["passed"]


def make_request(home, scenario="success"):
    fixture = deployments(home, scenario)
    fw = DecisionFirewall(home, [fixture.domain])
    rid = fw.submit(fixture.proposal, fixture.assessment)
    return fixture, fw, rid


def test_investigation_recovery_and_no_permits(tmp_path):
    fixture, fw, rid = make_request(tmp_path, "response_loss")
    evaluated = fw.evaluate(rid)
    token = evaluated["authorization"]
    fw.execute(token)
    receipt = fw.receipt()
    pending = investigate(receipt, fw.store.public, rid)
    assert pending["request_status_from_events"] == "AWAITING_RECONCILIATION"
    assert pending["unresolved_authorizations"] == [token["payload"]["id"]]
    fw = DecisionFirewall(tmp_path, [fixture.restart()])
    fw.reconcile(token["payload"]["id"])
    report = investigate(fw.receipt(), fw.store.public, rid)
    assert report["request_status_from_events"] == "COMPLETED"
    assert not report["gaps"] and not report["unresolved_authorizations"]
    assert report["evaluations"][0]["policy_version"] == "deployment-demo-v1"
    assert report["evaluations"][0]["rules"]
    assert report["authorizations"][0]["outcomes"][-1]["status"] == "SUCCEEDED"
    encoded = json.dumps(report)
    assert token["signature"] not in encoded
    assert fixture.proposal.message not in encoded
    assert fixture.proposal.action["artifact"] not in encoded
    # Old snapshots remain unknown even after a later successful reconciliation.
    assert investigate(receipt, fw.store.public, rid) == pending


@pytest.mark.parametrize("scenario,expected", [("failure", "OPEN"), ("review", "COMPLETED")])
def test_review_and_request_status_distinct_from_execution(tmp_path, scenario, expected):
    _, fw, rid = make_request(tmp_path, scenario)
    result = fw.evaluate(rid)
    if scenario == "review":
        result = fw.review(
            rid,
            Review(decision="approve", reason="Approved release"),
            revision=1,
            evaluation_id=result["evaluation_id"],
        )
    fw.execute(result["authorization"])
    report = investigate(fw.receipt(), fw.store.public, rid)
    assert report["request_status_from_events"] == expected
    assert bool(report["reviews"]) is (scenario == "review")


def test_investigation_refuses_tampered_receipt_or_wrong_key(tmp_path):
    _, fw, rid = make_request(tmp_path)
    receipt = fw.receipt()
    damaged = copy.deepcopy(receipt)
    damaged["events"][0]["body"] = damaged["events"][0]["body"].replace("Test deployment", "Forged")
    with pytest.raises((ValueError, InvalidSignature)):
        investigate(damaged, fw.store.public, rid)
    with pytest.raises((ValueError, InvalidSignature)):
        investigate(receipt, b"x" * 32, rid)
    with pytest.raises(ValueError, match="submission"):
        investigate(receipt, fw.store.public, "missing")


def test_missing_context_and_reserved_without_outcome(tmp_path):
    fixture, fw, rid = make_request(tmp_path)
    token = fw.evaluate(rid)["authorization"]
    with pytest.raises(RuntimeError):
        fw.execute(token, crash_after_reserve=True)
    report = investigate(fw.receipt(), fw.store.public, rid)
    assert report["unresolved_authorizations"]
    assert report["request_status_from_events"] == "AWAITING_RECONCILIATION"
    assert fixture.effects() == 0  # Report must not infer failure from no response.


def test_investigation_cli_offline(tmp_path):
    _, fw, rid = make_request(tmp_path)
    fw.evaluate(rid)
    receipt, key = tmp_path / "receipt.json", tmp_path / "trusted.pub"
    receipt.write_text(json.dumps(fw.receipt()), encoding="utf-8")
    key.write_text(base64.b64encode(fw.store.public).decode(), encoding="ascii")
    saved = tmp_path / "incident.json"
    result = CliRunner().invoke(
        app, ["investigate", str(receipt), str(key), rid, "--save", str(saved)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(saved.read_text())["audit_verified"]
    key.write_text(base64.b64encode(b"x" * 32).decode(), encoding="ascii")
    result = CliRunner().invoke(app, ["investigate", str(receipt), str(key), rid])
    assert result.exit_code == 1
    assert "proposals" not in result.output


def test_conformance_cli_exit_codes(monkeypatch):
    import decision_firewall.tooling_cli as cli

    for counts, expected in [
        ({"FAIL": 0, "UNSUPPORTED": 0}, 0),
        ({"FAIL": 1, "UNSUPPORTED": 0}, 1),
        ({"FAIL": 0, "UNSUPPORTED": 1}, 2),
    ]:
        monkeypatch.setattr(
            cli, "run_conformance", lambda factory, counts=counts: {"counts": counts}
        )
        result = CliRunner().invoke(
            app, ["conformance", "decision_firewall.conformance_fixtures:access"]
        )
        assert result.exit_code == expected


def test_evaluation_error_is_explicit_gap(tmp_path):
    fixture, fw, rid = make_request(tmp_path)

    def unavailable(_):
        raise OSError("Registry unavailable")

    fw.domains["deployments"] = replace(fixture.domain, resolve=unavailable)
    fw.evaluate(rid)
    report = investigate(fw.receipt(), fw.store.public, rid)
    assert report["gaps"]
    assert report["request_status_from_events"] == "EVALUATION_ERROR"
    assert report["evaluations"][0]["evidence_versions"] is None
    assert not report["authorizations"]


def test_revision_supersedes_authorization_and_action_export_is_opt_in(tmp_path):
    fixture, fw, rid = make_request(tmp_path)
    fw.evaluate(rid)
    fw.revise(rid, fixture.proposal.model_copy(update={"message": "Revised"}), fixture.assessment)
    report = investigate(fw.receipt(), fw.store.public, rid, action_fields=("service",))
    assert report["request_status_from_events"] == "OPEN"
    assert report["authorizations"][0]["status"] == "SUPERSEDED"
    assert report["proposals"][-1]["revision"] == 2
    assert report["proposals"][-1]["selected_action_values"] == {"service": "orders"}


def test_broken_idempotent_adapter_detected():
    def broken(home, scenario):
        if scenario != "adapter_idempotency":
            raise NotImplementedError
        fixture = deployments(home, scenario)
        executor = fixture.domain.executor
        original = executor.execute
        calls = [0]

        def duplicate(key, proposal, evidence):
            calls[0] += 1
            return original(str(calls[0]), proposal, evidence)

        executor.execute = duplicate
        return fixture

    report = run_conformance(broken)
    failure = next(r for r in report["checks"] if r["status"] == "FAIL")
    assert failure["check"] == "adapter_idempotency"
    assert failure["reason"] == "Adapter retry duplicated effects"
