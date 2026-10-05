"""Measure the bounded pilot and six declared behavioural fault injections."""

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

from control_conformance.runner import CHECKS, run

from .adapters import Bridge

ROOT = Path(__file__).resolve().parents[2]


def expected_result(report, fault):
    return (
        {r["case"] for r in report["checks"]} == set(CHECKS)
        and all(
            row["status"] == ("FAIL" if row["case"] == fault else "PASS")
            for row in report["checks"]
        )
        and len(report["checks"]) == len(CHECKS)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    measurements = []
    for arm in ("application", "framework"):
        for fault in (None, *CHECKS):
            started = time.perf_counter()
            report = run(
                lambda home, scenario, arm=arm, fault=fault: Bridge(home, scenario, arm, fault)
            )
            expected = expected_result(report, fault)
            measurements.append(
                {
                    "arm": arm,
                    "fault": fault,
                    "expected_result_observed": expected,
                    "elapsed_seconds": round(time.perf_counter() - started, 4),
                    "report": report,
                }
            )
    paths = sorted(
        [
            *(ROOT / "conformance/src").rglob("*.py"),
            *(ROOT / "benchmarks/control_conformance").glob("*.py"),
            *(ROOT / "benchmarks/reuse_observability").glob("*.py"),
            ROOT / "benchmarks/framework_value/application.py",
            *(ROOT / "src/decision_firewall/core").rglob("*.py"),
            ROOT / "tests/test_independent_conformance.py",
            ROOT / "conformance/pyproject.toml",
        ]
    )
    manifest = {
        "suite": "control-conformance-pilot-2",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_parent_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=ROOT
        ).strip(),
        "source_hash_encoding": "UTF-8 with CRLF normalized to LF",
        "source_hashes": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(
                p.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            for p in paths
        },
        "integration_inventory": {
            "required_protocol_methods": 6,
            "nonblank_lines_including_comments": {
                name: sum(
                    bool(line.strip())
                    for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
                )
                for name in (
                    "benchmarks/control_conformance/adapters.py",
                    "benchmarks/control_conformance/recover.py",
                    "benchmarks/reuse_observability/application.py",
                    "benchmarks/reuse_observability/framework.py",
                )
            },
            "interpretation": "Shared bridge/oracle plus reused engine source; not time saved or total system size",
        },
        "measurements": measurements,
        "limitations": [
            "Development-informed synthetic fixtures; one export domain",
            "Six injected behavioural faults, not mutation coverage",
            "No human productivity or production-effectiveness measurement",
            "Elapsed time includes fresh-interpreter recovery; not a performance benchmark",
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    rows = [
        "# Independent control-conformance pilot",
        "",
        "Measured on " + platform.platform() + ", Python " + platform.python_version() + ".",
        "",
        "| Arm | Injection | PASS | FAIL | ERROR | Expected result |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in measurements:
        c = item["report"]["counts"]
        rows.append(
            f"| {item['arm']} | {item['fault'] or 'healthy'} | {c['PASS']} | {c['FAIL']} | {c['ERROR']} | {item['expected_result_observed']} |"
        )
    rows += [
        "",
        *manifest["limitations"],
        "",
        "A detected fault must produce FAIL on its targeted case. ERROR does not count as detection.",
        "Source hashes and individual reasons are in results.json. Historical benchmark files are unchanged.",
    ]
    rows += [
        "",
        "## Integration inventory",
        "",
        "Six test protocol methods. Nonblank lines including comments:",
    ]
    rows += [
        f"- `{name}`: {count}"
        for name, count in manifest["integration_inventory"][
            "nonblank_lines_including_comments"
        ].items()
    ]
    rows += ["", manifest["integration_inventory"]["interpretation"]]
    (args.output / "summary.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("\n".join(rows))
    return 0 if all(r["expected_result_observed"] for r in measurements) else 1


if __name__ == "__main__":
    raise SystemExit(main())
