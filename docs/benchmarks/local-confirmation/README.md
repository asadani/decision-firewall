# Local benchmark confirmation — 28 September 2026

Fresh local executions of the unchanged frozen protocols. These results measure governance,
audit, recovery, reuse and overhead; they do not claim improved model accuracy.
Earlier published results remain unchanged. All financial effects are simulated.

## Actual local model

The refund comparison used cached Laya checkpoint
`convaiinnovations/laya-typed-decisions@1a793eb568e6718f15941d08f85432581df534e3`,
SDK 0.3.20, CUDA FP32 on the GTX 1650 (4 GB), with no CPU fallback.
Hugging Face and Transformers offline flags were enabled. No hosted inference was used.
Loading took 29.30 seconds; median inference across 34 assessments was 49.95 ms,
including the first inference. Confidence remains uncalibrated; the SDK emitted its
checkpoint temperature warning. Each assessment was shared across treatment arms.

## Results

- [Refund comparison](refund/summary.md): 32 scenarios, five repetitions, 160 episodes
  and 170 request trials per arm. Application and framework both had zero unsafe effects,
  duplicates, over-refunds, missed expected effects and unresolved outcomes. Framework
  receipts verified in 160/160 episodes. Paired median framework overhead on 25 matched
  straightforward success trials was 26.34 ms, excluding inference and initialization.
- [Audit and observability comparison](observability/summary.md): both implementations
  passed 60/60 conformance cases across refund and data-export domains. Framework signed
  receipts and tamper rejection passed 60/60. Eight lifecycle stages were instrumented
  without application event hooks. The ordinary callable-policy telemetry path still
  lacks evaluation ID, policy version, disposition and reasons; this limitation is retained.
- Framework operation p50 was 42.32 ms without external telemetry and 43.86 ms with it;
  paired median telemetry increment was 1.48 ms over 50 pairs. Local desktop variation
  limits interpretation. Actual loopback OTLP, restart linkage, redaction and exporter
  failure checks completed. No hosted Langfuse service was used.

The competent application already supplies equivalent safety controls. The demonstrated
framework value is supplied lifecycle code, signed records and instrumentation, with added
processing cost. Source line counts are not measurements of developer time or maintenance ROI.

## Scope

These are synthetic, implementation-informed scenarios, not independent production efficacy
estimates. Repetitions are timing samples, not new cases. The direct arm deliberately maps
classifications to actions without application governance; its failures do not establish
that a framework is the only way to implement controls.

This run does not execute tau-bench or AgentDojo. No local conversational tool-calling model
is installed; Laya is a typed classifier. The full BANKING77/Bitext results from the earlier
run are unchanged and were not rerun here. No new model weights were downloaded.

## Reproduce

From the repository root, in the existing model and telemetry environment, choose new output
directories. On PowerShell:

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
.venv/Scripts/python.exe -m benchmarks.framework_value.runner --output .runtime-local-confirmation/laya --provider local_laya
.venv/Scripts/python.exe -m benchmarks.reuse_observability.runner --output .runtime-local-confirmation/reuse --mode all
```

The linked reports include sanitized observations and manifests with source, dataset and
protocol hashes. Private runtime databases, signing keys and permits remain in ignored
`.runtime-local-confirmation/`. HTML comparisons are available in each report directory.
