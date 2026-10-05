"""Behavioural assertions and fault sensitivity across both existing engines."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from control_conformance import Observation, Unsupported, run
from control_conformance.runner import CHECKS

from benchmarks.control_conformance.adapters import Bridge


@pytest.mark.parametrize("arm", ["application", "framework"])
def test_existing_engines(arm):
    report = run(lambda home, scenario: Bridge(home, scenario, arm))
    assert report["passed"], report


@pytest.mark.parametrize("arm", ["application", "framework"])
@pytest.mark.parametrize("fault", CHECKS)
def test_fault_is_detected_as_violation_not_error(arm, fault):
    report = run(lambda home, scenario: Bridge(home, scenario, arm, fault))
    result = next(r for r in report["checks"] if r["case"] == fault)
    assert result["status"] == "FAIL", report


def test_errors_and_unsupported_are_not_passes():
    def unsupported(home, scenario):
        raise Unsupported("No fault injection hook")

    def broken(home, scenario):
        raise ValueError("broken adapter")

    assert run(unsupported)["counts"]["UNSUPPORTED"] == 3
    report = run(broken)
    assert not report["passed"] and report["counts"]["ERROR"] == 3


def test_plain_application_never_imports_framework():
    root = Path(__file__).resolve().parents[1]
    code = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path('conformance/src').resolve()))
class Block:
    def find_spec(self, fullname, *args):
        if fullname == 'decision_firewall' or fullname.startswith('decision_firewall.'):
            raise AssertionError('framework import: ' + fullname)
sys.meta_path.insert(0, Block())
from control_conformance import run
from benchmarks.control_conformance.adapters import application
report = run(application)
assert report['passed'], report
assert not any(n.startswith('decision_firewall') for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True, timeout=60)


@pytest.mark.parametrize(
    "exception,exit_code,status",
    [
        ("Unsupported", 2, "UNSUPPORTED"),
        ("ValueError", 1, "ERROR"),
    ],
)
def test_cli_reports_incomplete_and_broken_adapters(tmp_path, exception, exit_code, status):
    (tmp_path / "fixture.py").write_text(
        "from control_conformance import Unsupported\n"
        f"def factory(home, scenario):\n    raise {exception}('test hook')\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, "-m", "control_conformance", "fixture:factory", "--output", str(output)],
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    assert result.returncode == exit_code, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert not report["passed"] and report["counts"][status] == 3


class ScriptedTarget:
    """Adversarial adapter responses to test the suite itself, not an application."""

    def __init__(self, scenario, fault):
        self.scenario, self.fault = scenario, fault
        self.seen = Observation(0, (), (), "intended", (), "facts-1")
        self.stale = False

    def effect(self):
        self.seen = replace(
            self.seen,
            effects=1,
            dispatch_keys=("original",),
            effect_fingerprints=("wrong" if self.fault == "wrong_effect" else "intended",),
        )

    def prepare(self):
        if self.fault == "early_prepare":
            self.effect()
        return "READY" if self.fault == "automatic" else "REVIEW_REQUIRED"

    def approve(self):
        if self.fault == "early_approval":
            self.effect()
        assert self.fault != "automatic", "Automatic actions must not receive fake human review"
        return "READY"

    def execute(self):
        if self.stale:
            return "BLOCKED"
        self.effect()
        if self.fault == "late_unsupported":
            raise Unsupported("Cannot downgrade a started scenario")
        if self.scenario == "lost_response":
            if self.fault == "old_lookup":
                self.seen = replace(self.seen, lookup_keys=("original",))
            return "UNKNOWN"
        return "SUCCEEDED"

    def change_evidence(self):
        self.stale = True
        if self.fault != "no_change":
            self.seen = replace(self.seen, evidence_fingerprint="facts-2")

    def recover_after_restart(self):
        if self.fault != "old_lookup":
            self.seen = replace(self.seen, lookup_keys=("original",))
        return "SUCCEEDED"

    def observe(self):
        return self.seen


@pytest.mark.parametrize(
    "fault,case,reason",
    [
        ("early_prepare", "duplicate_effect", "preparation_changed_effects_or_evidence"),
        ("early_approval", "duplicate_effect", "approval_changed_effects_or_evidence"),
        ("wrong_effect", "duplicate_effect", "wrong_action_effect"),
        ("no_change", "stale_approval", "stale_evidence_not_injected"),
        ("old_lookup", "lost_response", "recovery_did_not_query_authority"),
    ],
)
def test_suite_rejects_false_positive_paths(fault, case, reason):
    report = run(lambda home, scenario: ScriptedTarget(scenario, fault))
    result = next(r for r in report["checks"] if r["case"] == case)
    assert result == {"case": case, "status": "FAIL", "reason": reason}


def test_late_unsupported_is_error():
    report = run(lambda home, scenario: ScriptedTarget(scenario, "late_unsupported"))
    assert report["counts"]["ERROR"] == 2 and report["counts"]["UNSUPPORTED"] == 0


def test_automatic_actions_need_no_fake_review():
    def factory(home, scenario):
        if scenario == "stale_approval":
            raise Unsupported("No human review in this integration")
        return ScriptedTarget(scenario, "automatic")

    report = run(factory)
    assert report["counts"] == {"PASS": 2, "FAIL": 0, "ERROR": 0, "UNSUPPORTED": 1}


@pytest.mark.parametrize(
    "values",
    [
        {"effects": True},
        {"effects": -1},
        {"effects": 1},
        {"expected_effect": ""},
        {"dispatch_keys": ("",)},
        {"effect_fingerprints": ["x"]},
    ],
)
def test_malformed_oracles_are_rejected(values):
    with pytest.raises(ValueError):
        replace(Observation(0, (), (), "intended", (), "facts-1"), **values)


def test_detection_gate_rejects_unrelated_errors_and_duplicate_cases():
    from benchmarks.control_conformance.run import expected_result

    rows = [{"case": c, "status": "FAIL" if c == "stale_approval" else "PASS"} for c in CHECKS]
    assert expected_result({"checks": rows}, "stale_approval")
    rows[-1]["status"] = "ERROR"
    assert not expected_result({"checks": rows}, "stale_approval")
    assert not expected_result({"checks": [rows[0]] * 3}, "stale_approval")


@pytest.mark.parametrize("factory,code", [("missing_colon", 2), ("no_such_module:factory", 1)])
def test_cli_load_errors_fail_cleanly(factory, code):
    result = subprocess.run(
        [sys.executable, "-m", "control_conformance", factory],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == code
    assert "Traceback" not in result.stderr
