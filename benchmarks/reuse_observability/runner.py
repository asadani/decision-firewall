"""Frozen reuse and observability experiment; no model downloads or real effects."""

import argparse
import copy
import hashlib
import json
import platform
import random
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from decision_firewall import Assessment
from decision_firewall.core import Signal, verify_receipt

from .application import Application
from .framework import Framework
from .service import Service, transaction

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
ARMS = ("modular_application", "firewall")
NOW = 1700000000.0


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make(home, case, arm, clock, observer=None):
    service = Service(home, case["domain"])
    if arm == "firewall":
        engine = Framework(home, case["domain"], case["config"], service, clock, observer)
    else:
        if observer is not None:
            from .telemetry import application_observer

            observer = application_observer(observer)
        engine = Application(home, case["domain"], case["config"], service, clock, observer)
    return engine, service


def assessment(label):
    return Assessment(
        provider="fixture",
        model="controlled",
        revision="1",
        signals={"request_type": Signal(kind="choice", value=label)},
        metadata={"raw": "MODEL-CANARY", "credential": "CREDENTIAL-CANARY"},
    ).model_dump(mode="json")


def write_facts(home, case):
    facts = copy.deepcopy(case["facts"])
    if facts:
        facts["private_note"] = "EVIDENCE-CANARY"
    (home / f"{case['domain']}-facts.json").write_text(json.dumps(facts), encoding="utf-8")


def fresh_recovery(home, case, arm, handle, endpoint=None):
    source, target = home / "recovery-in.json", home / "recovery-out.json"
    source.write_text(
        json.dumps(
            {
                "home": str(home.resolve()),
                "case": case,
                "arm": arm,
                "handle": handle,
                "endpoint": endpoint,
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.reuse_observability.runner",
            "--recover",
            str(source.resolve()),
            str(target.resolve()),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=45,
    )
    return json.loads(target.read_text(encoding="utf-8"))


def recover(source, target):
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    observer = None
    if data["endpoint"]:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        from decision_firewall.adapters.opentelemetry import OpenTelemetryObserver

        observer = OpenTelemetryObserver(
            exporter=OTLPSpanExporter(endpoint=data["endpoint"], timeout=2)
        )
    engine, _ = make(Path(data["home"]), data["case"], data["arm"], lambda: NOW, observer)
    result = engine.reconcile(data["handle"])
    flushed = True
    if observer:
        flushed = observer.flush()
        observer.close()
    Path(target).write_text(json.dumps({"result": result, "flushed": flushed}), encoding="utf-8")


def episode(home, case, arm, observer=None, profile=False, endpoint=None):
    start = time.perf_counter()
    home.mkdir(parents=True, exist_ok=False)
    write_facts(home, case)
    now = [NOW]
    engine, service = make(home, case, arm, lambda: now[0], observer)
    setup_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    handles = [
        engine.prepare(case["action"], case["label"], assessment(case["label"]))
        for _ in range(case["count"])
    ]
    initial = [h["disposition"] for h in handles]
    errors = []
    if case["name"] in {"review_approved", "review_unauthorized"}:
        try:
            engine.approve(handles[0], case["name"] == "review_approved")
        except ValueError as exc:
            errors.append(type(exc).__name__)
    if case["name"] == "expired":
        now[0] += 400
    if case["name"] == "revoked":
        engine.revoke(handles[0])
    if case["name"] == "changed_evidence":
        facts = service.facts()
        facts["version"] += 1
        service.facts_path.write_text(json.dumps(facts), encoding="utf-8")
    if case["name"] == "audit_failure":
        if arm == "modular_application":
            engine.audit_unavailable = True
        else:

            def fail_audit(*args):
                raise OSError("Required audit outage")

            engine.fw.store.event = fail_audit
    if case["name"] == "response_loss_restart" or profile:
        service.mode = "response_loss"
    barrier = threading.Barrier(case["count"]) if case["count"] > 1 else None

    def dispatch(handle):
        if barrier:
            barrier.wait(timeout=10)
        try:
            return engine.dispatch(handle)
        except (ValueError, OSError) as exc:
            errors.append(type(exc).__name__)
            return "BLOCKED"

    if barrier:
        with ThreadPoolExecutor(max_workers=case["count"]) as pool:
            statuses = list(pool.map(dispatch, handles))
    else:
        statuses = [dispatch(handles[0])]
    if case["name"] == "repeat":
        dispatch(handles[0])
    if "UNKNOWN" in statuses:
        if endpoint is not None and observer is not None:
            # Ensure pre-restart spans reach the collector before the recovery process starts.
            observer.flush()
        recovered = fresh_recovery(home, case, arm, handles[0], endpoint)
        statuses[0] = recovered["result"]
    elapsed = (time.perf_counter() - start) * 1000
    audit_ok, tamper_rejected, audit_contains_canaries = None, None, False
    if arm == "firewall":
        receipt = engine.fw.receipt()
        audit_ok = verify_receipt(receipt, engine.fw.store.public)
        serialized = json.dumps(receipt)
        audit_contains_canaries = "MODEL-CANARY" in serialized and "EVIDENCE-CANARY" in serialized
        # Change a known body string while retaining its signatures.
        tampered = json.loads(serialized.replace("MODEL-CANARY", "EDITED-CANARY"))
        try:
            tamper_rejected = not verify_receipt(tampered, engine.fw.store.public)
        except ValueError:
            tamper_rejected = True
        with engine.fw.store.transaction() as db:
            audit_records = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    else:
        with transaction(engine.path) as db:
            bodies = [r[0] for r in db.execute("SELECT body FROM audit")]
        audit_records = len(bodies)
        audit_contains_canaries = "MODEL-CANARY" in str(bodies) and "EVIDENCE-CANARY" in str(bodies)
    return {
        "case": case["id"],
        "arm": arm,
        "initial": initial,
        "expected_initial": case["initial"],
        "statuses": statuses,
        "effects": service.count(),
        "expected_effects": case["expected_effects"],
        "setup_ms": setup_ms,
        "operation_ms": elapsed,
        "errors": errors,
        "audit_records": audit_records,
        "audit_verified": audit_ok,
        "audit_tamper_rejected": tamper_rejected,
        "audit_contains_canaries": audit_contains_canaries,
        "rid": handles[0]["id"],
    }


def save(output, name, value):
    (output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")


def conformance(output, cases):
    rows = [
        episode(output / "runtime" / case["id"] / arm, case, arm) for case in cases for arm in ARMS
    ]
    for row in rows:
        row["passed"] = (
            row["initial"] == [row["expected_initial"]] * len(row["initial"])
            and row["effects"] == row["expected_effects"]
            and "UNKNOWN" not in row["statuses"]
        )
    save(output, "conformance.json", rows)
    print("Conformance:", sum(r["passed"] for r in rows), "/", len(rows), flush=True)
    return rows


def latency(output, case, protocol):
    from decision_firewall.adapters.opentelemetry import OpenTelemetryObserver

    from .telemetry import Sink

    rng = random.Random(protocol["latency"]["seed"])
    rows = []
    for arm in ARMS:
        episode(output / "warmup" / arm, case, arm)
    for repetition in range(protocol["latency"]["paired_repetitions"]):
        order = [(arm, enabled) for arm in ARMS for enabled in (False, True)]
        rng.shuffle(order)
        for arm, enabled in order:
            sink = Sink()
            observer = OpenTelemetryObserver(exporter=sink) if enabled else None
            row = episode(
                output / "latency-runtime" / str(repetition) / f"{arm}-{enabled}",
                case,
                arm,
                observer,
            )
            start = time.perf_counter()
            flushed = observer.flush() if observer else True
            drain_ms = (time.perf_counter() - start) * 1000
            diagnostics = dict(observer.diagnostics) if observer else None
            if observer:
                observer.close()
            row.update(
                repetition=repetition,
                telemetry=enabled,
                drain_ms=drain_ms,
                flushed=flushed,
                spans=len(sink.spans),
                export_diagnostics=diagnostics,
            )
            rows.append(row)
        if (repetition + 1) % 10 == 0:
            print("Latency pairs:", repetition + 1, flush=True)
    save(output, "latency.json", rows)
    summary = {}
    for arm in ARMS:
        for enabled in (False, True):
            samples = [r for r in rows if r["arm"] == arm and r["telemetry"] == enabled]
            values = sorted(r["operation_ms"] for r in samples)
            summary[f"{arm}-{'on' if enabled else 'off'}"] = {
                "n": len(values),
                "p50_ms": statistics.median(values),
                "p95_ms": values[max(0, __import__("math").ceil(0.95 * len(values)) - 1)],
                "drain_p50_ms": statistics.median(r["drain_ms"] for r in samples),
                "setup_p50_ms": statistics.median(r["setup_ms"] for r in samples),
                "spans": sum(r["spans"] for r in samples),
                "effects": sum(r["effects"] for r in samples),
            }
        deltas = [
            next(
                r["operation_ms"]
                for r in rows
                if r["arm"] == arm and r["telemetry"] and r["repetition"] == i
            )
            - next(
                r["operation_ms"]
                for r in rows
                if r["arm"] == arm and not r["telemetry"] and r["repetition"] == i
            )
            for i in range(protocol["latency"]["paired_repetitions"])
        ]
        summary[arm + "-paired-telemetry"] = {
            "n": len(deltas),
            "median_ms": statistics.median(deltas),
            "min_ms": min(deltas),
            "max_ms": max(deltas),
        }
    save(output, "latency-summary.json", summary)
    return rows, summary


def profiles(output, case):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    from decision_firewall.adapters.opentelemetry import OpenTelemetryObserver
    from decision_firewall.core.observation import Observation

    from .telemetry import Collector, OutsideTransactionObserver, Sink, inspect

    results = {}
    for arm in ARMS:
        collector = Collector()
        try:
            observer = OpenTelemetryObserver(
                exporter=OTLPSpanExporter(endpoint=collector.endpoint, timeout=2)
            )
            home = output / "profile-runtime" / arm
            probe = OutsideTransactionObserver(
                observer, home / ("governance.db" if arm == "firewall" else "application.db")
            )
            # episode's pre-recovery drain is forwarded by this wrapper.
            probe.flush = observer.flush
            row = episode(home, case, arm, probe, profile=True, endpoint=collector.endpoint)
            flushed = observer.flush()
            observer.close()
            inspection = inspect(collector.spans, row["rid"])
            inspection.update(
                flushed=flushed,
                observer_calls=probe.calls,
                write_lock_failures=probe.failures,
                episode=row,
            )
            save(output, arm + "-spans.json", collector.spans)
            results[arm] = inspection
        finally:
            collector.close()
        failed_sink = Sink(failure=True)
        observer = OpenTelemetryObserver(exporter=failed_sink)
        failure = episode(output / "exporter-failure" / arm, case, arm, observer)
        observer.flush()
        diagnostics = dict(observer.diagnostics)
        observer.close()
        results[arm]["exporter_failure"] = {
            "effects": failure["effects"],
            "statuses": failure["statuses"],
            "diagnostics": diagnostics,
        }
    # Saturation is a property of the shared optional adapter, not a special governance advantage.
    unblock = threading.Event()
    blocked = Sink(block=unblock)
    observer = OpenTelemetryObserver(exporter=blocked, capacity=8)
    observer.emit(Observation("probe", "safe-id", "ok", 0, {"message": "MESSAGE-CANARY"}))
    if not blocked.entered.wait(2):
        raise RuntimeError("Blocked exporter never started")
    start = time.perf_counter()
    for _ in range(1000):
        observer.emit(Observation("probe", "safe-id", "ok", 0))
    enqueue_ms = (time.perf_counter() - start) * 1000
    queued = observer.queue.qsize()
    dropped = observer.diagnostics["dropped"]
    unblock.set()
    flushed = observer.flush()
    observer.close()
    results["shared_saturation"] = {
        "capacity": 8,
        "queued_while_blocked": queued,
        "dropped": dropped,
        "enqueue_1000_ms": enqueue_ms,
        "flushed": flushed,
    }
    save(output, "telemetry-profiles.json", results)
    return results


def run(output, mode):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    save(
        output,
        "manifest.json",
        {
            "started": datetime.now(UTC).isoformat(),
            "mode": mode,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "protocol_hash": file_hash(HERE / "protocol.json"),
            "cases_hash": file_hash(HERE / "cases.json"),
            "source_hashes": {
                str(p.relative_to(ROOT)): file_hash(p)
                for folder in (HERE, ROOT / "src", ROOT / "benchmarks/framework_value")
                for p in sorted(folder.rglob("*.py"))
            },
        },
    )
    (output / "protocol.json").write_bytes((HERE / "protocol.json").read_bytes())
    (output / "cases.json").write_bytes((HERE / "cases.json").read_bytes())
    passed = True
    if mode in {"all", "conformance"}:
        rows = conformance(output, cases)
        passed = all(r["passed"] for r in rows)
    if mode in {"all", "telemetry"}:
        simple = next(c for c in cases if c["id"] == "data_export-base-allow")
        latency_rows, summary = latency(output, simple, protocol)
        complex_case = next(c for c in cases if c["id"] == "data_export-base-review_approved")
        observed = profiles(output, complex_case)
        passed &= all(r["effects"] == 1 for r in latency_rows)
        passed &= all(
            not observed[a]["canaries_leaked"]
            and observed[a]["write_lock_failures"] == 0
            and observed[a]["exporter_failure"]["effects"] == 1
            for a in ARMS
        )
        print(json.dumps(summary, indent=2))
    save(
        output,
        "acceptance.json",
        {"passed": passed, "missing_telemetry_fields_are_reported_not_hidden": True},
    )
    return 0 if passed else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("all", "conformance", "telemetry"), default="all")
    parser.add_argument("--recover", nargs=2)
    args = parser.parse_args()
    if args.recover:
        recover(*args.recover)
    elif args.output:
        raise SystemExit(run(args.output, args.mode))
    else:
        parser.error("--output required")
