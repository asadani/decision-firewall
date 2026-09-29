# Optional OpenTelemetry and Langfuse

Core exposes `Observer.emit(Observation)` in `decision_firewall.core.observation` without importing telemetry packages. Pass `observer=` to `DecisionFirewall`, `ExperimentRunner` or `ContextualModel`. The optional adapter exports OTLP/HTTP:

```sh
python -m pip install -r requirements-telemetry.lock
```

```python
from decision_firewall import DecisionFirewall
from decision_firewall.domains.access.pack import access_domain
from decision_firewall.adapters.opentelemetry import OpenTelemetryObserver

observer = OpenTelemetryObserver(capacity=256)
firewall = DecisionFirewall(".runtime-observed", [access_domain(".runtime-observed")],
                            observer=observer)
# Use the ordinary SDK operations here.
observer.flush(timeout=5)
observer.close(timeout=5)
```

Set standard `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` (including `/v1/traces`) and `OTEL_EXPORTER_OTLP_TRACES_HEADERS`, or the generic OTLP endpoint/headers variables. The exporter uses the SDK's standard HTTP configuration. Configuration examples: [OpenTelemetry Python exporters](https://opentelemetry.io/docs/languages/python/exporters/).

For an existing Langfuse installation, set the endpoint to your deployment's `/api/public/otel/v1/traces` and configure its Basic authorization header using its public/secret key pair. Use your actual regional/self-hosted base URL and keep headers in environment/secret configuration, never source or reports. Langfuse's [native OpenTelemetry integration](https://langfuse.com/integrations/native/opentelemetry) documents endpoint and authentication setup. No Langfuse service is provisioned or required. These are generic governance spans; we do not manufacture LLM generation content or costs.

Assessment, retrieval, evidence resolution, policy rules, review, authorization, dispatch, reconciliation and experiments emit observations. Decision IDs reconstruct stable trace IDs across restart. Evaluation and attempt IDs appear on relevant audit observations; assessment hashes connect assessment and submission. Human waiting uses separate operations, not an indefinitely open span. The stable trace context has a synthetic unexported parent; consumers can group by `firewall.correlation_id` even if they display orphan roots. Pass the same observer to a contextual model to collect its retrieval observations.

Default export includes IDs, versions, statuses, durations and safe counts. No request text, evidence bodies, raw outputs, credentials or tokens are exported. Local experiment artifacts may contain full synthetic/imported input; protect them separately. Explicit `content_allowlist` additionally requires `redact(key, value)`; redaction runs before enqueue. Instrumentation does not produce content attributes by default, so integrations must deliberately supply any allowed content.

Governance observations buffer until the outer operation leaves its transactions. Core buffers at most 256 observations per operation; the adapter's bounded queue exports asynchronously on one worker. Saturation drops telemetry and increments diagnostics; export failures increment `observer.diagnostics["export_failures"]`. Core callback errors/drops are exposed in `core.observation.diagnostics`. Neither changes policy or execution results. Required local audit failures still block authorization. Telemetry does not enter authorization fingerprints or signed payloads.

Call `flush` and `close` on orderly shutdown. They wait only up to the requested duration; a permanently blocked third-party exporter may leave a daemon worker unfinished, and queued telemetry can be lost on abrupt shutdown. The default HTTP exporter has a two-second timeout. Applications needing durable external telemetry should operate their own collector. Tests use an in-process loopback OTLP collector, exporter failure and queue saturation; they contact no external service.
