"""Offline experiments have no governance store, authorization issuer or executor."""

import csv
import hashlib
import html
import importlib.metadata
import json
import platform
import random
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from .core.audit import digest
from .core.contracts import Assessment, Context, Record
from .core.observation import component, observed, set_correlation
from .core.policy import evaluate_context
from .history import DatasetSnapshot, ExpectedLabels, SnapshotCase


class EvaluationCase(SnapshotCase):
    """Pinned historical input plus separately reviewed expected labels."""


class Threshold(Record):
    metric: str
    maximum: float | None = None
    minimum: float | None = None

    @model_validator(mode="after")
    def bounds(self):
        if self.maximum is None and self.minimum is None:
            raise ValueError("A threshold requires a minimum or maximum")
        if self.maximum is not None and self.minimum is not None and self.minimum > self.maximum:
            raise ValueError("Threshold minimum exceeds maximum")
        return self


class ExperimentSpec(Record):
    name: str
    mode: Literal["policy", "model"] = "policy"
    split: Literal["development", "validation", "evaluation"] = "development"
    seed: int = 42
    thresholds: list[Threshold] = Field(default_factory=list)


class Score(Record):
    name: str
    value: float | bool | None
    hard_invariant: bool = False
    detail: str = ""

    @model_validator(mode="after")
    def invariant_is_boolean(self):
        if self.hard_invariant and not isinstance(self.value, bool):
            raise ValueError("Hard invariants require explicit boolean pass/fail results")
        return self


class Evaluator(Protocol):
    name: str
    version: str

    def __call__(self, case: EvaluationCase, result: dict) -> list[Score]: ...


@dataclass(frozen=True)
class EvaluationPolicy:
    """Capability-limited policy view: no resolver or executor reference."""

    manifest: dict
    action_schema: Any
    evaluate: Any
    supported_constraints: frozenset[str]

    @classmethod
    def from_domain(cls, domain):
        return cls(
            json.loads(json.dumps(domain.manifest())),
            domain.action_schema,
            domain.evaluate,
            frozenset(domain.executor.supported_constraints),
        )


@dataclass(frozen=True)
class ExperimentVariant:
    name: str
    policy: EvaluationPolicy
    model: Any = None
    model_manifest: dict | None = None


class ExperimentResult(Record):
    manifest: dict
    summaries: dict
    observations: list[dict]
    passed: bool
    failures: list[str]


def _mean(values):
    return statistics.mean(values) if values else None


def summarize(rows):
    labeled = [r for r in rows if r["expected"] is not None]
    scored = [r for r in labeled if r["status"] == "ok"]
    allowed = {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
    kinds: dict[str, dict] = {}
    for row in rows:
        for name, score in row["signals"].items():
            aggregate = kinds.setdefault(name, {"kind": score["kind"], "values": []})
            if aggregate["kind"] != score["kind"]:
                raise ValueError("A signal changed semantics within an experiment variant")
            aggregate["values"].append(score)
    model_metrics = {}
    for name, aggregate in kinds.items():
        values = aggregate["values"]
        kind = aggregate["kind"]
        metric: dict[str, Any] = {
            "kind": kind,
            "n": len(values),
            "missing_labels": sum(name not in r.get("expected_signal_names", []) for r in rows),
            "unscored_labels": sum(name in r.get("expected_signal_names", []) for r in rows)
            - len(values),
        }
        if kind in {"choice", "text"}:
            metric["accuracy"] = _mean([v["actual"] == v["expected"] for v in values])
        elif kind == "ordinal":
            metric["mean_absolute_error"] = _mean(
                [abs(v["actual"] - v["expected"]) for v in values]
            )
        elif kind == "probability":
            metric["brier"] = _mean([(v["actual"] - v["expected"]) ** 2 for v in values])
            bins = []
            for index in range(10):
                members = [v for v in values if min(9, int(v["actual"] * 10)) == index]
                bins.append(
                    {
                        "lower": index / 10,
                        "n": len(members),
                        "predicted": _mean([v["actual"] for v in members]),
                        "observed": _mean([v["expected"] for v in members]),
                    }
                )
            metric["calibration_bins"] = bins
            metric["ece"] = sum(
                b["n"] * abs(b["predicted"] - b["observed"]) for b in bins if b["n"]
            ) / len(values)
        model_metrics[name] = metric
    for name in {
        name for r in rows for name in r.get("expected_signal_names", [])
    } - model_metrics.keys():
        model_metrics[name] = {
            "n": 0,
            "kind": None,
            "missing_labels": sum(name not in r.get("expected_signal_names", []) for r in rows),
            "unscored_labels": sum(name in r.get("expected_signal_names", []) for r in rows),
        }
    historical = [r for r in rows if r["historical"] is not None and r["status"] == "ok"]
    latency = sorted(r["latency_ms"] for r in rows)
    ok = [r for r in rows if r["status"] == "ok"]
    return {
        "n": len(rows),
        "completed": len(ok),
        "labeled": len(labeled),
        "scored_dispositions": len(scored),
        "missing_disposition_labels": len(rows) - len(labeled),
        "disposition_agreement": _mean([r["actual"] == r["expected"] for r in scored]),
        "false_allows": sum(
            r["actual"] in allowed and r["expected"] not in allowed for r in scored
        ),
        "false_blocks": sum(
            r["actual"] not in allowed and r["expected"] in allowed for r in scored
        ),
        "review_rate": _mean([r["actual"] == "REQUIRE_REVIEW" for r in ok]),
        "historical_agreement": _mean([r["actual"] == r["historical"] for r in historical]),
        "historical_n": len(historical),
        "incomplete": sum(r["status"] == "incomplete" for r in rows),
        "errors": sum(r["status"] == "error" for r in rows),
        "invalid_outputs": sum(r["invalid_output"] for r in rows),
        "latency_p50_ms": latency[int((len(latency) - 1) * 0.5)] if latency else None,
        "latency_p95_ms": latency[int((len(latency) - 1) * 0.95)] if latency else None,
        "signals": model_metrics,
        "runtime_samples": [{"case_id": r["case_id"], **r.get("runtime", {})} for r in rows],
        "hard_invariant_failures": sum(
            s["hard_invariant"] and s["value"] is False for r in rows for s in r["scores"]
        ),
    }


class ExperimentRunner:
    def __init__(
        self,
        variants: list[ExperimentVariant],
        *,
        evaluators: list[Evaluator] | None = None,
        observer=None,
    ):
        if not variants or len({v.name for v in variants}) != len(variants):
            raise ValueError("Unique named variants required")
        self.variants, self.evaluators, self.observer = variants, evaluators or [], observer

    @observed("experiment.run")
    def run(
        self, dataset: DatasetSnapshot, spec: ExperimentSpec, output: str | Path
    ) -> ExperimentResult:
        dataset = DatasetSnapshot.model_validate(dataset.model_dump(mode="json"))
        cases = [
            EvaluationCase.model_validate(c.model_dump())
            for c in dataset.cases
            if c.split == spec.split
        ]
        if not cases:
            raise ValueError("Selected dataset split is empty")
        if spec.mode == "model" and any(
            v.model is None or not v.model_manifest for v in self.variants
        ):
            raise ValueError(
                "Model experiments require a model and explicit version/config manifest per variant"
            )
        source = Path(__file__).parent
        manifest = {
            "spec": spec.model_dump(),
            "dataset_hash": dataset.hash,
            "development_informed": dataset.development_informed,
            "coverage": dataset.coverage(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "package_version": importlib.metadata.version("decision-firewall"),
            "code_hash": hashlib.sha256(
                b"".join(
                    p.relative_to(source).as_posix().encode() + p.read_bytes()
                    for p in sorted(source.rglob("*.py"))
                )
            ).hexdigest(),
            "variants": [
                {
                    "name": v.name,
                    "policy": v.policy.manifest,
                    "policy_hash": digest(v.policy.manifest),
                    "model": v.model_manifest,
                    "model_hash": digest(v.model_manifest) if v.model_manifest else None,
                    "question_template_hash": digest({"questions": v.model_manifest["questions"]})
                    if v.model_manifest and "questions" in v.model_manifest
                    else None,
                    "retrieval": v.model.manifest() if hasattr(v.model, "manifest") else None,
                    "retrieval_hash": digest(v.model.manifest())
                    if hasattr(v.model, "manifest")
                    else None,
                }
                for v in self.variants
            ],
            "evaluators": [{"name": e.name, "version": e.version} for e in self.evaluators],
            "evaluator_hash": digest(
                {"evaluators": [{"name": e.name, "version": e.version} for e in self.evaluators]}
            ),
            "workers": 1,
            "execution": "disabled",
            "resource_measurements": "wall latency; RSS if psutil installed; CUDA allocation if torch is already loaded; null means unavailable",
        }
        manifest["experiment_id"] = digest(manifest)
        set_correlation(manifest["experiment_id"])
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        # Save thresholds/configuration before running any model or evaluator.
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        dataset.save(output / "dataset.json")
        rows = []
        for variant in self.variants:
            random.seed(spec.seed)
            if hasattr(variant.model, "set_seed"):
                variant.model.set_seed(spec.seed)
            try:
                for case in cases:
                    rows.append(
                        self._run_case(case, spec, variant, dataset, manifest["experiment_id"])
                    )
            finally:
                if hasattr(variant.model, "release"):
                    variant.model.release()
        summaries = {
            v.name: summarize([r for r in rows if r["variant"] == v.name]) for v in self.variants
        }
        failures = []
        for name, summary in summaries.items():
            if summary["errors"] or summary["incomplete"] or summary["hard_invariant_failures"]:
                failures.append(f"{name}: incomplete/error/invariant failure")
            for threshold in spec.thresholds:
                value = summary.get(threshold.metric)
                if (
                    not isinstance(value, (float, int))
                    or (threshold.maximum is not None and value > threshold.maximum)
                    or (threshold.minimum is not None and value < threshold.minimum)
                ):
                    failures.append(f"{name}: threshold {threshold.metric} failed or unavailable")
        report = ExperimentResult(
            manifest=manifest,
            summaries=summaries,
            observations=rows,
            passed=not failures,
            failures=failures,
        )
        write_report(output, report)
        set_correlation(manifest["experiment_id"])
        return report

    def _run_case(self, case, spec, variant, dataset, experiment_id):
        case = EvaluationCase.model_validate(case.model_dump(mode="json"))
        set_correlation(case.id)
        record = case.record
        row = {
            "case_id": case.id,
            "variant": variant.name,
            "status": "ok",
            "error": None,
            "expected": case.labels.disposition.value
            if case.labels and case.labels.disposition
            else None,
            "historical": record.historical_decision.disposition.value
            if record.historical_decision and record.historical_decision.disposition
            else None,
            "actual": None,
            "signals": {},
            "scores": [],
            "rules": [],
            "assessment": None,
            "invalid_output": False,
            "expected_signal_names": sorted(case.labels.signals) if case.labels else [],
            "runtime": {
                "inference_ms": None,
                "gate_ms": None,
                "rss_bytes": None,
                "gpu_allocated_bytes": None,
            },
        }
        start = time.perf_counter()
        missing = []
        for field in ("decision_at", "evidence", "evidence_available_at", "usage"):
            if getattr(record, field) is None:
                missing.append(field)
        if (
            record.evidence_available_at is not None
            and record.decision_at is not None
            and record.evidence_available_at > record.decision_at
        ):
            missing.append("evidence_not_available_at_decision")
        if record.review is not None and (
            record.review_available_at is None
            or record.decision_at is None
            or record.review_available_at > record.decision_at
        ):
            missing.append("review_not_available_at_decision")
        if spec.mode == "policy" and record.assessment is None:
            missing.append("assessment")
        if missing:
            row.update(status="incomplete", error=", ".join(missing))
        else:
            try:
                action = variant.policy.action_schema.model_validate(record.proposal.action)
                proposal = record.proposal.model_copy(
                    update={"action": action.model_dump(mode="json")}
                )
                if proposal.domain != variant.policy.manifest["name"]:
                    raise ValueError("Case domain does not match variant")
                assessment = record.assessment
                if spec.mode == "model":
                    inference_start = time.perf_counter()
                    try:
                        if hasattr(variant.model, "assess_case"):
                            assessment = variant.model.assess_case(
                                EvaluationCase.model_validate(case.model_dump(mode="json")),
                                DatasetSnapshot.model_validate(dataset.model_dump(mode="json")),
                            )
                        else:
                            assessment = variant.model.assess(proposal.message)
                        assessment = Assessment.model_validate(assessment.model_dump(mode="json"))
                        component(
                            "assessment.completed",
                            assessment_id=digest(assessment.model_dump()),
                            experiment_id=experiment_id,
                        )
                        row["runtime"]["inference_ms"] = (
                            time.perf_counter() - inference_start
                        ) * 1000
                    except Exception:
                        row["invalid_output"] = True
                        raise
                context = Context(
                    proposal=proposal,
                    assessment=assessment,
                    evidence=record.evidence,
                    review=record.review,
                    usage=record.usage,
                    now=record.decision_at,
                )
                rules: list = []
                gate_start = time.perf_counter()
                decision = evaluate_context(variant.policy, context, rules)
                row["runtime"]["gate_ms"] = (time.perf_counter() - gate_start) * 1000
                row.update(
                    actual=decision.disposition.value if decision.disposition else None,
                    decision=decision.model_dump(mode="json"),
                    rules=[r.model_dump() for r in rules],
                    assessment=assessment.model_dump(mode="json"),
                )
                if decision.errors:
                    row.update(status="error", error="; ".join(decision.errors))
                self._score_signals(row, assessment, case.labels)
            except Exception as exc:  # noqa: BLE001 -- expose per-case failures in reports
                row.update(status="error", error=type(exc).__name__ + ": " + str(exc))
        row["latency_ms"] = (time.perf_counter() - start) * 1000
        try:
            import psutil

            row["runtime"]["rss_bytes"] = psutil.Process().memory_info().rss
        except ImportError:
            pass
        # Never import a model dependency just to observe it.
        import sys

        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_initialized():
            row["runtime"]["gpu_allocated_bytes"] = torch.cuda.memory_allocated()
        for evaluator in self.evaluators:
            try:
                row["scores"].extend(
                    Score.model_validate(s.model_dump()).model_dump()
                    for s in evaluator(
                        EvaluationCase.model_validate(case.model_dump(mode="json")),
                        json.loads(json.dumps(row)),
                    )
                )
            except Exception as exc:  # noqa: BLE001 -- broken evaluation is not a passing result
                row.update(
                    status="error", error=f"evaluator {evaluator.name}: {type(exc).__name__}"
                )
        if self.observer:
            from .core.observation import emit

            emit(
                self.observer,
                "experiment.case",
                case.id,
                row["status"],
                row["latency_ms"],
                attributes={
                    "variant": variant.name,
                    "dataset_id": dataset.hash,
                    "experiment_id": experiment_id,
                },
            )
        return row

    @staticmethod
    def _score_signals(row, assessment, labels: ExpectedLabels | None):
        if not labels:
            return
        for name, expected in labels.signals.items():
            signal = assessment.signals.get(name)
            if signal is None:
                continue
            if signal.kind == "probability" and (
                not isinstance(expected, (int, float)) or expected not in (0, 1)
            ):
                raise ValueError("Binary Brier labels must be 0 or 1")
            if signal.kind == "ordinal" and not isinstance(expected, (int, float)):
                raise ValueError("Ordinal labels must be numeric")
            row["signals"][name] = {
                "kind": signal.kind,
                "actual": signal.value,
                "expected": expected,
            }


def write_report(output: Path, report: ExperimentResult):
    (output / "results.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    with (output / "observations.csv").open("w", newline="", encoding="utf-8") as file:
        fields = [
            "case_id",
            "variant",
            "status",
            "expected",
            "actual",
            "historical",
            "latency_ms",
            "error",
        ]
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report.observations)
    lines = [
        "# Decision experiment",
        "",
        "Execution disabled. Historical agreement is not correctness.",
        "",
        "| Variant | Cases | Agreement | False allows | False blocks | Errors |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, m in report.summaries.items():
        lines.append(
            f"| {name} | {m['n']} | {m['disposition_agreement']} | {m['false_allows']} | {m['false_blocks']} | {m['errors']} |"
        )
    lines += ["", "Passed: " + str(report.passed), *report.failures]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    bars = "".join(
        f'<p>{html.escape(name)} <meter min="0" max="1" value="{m["disposition_agreement"] or 0}"></meter> {m["disposition_agreement"]} (n={m["scored_dispositions"]})</p>'
        for name, m in report.summaries.items()
    )
    rows = "".join(
        f"<tr><td>{html.escape(r['case_id'])}</td><td>{html.escape(r['variant'])}</td><td>{html.escape(str(r['expected']))}</td><td>{html.escape(str(r['actual']))}</td><td><details><summary>{html.escape(r['status'])}</summary><pre>{html.escape(json.dumps(r, indent=2))}</pre></details></td></tr>"
        for r in report.observations
    )
    (output / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Decision experiment</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:32px auto;padding:20px;color:#172d43}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ccc}pre{white-space:pre-wrap;overflow-wrap:anywhere}meter{width:220px}</style><h1>Decision experiment</h1><p>Offline; execution disabled. Historical agreement is diagnostic only.</p>'
        + bars
        + "<h2>Case comparison and rule explanations</h2><table><tr><th>Case</th><th>Variant</th><th>Expected</th><th>Actual</th><th>Details</th></tr>"
        + rows
        + "</table><h2>Manifest and label coverage</h2><pre>"
        + html.escape(json.dumps(report.manifest, indent=2))
        + "</pre></html>",
        encoding="utf-8",
    )


def compare_reports(paths: Sequence[str | Path]) -> dict:
    reports = [
        ExperimentResult.model_validate_json((Path(p) / "results.json").read_text()) for p in paths
    ]
    if (
        not reports
        or len({(r.manifest["dataset_hash"], r.manifest["spec"]["split"]) for r in reports}) != 1
    ):
        raise ValueError("Comparison requires identical dataset snapshots and splits")
    return {
        "dataset_hash": reports[0].manifest["dataset_hash"],
        "runs": [
            {"id": r.manifest["experiment_id"], "summaries": r.summaries, "passed": r.passed}
            for r in reports
        ],
    }
