"""Independent acceptance checks for the frozen architecture comparison."""

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.reuse_observability.policies import configuration, export_v2
from benchmarks.reuse_observability.runner import episode

HERE = Path(__file__).parents[1] / "benchmarks/reuse_observability"


def test_frozen_inputs():
    expected = {
        "protocol.json": "af91b5c5f9edb872cb4eefd9020d067217a5c551c5ee21a321da0905a54f0032",
        "cases.json": "6ddad5437fe2da2e94d192c5b108893076c5a27da9a8aac8f97394ab39dde9dc",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest


def test_review_cannot_override_new_mandatory_rule():
    result, reasons = export_v2({}, {"legal_hold": True}, configuration("data_export", True), True)
    assert result == "DENY"
    assert reasons == ["legal_hold_mandatory"]


@pytest.mark.parametrize("arm", ["modular_application", "firewall"])
@pytest.mark.parametrize("name", ["concurrent_capacity", "response_loss_restart", "audit_failure"])
def test_critical_conformance(tmp_path, arm, name):
    cases = json.loads((HERE / "cases.json").read_text())
    case = next(c for c in cases if c["id"] == "data_export-changed-" + name)
    row = episode(tmp_path / "run", case, arm)
    assert row["effects"] == case["expected_effects"]
    assert "UNKNOWN" not in row["statuses"]
    if arm == "firewall":
        assert row["audit_verified"]
        assert row["audit_tamper_rejected"]
