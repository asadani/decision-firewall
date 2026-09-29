import subprocess
import sys

import pytest
from typer.testing import CliRunner

from decision_firewall.cli import app
from decision_firewall.scaffolding import scaffold


@pytest.mark.parametrize("domain", ["access", "refunds"])
def test_domain_cli_demo(tmp_path, domain):
    result = CliRunner().invoke(
        app, ["framework", "--home", str(tmp_path), "--domain", domain, "demo"]
    )
    assert result.exit_code == 0, result.output
    assert '"receipt_verified": true' in result.output and '"SUCCEEDED"' in result.output


def test_generated_extension_runs_outside_repository(tmp_path):
    scaffold(tmp_path)
    result = subprocess.run(
        [sys.executable, str(tmp_path / "run.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SUCCEEDED" in result.stdout
    with pytest.raises(ValueError, match="empty"):
        scaffold(tmp_path)
