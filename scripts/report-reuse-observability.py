"""Publish selected synthetic observations, never runtime credentials or stores."""

import argparse
import ast
import csv
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inventory():
    folder = ROOT / "benchmarks/reuse_observability"
    counts = {
        name: sum(bool(line.strip()) for line in (folder / name).read_text().splitlines())
        for name in ("application.py", "framework.py", "policies.py", "service.py")
    }
    tree = ast.parse((folder / "application.py").read_text())
    counts["application_note_calls"] = sum(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "note"
        for n in ast.walk(tree)
    )
    counts["application_operation_decorators"] = sum(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "operation"
        for n in ast.walk(tree)
    )
    counts["framework_integration_event_hooks"] = 0
    counts["shared_export_v2_nonblank_lines"] = 4
    counts["refund_configuration_fields_changed"] = 1
    counts["export_configuration_fields_changed"] = 2
    counts["reused_core_library_nonblank_lines"] = sum(
        sum(bool(line.strip()) for line in p.read_text(encoding="utf-8").splitlines())
        for p in (ROOT / "src/decision_firewall/core").glob("*.py")
    )
    return counts


def report_body(summary):
    """Render this report's controlled headings, paragraphs and tables without dependencies."""
    blocks = []
    for block in summary.strip().split("\n\n"):
        lines = block.splitlines()
        if lines[0].startswith("| "):
            rows = [
                [html.escape(cell.strip()) for cell in line.strip("|").split("|")] for line in lines
            ]
            header = "<tr>" + "".join(f"<th>{cell}</th>" for cell in rows[0]) + "</tr>"
            body = "".join(
                "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows[2:]
            )
            blocks.append(
                "<div class='table'><table><thead>"
                + header
                + "</thead><tbody>"
                + body
                + "</tbody></table></div>"
            )
        elif block.startswith("## "):
            blocks.append("<h2>" + html.escape(block[3:]) + "</h2>")
        elif block.startswith("# "):
            continue
        else:
            blocks.append("<p>" + html.escape(block) + "</p>")
    return "".join(blocks)


def publish(conformance, telemetry, output):
    output.mkdir(parents=True, exist_ok=True)
    for folder, names in (
        (conformance, ["conformance.json", "manifest.json", "acceptance.json"]),
        (
            telemetry,
            [
                "latency.json",
                "latency-summary.json",
                "telemetry-profiles.json",
                "manifest.json",
                "acceptance.json",
                "modular_application-spans.json",
                "firewall-spans.json",
            ],
        ),
    ):
        for name in names:
            prefix = (
                ("conformance-" if folder == conformance else "telemetry-")
                if name in {"manifest.json", "acceptance.json"}
                else ""
            )
            shutil.copyfile(folder / name, output / (prefix + name))
    rows = read(conformance / "conformance.json")
    latency = read(telemetry / "latency-summary.json")
    profiles = read(telemetry / "telemetry-profiles.json")
    counts = inventory()
    (output / "engineering.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    with (output / "latency.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["arm", "telemetry", "repetition", "operation_ms", "setup_ms", "drain_ms"])
        for row in read(telemetry / "latency.json"):
            writer.writerow(
                [
                    row[k]
                    for k in (
                        "arm",
                        "telemetry",
                        "repetition",
                        "operation_ms",
                        "setup_ms",
                        "drain_ms",
                    )
                ]
            )
    lines = [
        "# Does the framework earn its overhead?",
        "",
        (
            "Measured locally on Windows, Python 3.12.14, Intel i5-9300H, approximately 8 GB RAM. "
            "Fixture models; no GPU inference. Optional OpenTelemetry SDK 1.45.0. All effects simulated."
        ),
        "",
        "## Findings",
        "",
        (
            "The framework and a competent modular application matched the frozen safety expectations. "
            "The demonstrated distinction is reusable lifecycle implementation and signed audit, not "
            "better business decisions. A modular application can also reuse its controls across domains."
        ),
        "",
        "| Arm | Conformance | Extra effects versus expected |",
        "|---|---:|---:|",
    ]
    for arm in ("modular_application", "firewall"):
        samples = [r for r in rows if r["arm"] == arm]
        lines.append(
            f"| {arm} | {sum(r['passed'] for r in samples)}/{len(samples)} | "
            f"{sum(max(0, r['effects'] - r['expected_effects']) for r in samples)} |"
        )
    lines += [
        "",
        (
            "60 cases per arm: 15 families × two domains × two policy/configuration versions. "
            "One deterministic pass, not 60 independent real-world safety observations."
        ),
        "",
        "## Latency",
        "",
        "| Arm / telemetry | n | p50 ms | p95 ms | Setup p50 ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, value in latency.items():
        if "p50_ms" in value:
            lines.append(
                f"| {key} | {value['n']} | {value['p50_ms']:.2f} | "
                f"{value['p95_ms']:.2f} | {value['setup_p50_ms']:.2f} |"
            )
    lines += [
        "",
        (
            "Operation timing includes assessment, authorization and one simulated effect; "
            "initialization and final exporter drain are separate. Fifty seeded shuffled paired "
            "repetitions per condition, same in-memory exporter. No hosted service latency is measured."
        ),
        "",
        (
            "Paired median telemetry on-minus-off: application "
            f"{latency['modular_application-paired-telemetry']['median_ms']:.2f} ms; framework "
            f"{latency['firewall-paired-telemetry']['median_ms']:.2f} ms. Negative deltas reflect "
            "measurement variability, not evidence that telemetry makes execution faster. "
            "This run does not resolve a stable incremental telemetry cost. The full framework "
            "has a higher observed operation median in both conditions. No statistical p-value "
            "or production latency guarantee is claimed."
        ),
        "",
        "## Audit and observability",
        "",
        "| Check | Modular application | Framework |",
        "|---|---|---|",
    ]
    for title, key in (("Lifecycle stages", "stages"), ("Exported metadata", "fields")):
        for name in profiles["firewall"][key]:
            values = [
                "yes" if profiles[a][key][name] else "missing"
                for a in ("modular_application", "firewall")
            ]
            lines.append(f"| {title}: {name} | {' | '.join(values)} |")
    lines += [
        "| Trace linkage across process restart | yes | yes |",
        "| Assessment linkage | yes | yes |",
        "| Exported sensitive canaries | 0/4 | 0/4 |",
        "| Observer callbacks under write lock | 0/14 | 0/20 |",
        "| Successful effect despite exporter failure | 1/1 | 1/1 |",
        "| Required audit outage blocks effect | yes | yes |",
        "| Signed receipt verification and tamper rejection | unsupported | 60/60 |",
        "",
        (
            "The framework supplies eight lifecycle stages without application event hooks. "
            "However its ordinary callable-policy path lacks evaluation ID, policy version, "
            "disposition and reasons in exported spans. The manually instrumented application "
            "supplies the first three; the shared export allowlist omits reasons for both. "
            "Named RuleSet paths may emit additional metadata and were not measured here. "
            "These are observed gaps in the measured implementation, left unchanged during the study."
        ),
        "",
        (
            "Actual loopback OTLP/HTTP spans were collected before and after a fresh Python "
            "process reconciled a lost response. Export failure diagnostics recorded 14 failed "
            "exports for the application and 20 for the framework. Both completed their effect. "
            "The common bounded adapter held 8 queued events and dropped 992 of 1000 new events "
            "while export was blocked; diagnostics exposed the drops and the queue drained afterward."
        ),
        "",
        (
            "Local audit retains evidence and model details; external telemetry excludes the "
            "four request/evidence/model/credential canaries. Signed receipts detect altered history "
            "given a trusted public key; they do not protect a fully compromised signing host. "
            "The application logs are unsigned by design: signing is extra functionality bundled "
            "by the framework, not something an application cannot implement."
        ),
        "",
        "## Reuse and owned implementation",
        "",
        (
            f"Application runtime: {counts['application.py']} nonblank lines; framework integration: "
            f"{counts['framework.py']} nonblank lines. Shared business policies: {counts['policies.py']}; "
            f"shared fake service: {counts['service.py']}. The reused core library itself contains "
            f"{counts['reused_core_library_nonblank_lines']} nonblank lines. These include imports, "
            "comments and docstrings; integration includes benchmark API wrappers. They are source "
            "inventory, not equivalent functionality, productivity, security or maintenance scores."
        ),
        "",
        (
            f"The application has {counts['application_note_calls']} explicit note call sites and "
            f"{counts['application_operation_decorators']} operation decorators; the framework "
            "integration has zero event hooks and passes an observer to its SDK. Both share the "
            "standalone exporter utility. Users can adopt that utility without the full runtime."
        ),
        "",
        (
            "Both arms reuse the same lifecycle code for refunds and data export. Both consume "
            "the same shared policy change: one refund configuration field, two export configuration "
            "fields, and a four-nonblank-line export-v2 function adding the mandatory legal-hold check. "
            "No lifecycle implementation changes were needed between those variants. Thus this "
            "experiment does not show easier business-rule editing than a modular application. "
            "It shows an existing runtime replaces code the application otherwise owns. No human "
            "onboarding, development hours, diagnosis time or ROI was measured."
        ),
        "",
        "## Interpretation and limitations",
        "",
        (
            "Use the framework when standardized authorization/recovery/audit across several "
            "workflows is worth owning less lifecycle code and accepting its runtime cost. "
            "An application that already has these controls may gain little from migration. "
            "Telemetry alone does not justify the entire runtime: reuse the observer utility or "
            "existing instrumentation. The strongest demonstrated extra here is supplied lifecycle "
            "instrumentation plus signed audit; exported policy metadata still needs improvement."
        ),
        "",
        (
            "The application was deliberately allowed sensible modularization. Shared policy "
            "functions eliminate business-logic differences, so agreement is partly by construction; "
            "the adversarial cases test lifecycle enforcement. One author implemented both adapters. "
            "This is a local synthetic, design-informed study, not an independent productivity trial. "
            "No model accuracy improvement is asserted. No production core files were changed to "
            "improve measured results. The first diagnostic stopped on the harness's incorrect "
            "assumption that tamper verification returns false rather than raising ValueError; "
            "that harness bug was corrected before the completed run. Frozen cases stayed unchanged."
        ),
        "",
        "## Reproduce",
        "",
        (
            "See ../../../benchmarks/reuse_observability/README.md in the "
            "repository. Manifests contain protocol, case and source hashes. JSON observations, "
            "latency.csv, engineering.json and redacted OTLP spans accompany this report. "
            "Runtime stores, permits and signing keys are excluded."
        ),
    ]
    summary = "\n".join(lines) + "\n"
    (output / "summary.md").write_text(summary, encoding="utf-8")
    bars = "".join(
        f"<div><span>{html.escape(key)}</span><meter min='0' max='60' "
        f"value='{value['p50_ms']}'></meter> {value['p50_ms']:.2f} ms</div>"
        for key, value in latency.items()
        if "p50_ms" in value
    )
    page = (
        """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Decision Firewall: reuse and observability results</title>
<style>body{font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:0 20px;color:#172b43}
h1{line-height:1.2}p{overflow-wrap:anywhere}h2{margin-top:32px}
.table{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:9px;border-bottom:1px solid #cad5e4}th{background:#edf4ff}
meter{width:30%;margin:0 12px}span{display:inline-block;min-width:240px}
section{background:#edf4ff;padding:20px;border-radius:12px}a{color:#145bc1}</style>
<h1>Reuse, audit and observability</h1><p>Measured results • Synthetic effects • September 2026</p>
<section><h2>Operation median (lower is faster)</h2>"""
        + bars
        + "</section>"
    )
    page += "<p><a href='latency.csv'>CSV measurements</a> · <a href='summary.md'>Markdown report</a></p>"
    page += report_body(summary) + "</html>"
    (output / "report.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("conformance", type=Path)
    parser.add_argument("telemetry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    publish(args.conformance, args.telemetry, args.output)
