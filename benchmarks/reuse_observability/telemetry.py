"""Shared observer plumbing and independent, mechanical trace checks."""

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from decision_firewall.core.observation import Observation


def application_observer(observer):
    # Reuse the optional utility, without using its governance runtime.
    def emit(event):
        observer.emit(Observation(**event))

    return emit


class Sink(SpanExporter):
    def __init__(self, failure=False, block=None):
        self.spans, self.failure, self.block = [], failure, block
        self.entered = threading.Event()

    def export(self, spans):
        self.entered.set()
        if self.block:
            self.block.wait(10)
        self.spans.extend(
            {
                "name": s.name,
                "trace_id": f"{s.context.trace_id:032x}",
                "attributes": dict(s.attributes or {}),
            }
            for s in spans
        )
        return SpanExportResult.FAILURE if self.failure else SpanExportResult.SUCCESS


class OutsideTransactionObserver:
    def __init__(self, observer, path):
        self.observer, self.path, self.failures, self.calls = observer, path, 0, 0

    def emit(self, event):
        self.calls += 1
        try:
            with sqlite3.connect(self.path, timeout=0) as db:
                db.execute("BEGIN IMMEDIATE")
                db.rollback()
        except sqlite3.OperationalError:
            self.failures += 1
        self.observer.emit(event)


class Collector:
    def __init__(self):
        self.spans = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = ExportTraceServiceRequest()
                request.ParseFromString(self.rfile.read(int(self.headers["Content-Length"])))
                for resource in request.resource_spans:
                    for scope in resource.scope_spans:
                        for span in scope.spans:
                            attrs = {}
                            for attr in span.attributes:
                                field = attr.value.WhichOneof("value")
                                attrs[attr.key] = getattr(attr.value, field) if field else None
                            owner.spans.append(
                                {
                                    "name": span.name,
                                    "trace_id": span.trace_id.hex(),
                                    "attributes": attrs,
                                }
                            )
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/v1/traces"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def inspect(spans, rid):
    names = {s["name"] for s in spans}
    stages = {
        "assessment": {"application.assessment", "assessment.completed"},
        "evidence": {"application.evidence", "evidence.resolve"},
        "policy": {"application.policy", "governance.evaluate"},
        "review": {"application.review", "governance.review"},
        "authorization": {"application.authorization", "audit.authorization_issued"},
        "dispatch": {"application.dispatch", "governance.execute"},
        "reconciliation": {"application.reconciliation", "governance.reconcile"},
        "outcome": {"application.outcome", "audit.execution_outcome"},
    }
    fields = (
        "assessment_id",
        "evaluation_id",
        "authorization_id",
        "attempt_id",
        "policy_version",
        "reasons",
    )
    result = {
        "span_count": len(spans),
        "stages": {k: bool(v & names) for k, v in stages.items()},
        "fields": {key: any("firewall." + key in s["attributes"] for s in spans) for key in fields},
    }
    result["fields"]["disposition"] = any(
        s["attributes"].get("firewall.status")
        in {"ALLOW", "ALLOW_WITH_CONSTRAINTS", "DENY", "REQUIRE_REVIEW", "REQUIRE_EVIDENCE"}
        or "firewall.disposition" in s["attributes"]
        for s in spans
    )
    decision_spans = [s for s in spans if s["attributes"].get("firewall.correlation_id") == rid]
    phase_trace = {s["trace_id"] for s in decision_spans}
    result["restart_trace_linked"] = len(phase_trace) == 1 and any(
        s["name"] in stages["reconciliation"] for s in decision_spans
    )
    assessed = {
        s["attributes"].get("firewall.assessment_id")
        for s in spans
        if s["name"] in stages["assessment"]
    }
    linked = {s["attributes"].get("firewall.assessment_id") for s in decision_spans}
    result["assessment_linked"] = bool((assessed & linked) - {None})
    result["canaries_leaked"] = [
        value
        for value in ("MESSAGE-CANARY", "EVIDENCE-CANARY", "MODEL-CANARY", "CREDENTIAL-CANARY")
        if value in json.dumps(spans)
    ]
    return result
