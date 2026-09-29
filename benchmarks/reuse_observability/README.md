# Reuse and observability experiment

Run from the repository with Python 3.12:

```console
python -m benchmarks.reuse_observability.runner --output .runtime-reuse/new-conformance --mode conformance
python -m pip install -r requirements-telemetry.lock
python -m benchmarks.reuse_observability.runner --output .runtime-reuse/new-telemetry --mode telemetry
```

Output directories must be new. Runtime subdirectories contain private keys and bearer permits; never publish them. The report publisher selects only aggregate observations and redacted spans.

The protocol and 60 cases were frozen before execution. Their byte hashes are asserted in `tests/test_reuse_observability.py`. A first diagnostic run stopped because the harness expected receipt verification to return false, while the API correctly raises ValueError on tampering. The harness now treats that exception as rejection; the protocol, cases and production library were not changed. The diagnostic directory is retained locally.

This is a design-informed conformance and source-inventory study, not a randomized developer productivity study. Both arms share pure policy functions and a neutral durable simulated effect service. Refunds use immutable evidence snapshots and retained resource claims; this is separate from the earlier payment benchmark. The modular application is allowed a reusable runtime and the standalone telemetry adapter. It is not deliberately forced to duplicate controls or implement an OTLP exporter.

The domain adapter uses the supported ordinary policy-callable interface. Named RuleSet policies can emit additional rule metadata; this experiment does not characterize those paths. External telemetry is explicitly configured, while required local audit remains active without it. No hosted Langfuse service or model inference is involved.

See `docs/benchmarks/reuse-observability/summary.md` for measured results and limitations. Counts of owned source lines describe these implementations, not general savings or development hours.
