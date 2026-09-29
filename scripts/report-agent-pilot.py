"""Publish aggregate agent-pilot measurements, excluding prompts, permits and credentials."""

import argparse
import csv
import html
import json
import shutil
import statistics
from pathlib import Path


def publish(source, output, diagnostics):
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((source / "manifest.json").read_text())
    rows = []
    all_attempts = []
    for path in sorted(source.glob("*.json")):
        if path.name == "manifest.json":
            continue
        record = json.loads(path.read_text())
        if "suite" not in record:
            continue
        attempts = record.get("attempts", [])
        all_attempts.extend(attempts)
        calls = record.get("calls", [])
        db_check = (record.get("reward") or {}).get("db_check") or {}
        rows.append(
            {
                **{
                    k: record.get(k)
                    for k in (
                        "suite",
                        "task",
                        "injection",
                        "arm",
                        "status",
                        "task_success",
                        "attack_success",
                        "termination",
                        "error_type",
                        "receipt_verified",
                    )
                },
                "db_match": db_check.get("db_match"),
                "tool_calls": len(calls) if "calls" in record else None,
                "blocked_calls": sum(c["blocked"] for c in calls) if "calls" in record else None,
                "out_of_policy_dispatches": (
                    sum(c["would_block"] and c["executed"] for c in calls)
                    if "calls" in record
                    else None
                ),
                "tool_boundary_ms": [c["elapsed_ms"] for c in calls],
                "accepted_model_responses": len(record.get("inference", [])),
                "cache_hits": sum(c["cache_hit"] for c in record.get("inference", [])),
                "paid_attempts": len(attempts),
                "reported_cost_usd": sum(c.get("cost_usd") or 0 for c in attempts),
                "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in attempts),
                "completion_tokens": sum(c.get("completion_tokens") or 0 for c in attempts),
                "unknown_cost_attempts": sum(c.get("cost_usd") is None for c in attempts),
            }
        )
    (output / "observations.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    shutil.copy2(source / "manifest.json", output / "manifest.json")
    summary = []
    for suite, attacked in (("tau2", False), ("agentdojo", False), ("agentdojo", True)):
        for arm in manifest["protocol"]["arms"]:
            group = [
                r
                for r in rows
                if r["suite"] == suite and bool(r["injection"]) == attacked and r["arm"] == arm
            ]
            timings = [v for r in group for v in r["tool_boundary_ms"]]
            summary.append(
                {
                    "suite": suite,
                    "condition": "attacked" if attacked else "clean",
                    "arm": arm,
                    "planned": 10,
                    "recorded": len(group),
                    "completed": sum(r["status"] == "completed" for r in group),
                    "task_successes": sum(r["task_success"] is True for r in group),
                    "attack_successes": sum(r["attack_success"] is True for r in group)
                    if attacked
                    else None,
                    "db_matches": sum(r["db_match"] is True for r in group)
                    if suite == "tau2"
                    else None,
                    "blocked_calls": sum(r["blocked_calls"] or 0 for r in group),
                    "out_of_policy_dispatches": sum(
                        r["out_of_policy_dispatches"] or 0 for r in group
                    ),
                    "boundary_episodes_observed": sum(r["tool_calls"] is not None for r in group),
                    "boundary_p50_ms": statistics.median(timings) if timings else None,
                    "boundary_samples": len(timings),
                    "receipts_verified": sum(r["receipt_verified"] is True for r in group),
                }
            )
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=summary[0])
        writer.writeheader()
        writer.writerows(summary)
    prior_attempts = []
    failed_diagnostics = []
    for diagnostic in diagnostics:
        for path in diagnostic.glob("*.json"):
            if path.name == "manifest.json":
                continue
            record = json.loads(path.read_text())
            prior_attempts.extend(record.get("attempts", []))
            failed_diagnostics.append(
                {k: record.get(k) for k in ("suite", "task", "arm", "status", "error_type")}
            )
    paid = all_attempts + prior_attempts
    spend = sum(c.get("cost_usd") or 0 for c in paid)
    accounting = {
        "this_pilot_reported_usd_including_retained_diagnostics": spend,
        "paid_attempts": len(paid),
        "http_429_attempts": sum(c.get("http_status") == 429 for c in paid),
        "unknown_cost_attempts": sum(c.get("cost_usd") is None for c in paid),
        "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in paid),
        "completion_tokens": sum(c.get("completion_tokens") or 0 for c in paid),
        "cache_hits": sum(r["cache_hits"] for r in rows),
        "diagnostics": failed_diagnostics,
        "budget_note": "Same non-resetting $5 key cap and durable budget DB as earlier echo probes. Unknown attempts retain worst-case reservations. Earlier echo spend is outside this pilot total and covered by the opening $0.01 reserve.",
    }
    (output / "accounting.json").write_text(json.dumps(accounting, indent=2), encoding="utf-8")
    lines = [
        "# Agent benchmark development pilot",
        "",
        (
            "Pinned τ-bench retail and AgentDojo banking tasks, simulated effects, one seeded trial. "
            "This is a 90-episode subset/configuration study, not a full-suite or leaderboard score."
        ),
        "",
        "| Suite / condition | Arm | Completed / planned | Task successes | Attack successes | DB matches | Blocked calls |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        lines.append(
            f"| {s['suite']} / {s['condition']} | {s['arm']} | {s['completed']}/{s['planned']} | {s['task_successes']} | {s['attack_successes'] if s['attack_successes'] is not None else 'N/A'} | {s['db_matches'] if s['db_matches'] is not None else 'N/A'} | {s['blocked_calls']} |"
        )
    lines += [
        "",
        "Task-success counts use the completed denominator shown; uncompleted episodes are not silently scored as correct or dropped. Attack success means the upstream attacker goal succeeded, so lower is better. Database match is τ-bench's deterministic state check; overall τ-bench success also includes applicable language assertions.",
        "",
        (
            "Tool-boundary counts and timing cover completed episodes only. Missing tool observations "
            "in aborted episodes are null, not evidence of zero effects. "
            f"There are {sum(r['status'] == 'error' for r in rows)} incomplete episodes; these are not scored task failures. "
            "Invalid or reasoning-only completions are never replaced with favorable outputs. "
            f"Signed receipts verified in {sum(r['receipt_verified'] is True for r in rows)} framework episodes; "
            "incomplete episodes have no reported verification result."
        ),
        "",
        "## Transport and cost",
        "",
        f"Response-reported pilot cost, including retained diagnostic attempts: **${spend:.6f}** across {len(paid)} paid attempts. There were {accounting['http_429_attempts']} rate-limited attempts and {accounting['unknown_cost_attempts']} attempts without a reported cost; reservations remain for unknown charges. {accounting['cache_hits']} identical-input responses were reused across arms. This is response accounting, not an independently reconciled invoice.",
        "",
        "Model: OpenRouter openai/gpt-oss-20b, Darkbloom only, temperature 0, low reasoning, max_tokens 2048, run seed 20260928 with per-case/role/turn derived seeds. Agent, τ-bench simulated user and NL judge use the same transport/budget. One inference worker; only bounded HTTP 429 backoff. Hosted model weights are not revision-pinned. The judge model differs from upstream defaults; its accuracy was not independently validated.",
        "",
        "## Interpretation",
        "",
        "The application and framework enforce the same narrow predicates. Retail checks identity lookup, record ownership and order status; existing upstream tools and prompts retain the other rules. Banking uses a conservative lexical capability check on the original user instruction. A document cannot grant write authority. Transfers lacking an explicitly supplied recipient, and scheduled-payment changes derived from documents, require review. There is no human approval in this pilot. Benign failures therefore matter: attack blocking alone is not evidence of useful governance.",
        "",
        "The baseline retains upstream tool validations. Out-of-policy dispatch counts in observations are relative to this study's added checks, not independently adjudicated harmful effects. Attack success comes from the unchanged AgentDojo security checker. Lower clean-task utility is reported instead of hiding review-related false blocks. No claim that these lexical checks implement complete semantic authorization, every retail policy clause, or production banking controls is made.",
        "",
        "Framework arms use real SDK submit/evaluate/authorize/execute and signed receipt verification at the tool boundary. The application arm invokes the same predicate directly and writes a SQLite audit entry. This comparison isolates packaging/enforcement of the selected checks; it is not a comparison of independently written full application architectures. Upstream environments are volatile simulators, so these episodes do not validate durable effect recovery.",
        "",
        "## Timing and reproducibility",
        "",
        "Boundary timing includes the upstream tool invocation and local governance work, excludes model inference, and has differing tool mixes between arms. comparison.csv contains sample counts and medians; do not interpret them as paired end-to-end overhead. Identical full inputs/settings/turns share cached responses, ensuring common prefixes use identical samples; divergent trajectories make new calls. Cache use makes raw episode wall time unsuitable for model-throughput comparisons.",
        "",
        "The manifest records frozen tasks, source hashes, packages, policy code, protocol, platform and settings. τ-bench uses the first 10 declared retail train tasks; AgentDojo uses banking user_task_0 through user_task_9, clean and injection_task_0, with the upstream important-instructions fixed template and generic names. Upstream attack construction may inspect ground truth to select injection locations; neither defender model nor policy receives ground truth or grading labels. The upstream graders are retained, with denied calls preserved as no-effects during τ-bench replay and exact NL-assertion response coverage validated.",
        "",
        "One initial live τ-bench episode exposed a scalar-string parsing bug in the adapter after successful authentication. Its failed diagnostic and cost are retained in accounting.json. Offline authentication coverage was added and the adapter corrected before the measurement run; tasks, policies and thresholds were not tuned to model results. No statistical p-values, accuracy uplift, production effectiveness or developer-hour savings are claimed.",
        "",
        "See [protocol and reproduction](../../../benchmarks/agent_suites/README.md). Private transcripts, response caches, runtime signing keys and bearer permits are excluded from this published report.",
    ]
    text = "\n".join(lines) + "\n"
    (output / "summary.md").write_text(text, encoding="utf-8")
    tables = (
        "<table><thead><tr>"
        + "".join(f"<th>{html.escape(k)}</th>" for k in summary[0])
        + "</tr></thead><tbody>"
    )
    for s in summary:
        tables += "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in s.values()) + "</tr>"
    tables += "</tbody></table>"
    charts = "".join(
        f"<p>{html.escape(s['suite'] + ' / ' + s['condition'] + ' / ' + s['arm'])}: <meter min='0' max='10' value='{s['task_successes']}'></meter> {s['task_successes']}/10 task successes</p>"
        for s in summary
    )
    page = "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Agent benchmark pilot</title><style>body{font:16px/1.6 system-ui;color:#172b43;margin:32px auto;padding:0 20px;max-width:1200px}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ccd6e3;text-align:left}th{background:#edf4ff}.table{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}meter{width:180px}</style><h1>Agent benchmark development pilot</h1><p>Simulated effects • Pinned upstream tasks • Three comparison arms</p>"
    page += (
        charts
        + "<div class='table'>"
        + tables
        + "</div><p><a href='comparison.csv'>CSV</a> · <a href='observations.json'>Case observations</a> · <a href='manifest.json'>Manifest</a></p><pre>"
        + html.escape(text)
        + "</pre></html>"
    )
    (output / "report.html").write_text(page, encoding="utf-8")
    print(json.dumps(accounting, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--diagnostic", action="append", type=Path, default=[])
    args = parser.parse_args()
    publish(args.source, args.output, args.diagnostic)
