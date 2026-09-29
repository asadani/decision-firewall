# Does the framework earn its overhead?

Measured locally on Windows, Python 3.12.14, Intel i5-9300H, approximately 8 GB RAM. Fixture models; no GPU inference. Optional OpenTelemetry SDK 1.45.0. All effects simulated.

## Findings

The framework and a competent modular application matched the frozen safety expectations. The demonstrated distinction is reusable lifecycle implementation and signed audit, not better business decisions. A modular application can also reuse its controls across domains.

| Arm | Conformance | Extra effects versus expected |
|---|---:|---:|
| modular_application | 60/60 | 0 |
| firewall | 60/60 | 0 |

60 cases per arm: 15 families × two domains × two policy/configuration versions. One deterministic pass, not 60 independent real-world safety observations.

## Latency

| Arm / telemetry | n | p50 ms | p95 ms | Setup p50 ms |
|---|---:|---:|---:|---:|
| modular_application-off | 50 | 28.55 | 34.81 | 35.21 |
| modular_application-on | 50 | 24.09 | 33.48 | 19.21 |
| firewall-off | 50 | 39.63 | 47.27 | 70.39 |
| firewall-on | 50 | 39.02 | 45.89 | 61.14 |

Operation timing includes assessment, authorization and one simulated effect; initialization and final exporter drain are separate. Fifty seeded shuffled paired repetitions per condition, same in-memory exporter. No hosted service latency is measured.

Paired median telemetry on-minus-off: application -4.01 ms; framework 0.40 ms. Negative deltas reflect measurement variability, not evidence that telemetry makes execution faster. This run does not resolve a stable incremental telemetry cost. The full framework has a higher observed operation median in both conditions. No statistical p-value or production latency guarantee is claimed.

## Audit and observability

| Check | Modular application | Framework |
|---|---|---|
| Lifecycle stages: assessment | yes | yes |
| Lifecycle stages: evidence | yes | yes |
| Lifecycle stages: policy | yes | yes |
| Lifecycle stages: review | yes | yes |
| Lifecycle stages: authorization | yes | yes |
| Lifecycle stages: dispatch | yes | yes |
| Lifecycle stages: reconciliation | yes | yes |
| Lifecycle stages: outcome | yes | yes |
| Exported metadata: assessment_id | yes | yes |
| Exported metadata: evaluation_id | yes | missing |
| Exported metadata: authorization_id | yes | yes |
| Exported metadata: attempt_id | yes | yes |
| Exported metadata: policy_version | yes | missing |
| Exported metadata: reasons | missing | missing |
| Exported metadata: disposition | yes | missing |
| Trace linkage across process restart | yes | yes |
| Assessment linkage | yes | yes |
| Exported sensitive canaries | 0/4 | 0/4 |
| Observer callbacks under write lock | 0/14 | 0/20 |
| Successful effect despite exporter failure | 1/1 | 1/1 |
| Required audit outage blocks effect | yes | yes |
| Signed receipt verification and tamper rejection | unsupported | 60/60 |

The framework supplies eight lifecycle stages without application event hooks. However its ordinary callable-policy path lacks evaluation ID, policy version, disposition and reasons in exported spans. The manually instrumented application supplies the first three; the shared export allowlist omits reasons for both. Named RuleSet paths may emit additional metadata and were not measured here. These are observed gaps in the measured implementation, left unchanged during the study.

Actual loopback OTLP/HTTP spans were collected before and after a fresh Python process reconciled a lost response. Export failure diagnostics recorded 14 failed exports for the application and 20 for the framework. Both completed their effect. The common bounded adapter held 8 queued events and dropped 992 of 1000 new events while export was blocked; diagnostics exposed the drops and the queue drained afterward.

Local audit retains evidence and model details; external telemetry excludes the four request/evidence/model/credential canaries. Signed receipts detect altered history given a trusted public key; they do not protect a fully compromised signing host. The application logs are unsigned by design: signing is extra functionality bundled by the framework, not something an application cannot implement.

## Reuse and owned implementation

Application runtime: 200 nonblank lines; framework integration: 110 nonblank lines. Shared business policies: 79; shared fake service: 54. The reused core library itself contains 1382 nonblank lines. These include imports, comments and docstrings; integration includes benchmark API wrappers. They are source inventory, not equivalent functionality, productivity, security or maintenance scores.

The application has 8 explicit note call sites and 4 operation decorators; the framework integration has zero event hooks and passes an observer to its SDK. Both share the standalone exporter utility. Users can adopt that utility without the full runtime.

Both arms reuse the same lifecycle code for refunds and data export. Both consume the same shared policy change: one refund configuration field, two export configuration fields, and a four-nonblank-line export-v2 function adding the mandatory legal-hold check. No lifecycle implementation changes were needed between those variants. Thus this experiment does not show easier business-rule editing than a modular application. It shows an existing runtime replaces code the application otherwise owns. No human onboarding, development hours, diagnosis time or ROI was measured.

## Interpretation and limitations

Use the framework when standardized authorization/recovery/audit across several workflows is worth owning less lifecycle code and accepting its runtime cost. An application that already has these controls may gain little from migration. Telemetry alone does not justify the entire runtime: reuse the observer utility or existing instrumentation. The strongest demonstrated extra here is supplied lifecycle instrumentation plus signed audit; exported policy metadata still needs improvement.

The application was deliberately allowed sensible modularization. Shared policy functions eliminate business-logic differences, so agreement is partly by construction; the adversarial cases test lifecycle enforcement. One author implemented both adapters. This is a local synthetic, design-informed study, not an independent productivity trial. No model accuracy improvement is asserted. No production core files were changed to improve measured results. The first diagnostic stopped on the harness's incorrect assumption that tamper verification returns false rather than raising ValueError; that harness bug was corrected before the completed run. Frozen cases stayed unchanged.

## Reproduce

See ../../../benchmarks/reuse_observability/README.md in the repository. Manifests contain protocol, case and source hashes. JSON observations, latency.csv, engineering.json and redacted OTLP spans accompany this report. Runtime stores, permits and signing keys are excluded.
