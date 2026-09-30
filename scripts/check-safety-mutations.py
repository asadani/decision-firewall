"""Nine bounded runtime mutations in an isolated copy; never modifies the checkout."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = {
    "M1_second_dispatch_validation": (
        '                domain, context, _ = self._revalidate(db, payload, exclude=payload["id"])',
        "                pass",
    ),
    "M2_unknown_reservations": (
        "(p.status IN ('RESERVED','UNKNOWN') OR",
        "(p.status IN ('RESERVED') OR",
    ),
    "M3_reconciliation_fingerprint": (
        'if domain.fingerprint != payload["domain_hash"]:',
        "if False:",
    ),
    "M4_permit_expiry": ('or payload["expires"] <= self.clock()', "or False"),
    "M5_approval_evidence": ('and approval["evidence_hash"] == digest(evidence.model_dump())', ""),
    "M6_approval_expiry": ('and approval["expires"] > self.clock()', ""),
    "M7_pending_evaluation": (
        "            self._pending(db, rid)\n            domain = self._domain",
        "            domain = self._domain",
    ),
    "M8_revocation": (
        "db.execute(\"UPDATE permits SET status='REVOKED' WHERE id=?\", (permit_id,))",
        "pass",
    ),
    "M9_approval_generation": ('and approval["reviewer_version"] == approval["generation"]', ""),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    test = ROOT / "tests/test_corrective_release.py"
    runtime = ROOT / "src/decision_firewall/core/runtime.py"
    original = runtime.read_text(encoding="utf-8")
    observations = []
    with tempfile.TemporaryDirectory(prefix="firewall-mutations-") as directory:
        home = Path(directory)
        shutil.copytree(
            ROOT / "src/decision_firewall",
            home / "src/decision_firewall",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copy2(test, home / test.name)
        target = home / "src/decision_firewall/core/runtime.py"
        env = {**os.environ, "PYTHONPATH": str(home / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import decision_firewall, pathlib; "
                    "assert pathlib.Path(decision_firewall.__file__).resolve().is_relative_to("
                    "pathlib.Path('src').resolve())"
                ),
            ],
            cwd=home,
            env=env,
            check=True,
        )
        for name, mutation in [("baseline", None), *MUTATIONS.items()]:
            if mutation and original.count(mutation[0]) != 1:
                raise RuntimeError(f"Mutation {name} anchor must occur exactly once")
            target.write_text(
                original.replace(*mutation, 1) if mutation else original, encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", test.name],
                cwd=home,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            status = (
                ("PASS" if result.returncode == 0 else "ERROR")
                if mutation is None
                else (
                    "KILLED"
                    if result.returncode == 1
                    else "SURVIVED"
                    if result.returncode == 0
                    else "ERROR"
                )
            )
            observations.append(
                {
                    "name": name,
                    "status": status,
                    "failed_tests": [
                        line for line in result.stdout.splitlines() if line.startswith("FAILED ")
                    ],
                }
            )
            print(name, status, flush=True)
            if mutation is None and status != "PASS":
                raise RuntimeError("Unmutated baseline must pass before scoring mutations")
    report = {
        "scope": "Nine fault classes from the independent review; targeted corrective tests only",
        "generation_mutation": "M9 updated for latest-review-first selection; same removed invariant",
        "runtime_sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
        "tests_sha256": hashlib.sha256(test.read_bytes()).hexdigest(),
        "python": sys.version.split()[0],
        "observations": observations,
        "counts": {
            s: sum(o["status"] == s for o in observations[1:])
            for s in ("KILLED", "SURVIVED", "ERROR")
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["counts"]["KILLED"] == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
