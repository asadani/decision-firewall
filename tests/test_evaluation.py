from decision_firewall.evaluation import benchmark


def test_measured_fixture_report(tmp_path):
    result = benchmark(tmp_path / "run", provider_name="fixture", variations=0, limit=8)
    assert result["overall"]["n"] == 8
    assert result["overall"]["policy_agreement"] == 1
    assert result["overall"]["over_refunds"] == 0
    assert (tmp_path / "run" / "report.html").exists()
