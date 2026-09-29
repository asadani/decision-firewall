"""Optional bounded OTLP/HTTP export. No SDK imports enter the core package."""

import queue
import threading
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from ..core.observation import Observation, trace_id

SAFE_ATTRIBUTES = frozenset(
    {
        "decision_id",
        "preparation_id",
        "assessment_id",
        "evaluation_id",
        "attempt_id",
        "authorization_id",
        "dataset_id",
        "experiment_id",
        "variant",
        "policy_version",
        "rule_name",
        "rule_version",
        "selected_count",
        "omitted_count",
        "event_count",
    }
)


class _CountingExporter(SpanExporter):
    def __init__(self, exporter, diagnostics):
        self.exporter, self.diagnostics = exporter, diagnostics

    def export(self, spans):
        try:
            result = self.exporter.export(spans)
            if result != SpanExportResult.SUCCESS:
                self.diagnostics["export_failures"] += 1
            return result
        except Exception:  # noqa: BLE001 -- do not expose exporter exception bodies/credentials
            self.diagnostics["export_failures"] += 1
            return SpanExportResult.FAILURE

    def shutdown(self):
        self.exporter.shutdown()


class OpenTelemetryObserver:
    def __init__(self, *, exporter=None, capacity=256, content_allowlist=(), redact=None):
        if capacity < 1:
            raise ValueError("Positive queue capacity required")
        if content_allowlist and redact is None:
            raise ValueError("Content export requires an explicit redaction hook")
        self.diagnostics = {"dropped": 0, "export_failures": 0}
        self.queue: queue.Queue = queue.Queue(maxsize=capacity)
        self.allowlist, self.redact = frozenset(content_allowlist), redact
        self.provider = TracerProvider(
            resource=Resource.create({"service.name": "decision-firewall"})
        )
        self.provider.add_span_processor(
            SimpleSpanProcessor(
                _CountingExporter(exporter or OTLPSpanExporter(timeout=2), self.diagnostics)
            )
        )
        self.tracer = self.provider.get_tracer("decision-firewall", "0.3.0")
        self.stopped = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True, name="firewall-otel")
        self.worker.start()

    def emit(self, event: Observation):
        if self.stopped.is_set():
            self.diagnostics["dropped"] += 1
            return
        # Strip content before enqueueing, so it does not accumulate in export buffers.
        attrs = {
            key: value
            for key, value in event.attributes.items()
            if key in SAFE_ATTRIBUTES and isinstance(value, (str, int, float, bool))
        }
        for key in self.allowlist:
            if key in event.attributes:
                attrs[key] = self.redact(key, event.attributes[key])
        safe = Observation(event.name, event.correlation_id, event.status, event.duration_ms, attrs)
        try:
            self.queue.put_nowait(safe)
        except queue.Full:
            self.diagnostics["dropped"] += 1

    def _run(self):
        while not self.stopped.is_set() or not self.queue.empty():
            try:
                event = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                parent = trace.SpanContext(
                    trace_id=trace_id(event.correlation_id),
                    span_id=1,
                    is_remote=False,
                    trace_flags=trace.TraceFlags(1),
                )
                context = trace.set_span_in_context(trace.NonRecordingSpan(parent))
                end = time.time_ns()
                start = end - int(event.duration_ms * 1_000_000)
                # Link to a stable lifecycle ID; no fictitious long-lived parent span is exported.
                with self.tracer.start_as_current_span(
                    event.name,
                    context=context,
                    start_time=start,
                    record_exception=False,
                    set_status_on_exception=False,
                ) as span:
                    span.set_attribute("firewall.correlation_id", event.correlation_id)
                    span.set_attribute("firewall.status", event.status)
                    span.set_attribute("firewall.duration_ms", event.duration_ms)
                    for key, value in event.attributes.items():
                        span.set_attribute("firewall." + key, value)
            except Exception:  # noqa: BLE001 -- worker cannot disrupt a decision
                self.diagnostics["export_failures"] += 1
            finally:
                self.queue.task_done()

    def flush(self, timeout=5.0) -> bool:
        deadline = time.monotonic() + timeout
        while self.queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.queue.unfinished_tasks == 0

    def close(self, timeout=5.0):
        self.stopped.set()
        self.worker.join(timeout)
        if not self.worker.is_alive():
            self.provider.shutdown()
