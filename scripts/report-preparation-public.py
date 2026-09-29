"""Publish sanitized preparation observations and attributed public-data results."""

import csv
import json
import runpy
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "docs/benchmarks/preparation-and-public"
    output.mkdir(parents=True, exist_ok=True)
    sources = {
        "preparation": ROOT / ".runtime-preparation/measured",
        "banking77-full": ROOT / ".runtime-public-data/full-test",
        "banking77-1k": ROOT / ".runtime-public-data/test-1k",
    }
    summaries = {}
    for prefix, source in sources.items():
        summaries[prefix] = json.loads((source / "summary.json").read_text())
        for name in ("manifest.json", "summary.json", "observations.json", "observations.csv"):
            if (source / name).exists():
                shutil.copyfile(source / name, output / f"{prefix}-{name}")
    observations = json.loads((sources["preparation"] / "observations.json").read_text())
    with (output / "preparation-observations.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(observations[0]))
        writer.writeheader()
        writer.writerows(observations)
    lines = [
        "# Preparation and public benchmark measurements",
        "",
        (
            "Measured September 28, 2026 on Windows, Python 3.12.14, Intel i5-9300H, approximately "
            "8 GB RAM. CPU only. No paid APIs, external telemetry services or model downloads."
        ),
        "",
        "## Before-model preparation",
        "",
        "| Arm | Cases | Expected outcomes matched | Model calls | Operation p50 ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm, row in summaries["preparation"].items():
        lines.append(
            f"| {arm} | {row['n']} | {row['matches']} | {row['model_calls']} | {row['p50_ms']:.2f} |"
        )
    lines += [
        "",
        (
            "The declared mix has 50 model-needed, 50 structured deterministic, 50 missing-evidence "
            "and 50 mandatory-restriction cases. Preparation avoids 150 of 200 model calls (75%) by "
            "construction of that workload. This is not an estimated production avoidance rate. "
            "Both arms use the same final governance gate; this is not a comparison against a "
            "well-engineered application baseline. Stopped preparations are compared to expected "
            "prerequisite outcomes, not described as final decisions. No effects were dispatched."
        ),
        "",
        (
            "The fixture adds no inference delay. Preparation adds evidence reads, signed records and "
            "freshness checks, so its observed median is higher. Real-model savings depend on the "
            "actual share of avoidable calls and their cost. Do not subtract these mixture medians "
            "to predict production savings or infer better model accuracy."
        ),
        "",
        "## BANKING77 intent benchmark",
        "",
        "| Evaluation | Train rows | Test rows | Accuracy | Macro-F1 | Normalized train overlaps |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("banking77-1k", "banking77-full"):
        row = summaries[name]
        lines.append(
            f"| {name} | {row['train_n']} | {row['n']} | {row['accuracy']:.2%} | "
            f"{row['macro_f1']:.2%} | {row['train_overlap']} |"
        )
    full = summaries["banking77-full"]
    lines += [
        "",
        (
            "Both runs use the same fixed unigram multinomial naive Bayes implementation with "
            "Laplace alpha=1 and empirical class priors. It trains only on the official training split. "
            "The 1K subset is sampled without replacement with seed 20260928. All 77 labels are "
            "represented; invalid outputs and missing labels are zero. These are baseline model "
            "scores, not Laya scores or improvements attributable to the firewall."
        ),
        "",
        (
            f"Full-test non-overlap accuracy is {full['nonoverlap_accuracy']:.2%} on "
            f"{full['nonoverlap_n']} examples. Normalization casefolds text and tokenizes word "
            "characters. This detects exact normalized overlap, not semantic paraphrase leakage. "
            f"Full-test inference p50/p95 is {full['p50_ms']:.3f}/{full['p95_ms']:.3f} ms; "
            f"training took {full['training_ms']:.2f} ms. Macroscopic accuracy is not a "
            "measure of authorization or refund eligibility."
        ),
        "",
        (
            "BANKING77 has 10,003 training rows but only 3,080 test rows. The runner refuses a 10K "
            "test request; copying training examples into evaluation would inflate the evidence. "
            "The original test split remains intact and the overlap-filtered score is supplemental. "
            "No prompt variants or hyperparameters were selected after inspecting these results. "
            "Future fixes informed by this test set should explicitly mark it development-informed."
        ),
        "",
        "## Scope and provenance",
        "",
        (
            "The preparation protocol was declared before its run. The BANKING77 source revision "
            "and file hashes were pinned before training/evaluation. Manifests and case-level "
            "JSON/CSV observations accompany this report. Runtime databases, private signing keys, "
            "permits and raw source texts are not published. The implementation remains a local "
            "sandbox; no production effectiveness or developer productivity claim is made."
        ),
        "",
        (
            "BANKING77 attribution: Iñigo Casanueva, Tadas Temčinas, Daniela Gerz, Matthew Henderson "
            "and Ivan Vulić, Efficient Intent Detection with Dual Sentence Encoders, NLP for ConvAI / "
            "ACL 2020; PolyAI, CC-BY-4.0. Dataset-derived observation files retain those rights; "
            "new framework and benchmark code is Apache-2.0. Original source: "
            "https://github.com/PolyAI-LDN/task-specific-datasets ."
        ),
        "",
        "## Reproduce",
        "",
        (
            "Run the commands in benchmarks/preparation/README.md and "
            "benchmarks/public_intent/README.md from the repository. Run "
            "python scripts/report-preparation-public.py after the documented measured run paths "
            "exist. See docs/benchmarks/public-datasets.md for Bitext, τ-bench and AgentDojo options. "
            "Those additional suites were researched, not executed."
        ),
    ]
    summary = "\n".join(lines) + "\n"
    (output / "summary.md").write_text(summary, encoding="utf-8")
    render = runpy.run_path(str(ROOT / "scripts/report-reuse-observability.py"))["report_body"]
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Preparation and BANKING77 measurements</title>
<style>body{font:16px/1.65 system-ui;color:#172b43;max-width:1050px;margin:40px auto;padding:0 20px}
h1{line-height:1.2}h2{margin-top:36px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:10px;border-bottom:1px solid #cad5e4}th{background:#edf4ff}
p{overflow-wrap:anywhere}a{color:#145bc1}</style>
<h1>Preparation and public benchmark measurements</h1>
<p><a href="preparation-observations.csv">Preparation CSV</a> ·
<a href="banking77-full-observations.csv">BANKING77 CSV</a> · <a href="summary.md">Markdown</a></p>"""
    (output / "report.html").write_text(page + render(summary) + "</html>", encoding="utf-8")


if __name__ == "__main__":
    main()
