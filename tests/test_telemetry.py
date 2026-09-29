import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from decision_firewall.adapters.opentelemetry import OpenTelemetryObserver
from decision_firewall.core.observation import Observation, trace_id


def test_in_process_otlp_collector_redaction_and_restart_correlation():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = ExportTraceServiceRequest()
            request.ParseFromString(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(request)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for operation in ("dispatch", "reconcile"):
            observer = OpenTelemetryObserver(
                exporter=OTLPSpanExporter(
                    endpoint=f"http://127.0.0.1:{server.server_port}/v1/traces", timeout=2
                )
            )
            observer.emit(
                Observation(
                    operation,
                    "decision-123",
                    "ok",
                    1,
                    {
                        "attempt_id": "attempt-1",
                        "message": "SECRET",
                        "token": "CREDENTIAL",
                        "evidence": "PRIVATE",
                    },
                )
            )
            assert observer.flush()
            observer.close()
        spans = [
            span
            for request in received
            for resource in request.resource_spans
            for scope in resource.scope_spans
            for span in scope.spans
        ]
        assert len(spans) == 2
        assert {int.from_bytes(s.trace_id, "big") for s in spans} == {trace_id("decision-123")}
        assert spans[0].span_id != spans[1].span_id
        assert all("firewall.attempt_id" in {a.key for a in s.attributes} for s in spans)
        assert not any(secret in str(received) for secret in ("SECRET", "CREDENTIAL", "PRIVATE"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_bounded_queue_export_failure_and_explicit_content_hook():
    entered, unblock = threading.Event(), threading.Event()
    exported = []

    class BlockingExporter(SpanExporter):
        def export(self, spans):
            entered.set()
            unblock.wait(3)
            exported.extend(spans)
            return SpanExportResult.FAILURE

    with pytest.raises(ValueError, match="redaction"):
        OpenTelemetryObserver(content_allowlist=["message"])
    observer = OpenTelemetryObserver(
        exporter=BlockingExporter(),
        capacity=2,
        content_allowlist=["message"],
        redact=lambda key, value: "[redacted]",
    )
    observer.emit(Observation("assessment", "case-1", "ok", 1, {"message": "SECRET"}))
    assert entered.wait(2)
    for _ in range(100):
        observer.emit(Observation("policy", "case-1", "ok", 0))
    assert observer.queue.qsize() <= 2 and observer.diagnostics["dropped"] >= 98
    unblock.set()
    assert observer.flush()
    observer.close()
    assert observer.diagnostics["export_failures"] > 0
    assert exported[0].attributes["firewall.message"] == "[redacted]"
