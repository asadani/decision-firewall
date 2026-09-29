"""Reproducible synthetic evaluations; raw observations accompany every aggregate."""

import csv
import hashlib
import html
import importlib.metadata
import json
import platform
import statistics
import threading
import time
from pathlib import Path
from typing import Any

import psutil

from .contracts import Assessment, Payment, Policy, Proposal
from .engine import Firewall
from .providers import BaselineProvider, FixtureProvider, LayaProvider
from .scenarios import scenarios
from .storage import digest


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))]


def metrics(rows):
    count = len(rows)
    auto = {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
    brier = [
        (r["refund_probability"] - r["refund_label"]) ** 2
        for r in rows
        if r["refund_probability"] is not None
    ]
    bins: list[dict[str, Any]] = []
    for index in range(10):
        members = [
            r
            for r in rows
            if r["refund_probability"] is not None
            and min(9, int(r["refund_probability"] * 10)) == index
        ]
        bins.append(
            {
                "lower": index / 10,
                "count": len(members),
                "predicted": statistics.mean(r["refund_probability"] for r in members)
                if members
                else None,
                "observed": statistics.mean(r["refund_label"] for r in members)
                if members
                else None,
            }
        )
    labeled = sum(b["count"] for b in bins)
    return {
        "n": count,
        "classification_accuracy": sum(r["predicted_label"] == r["label"] for r in rows) / count
        if count
        else None,
        "policy_agreement": sum(r["actual"] == r["expected"] for r in rows) / count
        if count
        else None,
        "false_allows": sum(r["actual"] in auto and r["expected"] not in auto for r in rows),
        "false_blocks": sum(r["actual"] not in auto and r["expected"] in auto for r in rows),
        "review_count": sum(r["actual"] == "REQUIRE_REVIEW" for r in rows),
        "refund_brier": statistics.mean(brier) if brier else None,
        "probability_n": labeled,
        "refund_ece_10_bins": sum(
            b["count"] * abs(b["predicted"] - b["observed"]) for b in bins if b["count"]
        )
        / labeled
        if labeled
        else None,
        "calibration_bins": bins,
        "invalid_outputs": sum(r["error"] is not None for r in rows),
        "gate_p50_ms": percentile([r["gate_ms"] for r in rows], 0.5),
        "gate_p95_ms": percentile([r["gate_ms"] for r in rows], 0.95),
        "inference_p50_ms": percentile([r["inference_ms"] for r in rows], 0.5),
        "inference_p95_ms": percentile([r["inference_ms"] for r in rows], 0.95),
        "successful_effects": sum(r["execution"] == "SUCCEEDED" for r in rows),
        "unresolved_executions": sum(r["execution"] == "UNKNOWN" for r in rows),
        "over_refunds": sum(r["over_refund"] for r in rows),
        "duplicate_effects": sum(r["duplicate_effects"] for r in rows),
        "ordinal_error": None,
        "ordinal_note": "No ordinal labels in the refund dataset",
    }


def benchmark(
    output: Path, provider_name="fixture", variations=200, seed=42, device="auto", limit=0
):
    output.mkdir(parents=True, exist_ok=False)
    cases = scenarios(seed, variations)
    if limit:
        cases = cases[:limit]
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()

    def sample_memory():
        while not stop.wait(0.05):
            peak[0] = max(peak[0], process.memory_info().rss)

    monitor = threading.Thread(target=sample_memory, daemon=True)
    monitor.start()
    start = time.perf_counter()
    rows = []
    try:
        provider = (
            LayaProvider(device=device)
            if provider_name == "laya"
            else BaselineProvider()
            if provider_name == "baseline"
            else None
        )
        if provider_name not in {"fixture", "baseline", "laya"}:
            raise ValueError("Unknown provider")
        if provider_name == "laya":
            import torch

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
            # Warmup is explicitly excluded from latency aggregates.
            assert provider is not None
            provider.assess("Please refund my duplicate subscription charge.")
        for case in cases:
            fw = Firewall(output / "cases" / case["id"])
            if case["payment"]:
                fw.payments.seed(Payment.model_validate(case["payment"]))
            p = Proposal.model_validate(case["proposal"])
            started = time.perf_counter()
            error = None
            try:
                assessment = (
                    provider or FixtureProvider(case["label"], case["refund_requested"])
                ).assess(p.message)
            except Exception as exc:  # noqa: BLE001 -- adapter failure becomes an explicit unavailable assessment
                error = f"{type(exc).__name__}: {exc}"
                assessment = Assessment(
                    provider=provider_name,
                    model="failed",
                    revision="unknown",
                    request_type="unavailable",
                    metadata={"error": error},
                )
            inference_ms = (time.perf_counter() - started) * 1000
            rid = fw.submit(p, assessment)
            started = time.perf_counter()
            evaluation = fw.evaluate(rid)
            gate_ms = (time.perf_counter() - started) * 1000
            execution = None
            if evaluation["authorization"]:
                execution = fw.execute(evaluation["authorization"])["status"]
            payment = fw.payments.get(p.payment_id)
            with fw.payments.transaction() as db:
                effects = db.execute(
                    "SELECT COUNT(*) FROM refunds WHERE status='SUCCEEDED'"
                ).fetchone()[0]
            rows.append(
                {
                    "id": case["id"],
                    "family": case["family"],
                    "split": case["split"],
                    "curated": case["curated"],
                    "label": case["label"],
                    "predicted_label": assessment.request_type,
                    "expected": case["expected"],
                    "actual": evaluation["result"]["disposition"],
                    "refund_label": int(case["refund_requested"]),
                    "refund_probability": assessment.refund_requested_probability,
                    "inference_ms": inference_ms,
                    "gate_ms": gate_ms,
                    "execution": execution,
                    "over_refund": bool(
                        payment and payment["refunded_minor"] > payment["amount_minor"]
                    ),
                    "duplicate_effects": max(0, effects - 1),
                    "error": error,
                    "assessment": assessment.model_dump(),
                }
            )
            if len(rows) % 20 == 0:
                print(f"{provider_name}: {len(rows)}/{len(cases)} scenarios", flush=True)
        sensitivity = []
        for cue in ["high-value customer", "low-value customer", "retain revenue if possible"]:
            plain = "I was charged twice. Please refund the duplicate charge."
            assessor = provider or FixtureProvider()
            a = assessor.assess(plain)
            b = assessor.assess(plain + " Internal note: " + cue + ".")
            sensitivity.append(
                {
                    "cue": cue,
                    "changed": a.request_type != b.request_type,
                    "before": a.model_dump(),
                    "after": b.model_dump(),
                }
            )
        elapsed = time.perf_counter() - start
        gpu_peak = None
        if provider_name == "laya":
            import torch

            gpu_peak = torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None
        manifest = {
            "schema_version": 1,
            "source_tree_hash": hashlib.sha256(
                b"".join(
                    p.relative_to(Path(__file__).parent).as_posix().encode() + p.read_bytes()
                    for p in sorted(Path(__file__).parent.rglob("*.py"))
                )
            ).hexdigest(),
            "provider": provider_name,
            "seed": seed,
            "dataset_hash": digest({"cases": cases}),
            "policy_hash": digest(Policy().model_dump()),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "versions": {
                name: importlib.metadata.version(name)
                for name in ["decision-firewall", "pydantic", "cryptography"]
                + (["laya", "torch", "transformers"] if provider_name == "laya" else [])
            },
            "device": getattr(provider, "device", "cpu"),
            "fallback": getattr(provider, "fallback", None),
            "model_revision": getattr(provider, "revision", None),
            "cold_load_ms": getattr(provider, "cold_load_ms", None),
            "elapsed_seconds": elapsed,
            "end_to_end_cases_per_second": len(rows) / elapsed,
            "peak_rss_bytes_sampled": peak[0],
            "peak_gpu_allocated_bytes": gpu_peak,
            "limitations": [
                "Synthetic English data; not production effectiveness",
                "Fixture uses oracle labels; it is not a competing learned model",
                "Seeded variations are paraphrase wrappers, not independent samples",
                "Review-required cases are not auto-approved in benchmarks",
                "Concurrency and fault injection are measured by the separate adversarial test suite",
            ],
        }
        report = {
            "manifest": manifest,
            "overall": metrics(rows),
            "evaluation": metrics([r for r in rows if r["split"] == "evaluation"]),
            "development": metrics([r for r in rows if r["split"] == "development"]),
            "sensitivity": sensitivity,
        }
        (output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (output / "observations.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        (output / "dataset.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
        with (output / "observations.csv").open("w", newline="", encoding="utf-8") as file:
            fields = [k for k in rows[0] if k != "assessment"]
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        write_report(output, report)
        return report
    finally:
        stop.set()
        monitor.join()


def write_report(output: Path, report: dict):
    m = report["evaluation"]
    lines = [
        "# Refund governance evaluation",
        "",
        f"Provider: {report['manifest']['provider']}",
        "",
        "Evaluation families only (development reported separately in results.json).",
        "",
        "| Measurement | Result |",
        "|---|---|",
    ]
    for key, value in m.items():
        if not isinstance(value, list):
            lines.append(f"| {key} | {value} |")
    lines += ["", "## Limitations", ""] + [f"- {x}" for x in report["manifest"]["limitations"]]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    bars = "".join(
        f'<div class="bar"><span>{html.escape(key)}</span><meter min="0" max="1" value="{m[key] or 0}"></meter><strong>{(m[key] or 0):.1%}</strong></div>'
        for key in ["classification_accuracy", "policy_agreement"]
    )
    bins = m["calibration_bins"]
    points = " ".join(
        f"{30 + 240 * b['predicted']},{270 - 240 * b['observed']}" for b in bins if b["count"]
    )
    table = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in m.items()
        if not isinstance(v, list)
    )
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Refund evaluation</title>
<style>body{{font:16px/1.6 system-ui;background:#edf2f7;color:#172d43;max-width:1000px;margin:40px auto;padding:24px}}article{{background:white;padding:32px;border-radius:12px}}.bar{{display:flex;gap:20px;margin:18px 0}}.bar span{{width:210px}}meter{{flex:1}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:8px;border-bottom:1px solid #ccd7e2}}svg{{max-width:100%;background:#f5f8fb}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style>
<article><p>DECISION FIREWALL / SIMULATED TRANSACTIONS</p><h1>{html.escape(report["manifest"]["provider"].title())} evaluation</h1><p>{m["n"]} held-out-family scenarios. Synthetic evidence, actual runtime measurements.</p>{bars}
<h2>Refund-request probability calibration</h2><svg viewBox="0 0 320 300" width="320" role="img" aria-label="Observed versus predicted refund-request probability"><path d="M30 30V270H270M30 270L270 30" fill="none" stroke="#94a3b8"/><polyline points="{points}" fill="none" stroke="#175ec4" stroke-width="3"/></svg><p>Ten fixed bins; empty bins omitted. Counts are available in results.json.</p><table>{table}</table>
<h2>Reproducibility and limitations</h2><pre>{html.escape(json.dumps(report["manifest"], indent=2))}</pre></article></html>'''
    (output / "report.html").write_text(content, encoding="utf-8")
