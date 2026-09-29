"""Verify a real wheel in a fresh, temporary core-only environment on either OS."""

import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    wheel = max((ROOT / "dist").glob("decision_firewall-0.3.0-*.whl"))
    with tempfile.TemporaryDirectory(prefix="firewall-core-") as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True).create(root / "env")
        python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

        def run(*args, cwd=root):
            subprocess.run([str(python), *map(str, args)], cwd=cwd, check=True)

        run("-m", "pip", "install", "-r", ROOT / "requirements-core.lock")
        run("-m", "pip", "install", "--no-deps", wheel)
        run(
            "-c",
            "import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ['torch','fastapi','opentelemetry','laya'])",
        )
        run("-m", "decision_firewall.cli", "init", root / "starter")
        starter = root / "starter"
        run(starter / "run.py")
        run(starter / "workflow.py")
        run(
            "-m",
            "decision_firewall.cli",
            "experiments",
            "run",
            "experiment.json",
            ".runtime/validation",
            cwd=starter,
        )
        run(
            "-m",
            "decision_firewall.cli",
            "experiments",
            "compare",
            ".runtime/validation",
            ".runtime/validation",
            cwd=starter,
        )
        run(ROOT / "examples/workbench/run.py", root / "reference-domains")
        run(ROOT / "examples/preparation.py")
        run(
            "-m",
            "decision_firewall.cli",
            "conformance",
            "decision_firewall.conformance_fixtures:deployments",
        )
        run(
            "-c",
            "from decision_firewall.conformance_fixtures import deployments; "
            "from decision_firewall.core import DecisionFirewall; "
            "from decision_firewall.core.investigation import investigate; "
            "from pathlib import Path; "
            "f=deployments(Path('incident-demo'), 'response_loss'); "
            "fw=DecisionFirewall('incident-demo', [f.domain]); "
            "rid=fw.submit(f.proposal, f.assessment); "
            "fw.execute(fw.evaluate(rid)['authorization']); "
            "r=investigate(fw.receipt(), fw.store.public, rid); "
            "assert r['audit_verified'] and r['unresolved_authorizations']",
        )
        run("prepare.py", cwd=starter)
        result = json.loads((starter / ".runtime/validation/results.json").read_text())
        assert result["passed"]
        print("Fresh core-only wheel: import, comparison, custom evaluator and both domains PASS")


if __name__ == "__main__":
    main()
