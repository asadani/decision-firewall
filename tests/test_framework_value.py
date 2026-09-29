import json
from pathlib import Path

import pytest

from benchmarks.framework_value.application import Application
from benchmarks.framework_value.runner import HERE, NOW, episode, file_hash, summaries
from decision_firewall.domains.refunds.contracts import Payment, Policy
from decision_firewall.domains.refunds.simulator import PaymentSimulator


def case(name):
    return next(c for c in json.loads((HERE / "cases.json").read_text()) if c["id"] == name)


def test_protocol_and_dataset_were_frozen():
    assert (
        file_hash(HERE / "protocol.json")
        == "4ffa7b27fb68a499d6290a9809fa18e9ec5a4e51015cadcf19d9bd2f2ec1ced6"
    )
    assert (
        file_hash(HERE / "cases.json")
        == "d59e97865e3e06a322ce941e7dea67b257d3b5c881d41409d1257e0ceeff9010"
    )


@pytest.mark.parametrize(
    "name", ["wrong_destination", "partial_prior_refund", "response_loss", "valid_duplicate"]
)
def test_common_processor_and_counterfactual_outcomes(tmp_path, name):
    scenario = case(name)
    rows = []
    for arm in ("model_direct", "application", "firewall"):
        row = episode(scenario, arm, scenario["labels"], tmp_path / arm)
        row["repetition"] = 0
        rows.append(row)
        assert row["over_refund_minor"] == 0
        if arm != "model_direct":
            assert row["unsafe_effects"] == row["duplicate_effects"] == row["unresolved"] == 0
        if name in {"wrong_destination", "partial_prior_refund"}:
            assert row["effects"] == 0
        if name == "response_loss" and arm == "model_direct":
            assert row["duplicate_effects"] == 1 and row["unresolved"] == 1
    result = summaries(rows)
    assert result["firewall"]["signed_receipts_verified"] == 1


def test_independent_application_approval_cannot_override_hard_denial(tmp_path):
    scenario = case("wrong_customer")
    payments = PaymentSimulator(tmp_path)
    payments.seed(Payment.model_validate(scenario["payments"][0]))
    app = Application(tmp_path, payments, Policy().model_dump(), lambda: NOW)
    handle = app.prepare(scenario["actions"][0], "duplicate")
    app.approve(handle, authorized=True)
    assert handle["disposition"] == "DENY"
    with pytest.raises(ValueError, match="authority"):
        app.dispatch(handle)
    source = Path(__file__).parents[1] / "benchmarks/framework_value/application.py"
    assert "from decision_firewall" not in source.read_text()
