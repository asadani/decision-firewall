"""Generate measured full-source comparisons without raw requests or runtime stores."""

import csv
import json
import runpy
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / ".runtime-paired-public/measured"
    target = ROOT / "docs/benchmarks/paired-public"
    target.mkdir(parents=True, exist_ok=True)
    results = json.loads((source / "summary.json").read_text())
    shutil.copyfile(source / "manifest.json", target / "manifest.json")
    shutil.copyfile(source / "summary.json", target / "summary.json")
    coverage = {}
    for result in results:
        name = result["dataset"]
        seen = {arm: Counter() for arm in result["arms"]}
        with (source / name / "observations.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                seen[row["arm"]][row["index"]] += 1
        expected = Counter(range(result["source_rows_scored"]))
        if any(actual != expected for actual in seen.values()):
            raise ValueError(f"Missing or duplicate row coverage: {name}")
        coverage[name] = {
            arm: {"unique_rows": len(counts), "each_scored_once": True}
            for arm, counts in seen.items()
        }
        for filename in ("summary.json", "observations.csv", "observations.jsonl"):
            shutil.copyfile(source / name / filename, target / f"{name}-{filename}")
    (target / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    for name in ("tau2", "agentdojo"):
        path = ROOT / f".runtime-agent-sources/{name}-manifest.json"
        if path.exists():
            shutil.copyfile(path, target / f"{name}-source-manifest.json")
    availability = {
        "tau_bench": "not_run",
        "agentdojo": "not_run",
        "requested_backend": "existing local endpoint",
        "missing": [
            "local endpoint URL",
            "conversational tool-calling model name",
            "governed tool-boundary integrations",
        ],
        "probed_endpoints": {
            "http://127.0.0.1:11434/api/tags": "connection failed",
            "http://127.0.0.1:1234/v1/models": "connection failed",
            "http://127.0.0.1:8000/v1/models": "connection failed",
        },
        "scope": "Connection failures do not establish that no other server exists. No agent task-success score is reported.",
    }
    (target / "agent-suite-status.json").write_text(
        json.dumps(availability, indent=2), encoding="utf-8"
    )
    table_rows = []
    lines = [
        "# Full-data before/after results",
        "",
        (
            "For the unchanged classifier on these datasets, the framework produced no accuracy gain. "
            "It added measured latency. Preparation also supplied signed records, but those records are "
            "not needed to improve a pure intent classifier. These results do not establish whether "
            "governance improves an agent's actions: no action-execution benchmark was run here."
        ),
        "",
        (
            "Measured on Windows, Python 3.12.14, Intel i5-9300H, approximately 8 GB RAM. CPU naive Bayes, "
            "not Laya. Optional external telemetry disabled. One full pass with paired shuffled arm order. "
            "The desktop was not an isolated performance lab; treat latency as local measurements, not "
            "production guarantees or statistical significance evidence."
        ),
        "",
        "## All source rows are accounted for",
        "",
        "| Dataset / evaluation | Rows | Direct accuracy | SDK assessment accuracy | Prepared accuracy | Prediction changes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        name, arms = result["dataset"], result["arms"]
        lines.append(
            f"| {name} | {result['source_rows_scored']:,} | "
            f"{arms['direct']['accuracy']:.2%} | {arms['framework_assess']['accuracy']:.2%} | "
            f"{arms['framework_prepared']['accuracy']:.2%} | "
            f"{arms['framework_prepared']['prediction_disagreements_with_direct']} |"
        )
        for arm, metrics in arms.items():
            table_rows.append(
                {
                    "dataset": name,
                    "arm": arm,
                    "n": metrics["n"],
                    "accuracy": metrics["accuracy"],
                    "macro_f1": metrics["macro_f1"],
                    "p50_ms": metrics["p50_ms"],
                    "p95_ms": metrics["p95_ms"],
                    "paired_delta_p50_ms": metrics.get("paired_delta_p50_ms", 0),
                    "invalid_outputs": metrics["invalid_outputs"],
                }
            )
    total = sum(r["source_rows_scored"] for r in results)
    lines += [
        "",
        (
            f"Total: {total:,} source rows and {total * 3:,} measured arm observations. "
            "BANKING77 contributes all 13,083 rows; Bitext contributes all 26,872 rows. "
            "This does not pool training-fold predictions with the official BANKING77 test score. "
            "The official 3,080 test cases use a model fitted on all 10,003 original training rows. "
            "The additional training-row score uses five out-of-fold models fitted without each "
            "evaluated fold. Official test examples are never used for fitting."
        ),
        "",
        (
            "All Bitext rows receive one held-out prediction using our five-fold split. It has no "
            "publisher-supplied test split here, so this is not a standard leaderboard score. Only "
            "the instruction text reaches the model. Response text, coarse category, flags and "
            "expected intent are excluded from prediction input."
        ),
        "",
        "## Measured latency",
        "",
        "| Dataset | Path | n | p50 ms | p95 ms | Paired median added ms |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in table_rows:
        lines.append(
            f"| {row['dataset']} | {row['arm']} | {row['n']:,} | {row['p50_ms']:.3f} | "
            f"{row['p95_ms']:.3f} | {row['paired_delta_p50_ms']:.3f} |"
        )
    lines += [
        "",
        (
            "The direct path returns a typed Assessment from the same classifier. The SDK-only "
            "path additionally validates and hashes the assessment through DecisionFirewall.assess. "
            "The prepared path calls prepare and assess_prepared: requester checks, empty evidence "
            "resolution, bounded unchanged input, signed preparation and assessment records, and "
            "freshness checks. There are no evidence-based shortcuts in this classification task. "
            "Every arm makes one fresh classifier call per row. No predictions are cached or copied "
            "between arms. No accuracy-enhancing prompt/context/model change is involved."
        ),
        "",
        (
            "These timings exclude runtime initialization and model fitting, which are recorded "
            "separately. The full action lifecycle (policy, authorization, dispatch, reconciliation) "
            "is not timed here. Do not describe the prepared column as the cost of all firewall "
            "features. One runtime per dataset accumulates its audit; first/last-1000 timing "
            "diagnostics are retained in summary.json."
        ),
        "",
        "## Data quality and limits",
        "",
        (
            "Exact normalized duplicates stay in the same out-of-fold partition. BANKING77's official "
            "test retains its 25 normalized overlaps with training for split comparability; the earlier "
            "report also supplied the non-overlap baseline score. Out-of-fold comparisons report zero "
            "such training overlap. This does not remove semantic paraphrases or shared generation "
            "templates. Bitext is generated language data, so high scores can reflect template "
            "similarity and are not independent production-effectiveness evidence."
        ),
        "",
        (
            "All errors remain in denominators; see per-arm invalid-output counts and case-level "
            "observations. No post-result tuning, accuracy threshold, promotion or selective row "
            "omission was applied. The protocol and data hashes were frozen before these runs. "
            "Dataset row counts are not counts of independent business transactions."
        ),
        "",
        "## τ-bench and AgentDojo status",
        "",
        (
            "Not run. The user chose an existing local endpoint, but its URL/model have not been "
            "supplied; the usual Ollama, LM Studio and local OpenAI-compatible ports did not respond. "
            "Laya cannot substitute for the required conversational agent/user simulator. We inspected "
            "pinned upstream source and added a local endpoint/tool-roundtrip preflight. A governed "
            "tool-boundary adapter also remains to be implemented and validated. No connection failure "
            "or source inspection is reported as a task-success/security benchmark score."
        ),
        "",
        (
            "τ-bench pin: b7ea9074c1cba482b30687fecdb5c8425fd6f619 (tau2 1.0.1). "
            "AgentDojo pin: 089ed468cf3ed0322acc66b0211f26d9d90dbf60 (package 0.1.35, "
            "versioned suites). See benchmarks/agent_suites/README.md for concrete prerequisites "
            "and the preflight command. Compare identical agents with no controls, application "
            "controls and equivalent firewall controls; preserve task grading and report benign "
            "utility as well as adversarial success. Hidden task solutions cannot enter the policy."
        ),
        "",
        "## Recommendation from these results",
        "",
        (
            "For a standalone intent classifier, use the direct path unless typed validation or "
            "audit records are independently needed. The framework has not earned an accuracy claim "
            "here. Its execution-governance value must be judged on tasks involving actual proposed "
            "actions, trusted evidence and constraints. Existing synthetic control-parity results "
            "remain relevant, but do not replace the pending agent suites."
        ),
        "",
        "## Reproduction and attribution",
        "",
        (
            "Run python -m benchmarks.paired_public.runner --output .runtime-paired-public/measured "
            "with a new output directory, then python scripts/report-paired-public.py. Raw CSVs are "
            "hash-checked in an ignored cache. Runtime databases, original message texts and signing "
            "keys are excluded from this report. Manifests, per-row CSV/JSONL, summary.json and "
            "comparison.csv accompany it."
        ),
        "",
        (
            "BANKING77: PolyAI and Casanueva et al., Efficient Intent Detection with Dual Sentence "
            "Encoders (2020), CC-BY-4.0; https://github.com/PolyAI-LDN/task-specific-datasets . "
            "Bitext: Bitext Innovations (2024), CDLA-Sharing-1.0; "
            "https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset . "
            "Dataset-derived observations retain upstream rights. New code is Apache-2.0."
        ),
    ]
    summary = "\n".join(lines) + "\n"
    (target / "summary.md").write_text(summary, encoding="utf-8")
    with (target / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table_rows[0]))
        writer.writeheader()
        writer.writerows(table_rows)
    render = runpy.run_path(str(ROOT / "scripts/report-reuse-observability.py"))["report_body"]
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Full-data before/after</title>
<style>body{font:16px/1.6 system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#172b43}
h1{line-height:1.2}h2{margin-top:36px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:9px;border-bottom:1px solid #cad5e4}th{background:#edf4ff}
p{overflow-wrap:anywhere}a{color:#145bc1}</style>
<h1>Full-data before/after measurements</h1>
<p><a href="comparison.csv">Comparison CSV</a> · <a href="summary.md">Markdown</a> ·
<a href="agent-suite-status.json">Agent suite status</a></p>"""
    (target / "report.html").write_text(page + render(summary) + "</html>", encoding="utf-8")


if __name__ == "__main__":
    main()
