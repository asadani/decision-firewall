"""Publish only synthetic observations/assessments; never copy runtime stores or permits."""

import argparse
import ast
import csv
import html
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "model_direct": "Model-directed",
    "application": "Application controls",
    "firewall": "Decision Firewall",
}
METRICS = {
    "episodes": "Scenario trials",
    "requests": "Request trials",
    "policy_matches": "Initial policy matches",
    "effects": "Completed simulated refunds",
    "unsafe_attempts": "Unsafe processor calls",
    "unsafe_effects": "Contract-violating effects",
    "duplicate_effects": "Duplicate effects (subset of violations)",
    "over_refund_minor": "Over-refunded minor units",
    "missed_expected_effects": "Expected successful effects missed",
    "unresolved": "Unresolved attempts after recovery",
    "review_count": "Initial review referrals",
    "straightforward_p50_ms": "Matched straightforward success p50, ms",
    "straightforward_p95_ms": "Matched straightforward success p95, ms",
    "setup_p50_ms": "Initial storage/key setup p50, ms",
}


def clean(value):
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def publish(inputs, destination):
    destination.mkdir(parents=True, exist_ok=False)
    reports = [json.loads((path / "results.json").read_text(encoding="utf-8")) for path in inputs]
    if len({(r["manifest"]["protocol_hash"], r["manifest"]["dataset_hash"]) for r in reports}) != 1:
        raise ValueError("Reports must use the same frozen protocol and cases")
    source = ROOT / "benchmarks/framework_value/application.py"
    app_lines = len(
        [line for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    )
    runner_source = (ROOT / "benchmarks/framework_value/runner.py").read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.parse(runner_source).body
        if isinstance(n, ast.ClassDef) and n.name == "Governed"
    )
    adapter_lines = len(
        [
            line
            for line in runner_source.splitlines()[node.lineno - 1 : node.end_lineno]
            if line.strip()
        ]
    )
    core_lines = sum(
        len([line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()])
        for p in (ROOT / "src/decision_firewall/core").glob("*.py")
    )
    text = [
        "# With and without Decision Firewall",
        "",
        "Paired synthetic diagnostic results. The competent application baseline is the primary comparator; direct model routing is a deliberately minimal reference arm.",
        "",
        "## What was held constant",
        "",
        "The 32 frozen scenarios contain 34 requests per pass, including two concurrent pairs. Five repetitions give 160 scenario trials and 170 request trials per arm and provider condition. Repetitions are runtime samples, not additional independent efficacy cases. All arms receive identical applied model signals, requests, evidence and fault schedules, and use the same payment simulator with balance/destination/idempotency protections enabled.",
        "",
        "Cases were designed with knowledge of the implementation. This is not a held-out model accuracy benchmark or production effectiveness estimate. Two declared model-fault cases inject disagreement/unavailability even in the Laya condition; raw outputs and applied labels are recorded separately.",
        "",
    ]
    sections = []
    for path, report in zip(inputs, reports, strict=True):
        provider = report["manifest"]["provider"]
        if report["manifest"]["diagnostic_only"]:
            raise ValueError("Do not publish a smoke run as the full comparison")
        assessments = json.loads((path / "assessments.json").read_text(encoding="utf-8"))
        for filename in ("results.json", "observations.csv", "assessments.json", "manifest.json"):
            (destination / f"{provider}-{filename}").write_bytes((path / filename).read_bytes())
        table = [
            f"## {provider}",
            "",
            "| Measurement | Model-directed | Application controls | Decision Firewall |",
            "|---|---:|---:|---:|",
        ]
        summaries = report["summaries"]
        for metric, name in METRICS.items():
            table.append(
                "| "
                + name
                + " | "
                + " | ".join(clean(summaries[arm][metric]) for arm in NAMES)
                + " |"
            )
        pair = summaries["paired_firewall_minus_application"]
        table += [
            "",
            f"Paired median framework overhead on matched straightforward successes: **{pair['median_ms']:.2f} ms**, n={pair['n']} paired trials. This is the median of within-case/repetition differences, not subtraction of unrelated percentiles. The matched set contains two basic eligibility patterns and three incentive-cue variants; it is small and synthetic.",
            "",
            f"Signed framework receipts verified: {summaries['firewall']['signed_receipts_verified']}/{summaries['firewall']['episodes']}. The application baseline has plain transactional audit records; signed receipt verification is unsupported there, not a failed-verification count.",
            "",
        ]
        if provider == "local_laya":
            metadata = assessments[0]["raw"]["metadata"]
            raw = assessments[0]["raw"]
            table += [
                f"Local model: `{raw['model']}` at `{raw['revision']}`; device `{metadata['device']}`, FP32, Laya SDK 0.3.20. Cold loading {metadata['cold_load_ms']:.2f} ms; median recorded inference {statistics.median(a['inference_ms'] for a in assessments):.2f} ms across {len(assessments)} request assessments (includes the first inference). Inference is reused and excluded from arm latency. Fallbacks: {sorted({str(a['raw']['metadata']['fallback']) for a in assessments})}. Confidence remains uncalibrated.",
                "",
            ]
        text.extend(table)
        rows = "".join(
            "<tr><th>"
            + html.escape(name)
            + "</th>"
            + "".join(f"<td>{clean(summaries[arm][metric])}</td>" for arm in NAMES)
            + "</tr>"
            for metric, name in METRICS.items()
        )
        chart = "".join(
            f"<div><span>{html.escape(NAMES[arm])}</span> <meter min='0' max='{max(1, max(summaries[a]['unsafe_effects'] for a in NAMES))}' value='{summaries[arm]['unsafe_effects']}'></meter> {summaries[arm]['unsafe_effects']} violating effects</div>"
            for arm in NAMES
        )
        case_rows = []
        for case in sorted({r["case"] for r in report["observations"]}):
            cells = []
            for arm in NAMES:
                samples = [
                    r for r in report["observations"] if r["case"] == case and r["arm"] == arm
                ]
                cells.append(
                    f"{sum(r['effects'] for r in samples)} effects / {sum(r['unsafe_effects'] for r in samples)} violations"
                )
            case_rows.append(
                "<tr><th>"
                + html.escape(case)
                + "</th>"
                + "".join(f"<td>{v}</td>" for v in cells)
                + "</tr>"
            )
        sections.append(
            f"<section><h2>{html.escape(provider)}</h2>{chart}<div class='scroll'><table><thead><tr><th>Measurement</th><th>Model-directed</th><th>Application controls</th><th>Decision Firewall</th></tr></thead><tbody>{rows}</tbody></table></div><p>Paired median framework overhead: <strong>{pair['median_ms']:.2f} ms</strong> (n={pair['n']}).</p><details><summary>All case-level differences</summary><div class='scroll'><table><thead><tr><th>Case</th><th>Model-directed</th><th>Application controls</th><th>Decision Firewall</th></tr></thead><tbody>{''.join(case_rows)}</tbody></table></div></details></section>"
        )
    both_equal = all(
        r["summaries"][a]["unsafe_effects"] == 0
        for r in reports
        for a in ("application", "firewall")
    )
    conclusion = (
        "The framework did not improve observed safety over the competent application baseline: both had zero violating effects. It added measured latency. Its demonstrated differences here are reusable lifecycle implementation and verified signed receipts, not unique safety capability."
        if both_equal
        else "The application/framework safety results differ. Inspect individual failures before attributing a general advantage; these cases cannot establish production effectiveness."
    )
    text += [
        "## Interpretation",
        "",
        conclusion,
        "",
        "The direct arm illustrates what goes wrong when favorable request classifications are mapped straight to actions without application controls. It is not evidence that Laya autonomously authorized these refunds, nor that a framework is the only remedy. Downstream balance/destination protections remain responsible for preventing some failures in every arm.",
        "",
        "Duplicate effects are included in contract-violating effects; do not add those columns. Over-refunding is separately measured against payment balance and may remain zero despite duplicate or ineligible refunds. Review referrals measure workflow burden, not reviewer time. A blocked malformed attempt does not mean the customer's underlying refund request is ineligible.",
        "",
        "## Engineering tradeoff",
        "",
        f"Nonblank source lines (including comments/docstrings): independent application policy/control module **{app_lines}**; benchmark framework integration class **{adapter_lines}**; reusable core package **{core_lines}**. The wrapper relies on the existing refund domain pack and core; these are not total-system size comparisons. The framework moves complexity into a dependency, it does not remove it. No developer-hour, productivity or maintenance-cost measurement was performed.",
        "",
        "Both governed approaches implement eligibility checks, review permissions, action/evidence binding, expiration/revocation, transactional resource reservations, durable attempt keys, reconciliation and required local audit. The framework additionally provides signed portable records, versioned policy replay and reusable domain interfaces; this experiment verifies receipts but does not quantitatively value long-term maintenance or independently benchmark every capability.",
        "",
        "## Limits and reproducibility",
        "",
        "Measured locally on Windows, Intel Core i5-9300H, approximately 8 GB RAM, GTX 1650 for Laya. Arms run in seeded randomized order; initialization is measured separately. Fresh-process recovery startup is included in lifecycle latency but is absent from the matched straightforward subset. Required local audit/simulator costs are included. No per-arm memory, throughput scalability or human integration-time claims are made.",
        "",
        "These are design-informed conformance cases with a fully specified favorable/other-classification execution mapping. No legal entitlement, production incident reduction, general model accuracy or compliance certification follows. The application baseline targets one daily budget window and one local process dispatch lock, as does this test. No real payment API was called.",
        "",
        "The one-pass diagnostic was retained under the ignored `.runtime-value/diagnostic-fixture` directory; it was not used to alter the frozen cases, rules or pass criteria. Public files contain synthetic observations and applied assessments only; runtime databases, signing keys and bearer permits are excluded.",
        "",
        "Reproduce with the [protocol and runner](../../../benchmarks/framework_value/README.md). Each result contains source hashes, protocol/dataset hashes, repetitions and environment metadata. Read all case-level outcomes before interpreting aggregate numbers.",
    ]
    (destination / "summary.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    title = "With and without Decision Firewall"
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{font:16px/1.6 system-ui;color:#142b42;background:#f5f7fa;margin:0}}main{{max-width:1150px;margin:auto;padding:32px 20px}}section,.finding{{background:white;padding:24px;margin:24px 0;border:1px solid #d6dfe8;border-radius:8px}}h1{{font-size:2.1rem;line-height:1.2}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #ddd}}table{{border-collapse:collapse;width:100%;font-size:.9rem}}.scroll{{overflow-x:auto}}meter{{width:180px}}meter::-webkit-meter-optimum-value{{background:#b54738}}meter::-moz-meter-bar{{background:#b54738}}summary{{cursor:pointer;padding:16px 0}}a{{color:#175ec4}}span{{display:inline-block;min-width:185px}}footer{{margin-top:32px;color:#43556a}}</style></head><body><main><p>SIMULATED • DESIGN-INFORMED DIAGNOSTIC</p><h1>{title}</h1><p>32 scenarios / 34 requests per pass; five repetitions per arm and provider condition. Repeated trials are not independent efficacy samples.</p><div class="finding"><strong>Measured conclusion</strong><p>{html.escape(conclusion)}</p></div>{"".join(sections)}<footer><p>All arms retain the same downstream balance and destination safeguards. Two model faults are explicitly injected. Direct routing is an intentionally minimal reference; the application baseline is the primary comparator.</p><p>See <a href="summary.md">full methodology, model details and limitations</a>. Raw JSON/CSV observations accompany this report. No model-accuracy or production-effectiveness claim.</p></footer></main></body></html>"""
    (destination / "report.html").write_text(document, encoding="utf-8")
    with (destination / "comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["provider", "arm", *METRICS])
        writer.writeheader()
        for report in reports:
            for arm in NAMES:
                writer.writerow(
                    {
                        "provider": report["manifest"]["provider"],
                        "arm": arm,
                        **{key: report["summaries"][arm][key] for key in METRICS},
                    }
                )
    print(destination / "summary.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    publish(args.inputs, args.destination)
