# Framework review — 28 September 2026

Fresh source review and adversarial regression validation before benchmark reruns.
This is a review by the implementing assistant, not an independent external security audit.

## Scope

Reviewed the generic runtime and contracts, audit/storage, policy/rules, preparation,
refund and access packs (including legacy compatibility), durable simulators, history
imports/snapshots, retrieval, experiments, provider adapters, observation/OTLP export,
CLI/starter, inspector routes/templates/client behavior and benchmark transport.
Existing tests were treated as evidence to challenge, not proof that the implementation
was correct. Plugins remain trusted Python code; the runtime is not a hostile-code sandbox.

## Confirmed findings and fixes

1. **High — legacy dispatch revalidation gap.** The legacy refund runtime validated
   authority before reservation, then dispatched in a second transaction without rechecking
   identity revocation, policy change or expiry. It now revalidates all bindings and policy
   under the dispatch lock, excluding its own reservation and accounting for a changed UTC day.
   Regression cases revoke requester/executor, change policy and expire the permit between
   reservation and dispatch. All prevent payment effects.
2. **Medium — missing-session CSRF sentinel.** A caller without a session could supply the
   literal `missing` as the CSRF field when presenting a valid Origin. Review now explicitly
   requires a session CSRF token. Origin protection remains; this finding did not establish
   arbitrary cross-origin browser exploitation.
3. **Medium — unsigned audit-envelope metadata.** Receipt verification checked signed bodies
   but ignored duplicated outer sequence/request identifiers. Verification now requires the
   envelope to match its signed body. Existing receipt fixtures still verify; signed payload
   formats and historical records are unchanged.
4. **Medium — simulator amount type.** Direct simulator calls could supply fractional or
   boolean amounts despite the domain contracts requiring integer minor units. The payment
   adapter now rejects these before touching its ledger.
5. **Medium — nested mutation across extension boundaries.** Frozen Pydantic records do not
   freeze dictionaries. Ordinary policy calls could mutate their input snapshot; context-aware
   models and evaluators could contaminate later variants. Validated isolated copies now cross
   these boundaries. Retrieval adapters also receive copies, and contextual input revalidates
   the dataset hash. Regression tests verify unchanged policy inputs and later-variant results.

The previous transport review additionally fixed provider/finish validation, redirect handling,
single-use budget settlement, durable attempt metadata, overrun blocking and exact echo checks.

## Validation completed before reruns

- 236 pytest tests passed, including compatibility receipt/replay fixtures, concurrency,
  unknown outcomes, rule safety, history leakage, telemetry failure and new regressions.
- Ruff lint and Python formatting passed; mypy passed across 44 source files.
- Wheel and source distribution built successfully.
- Fresh core-only wheel installed without model/web/telemetry dependencies and completed
  history import, policy comparisons, custom evaluation, starter and both reference domains.
- Chromium browser flows passed: search, empty states, keyboard select, review validation,
  approve/reject/request-evidence, narrow viewport and error navigation. No JavaScript errors;
  the measured review page had zero Axe violations.
- Local Markdown links passed. Windows was exercised here; Linux CI was not executed locally.

## Boundaries and remaining work

No finding justifies claiming a production security certification or protection from a
compromised host. Local signing keys and configured identities remain trusted. Evidence sources
and executors need deployment-specific atomicity/authentication outside the supplied simulators.
Ordinary callable-policy OTLP metadata still lacks some evaluation/policy fields; full reasons
remain in local signed audit rather than default external export.

The OpenRouter echo probe is not an official agent benchmark. Tau-bench and AgentDojo still
require reviewed tool-boundary integrations. Do not substitute synthetic conformance scores for
their task-success or attack-success scores. No paid inference occurred during this review.

Subsequent work on 29 September completed the optional integrations and a
[90-episode development pilot](../benchmarks/agent-pilot/summary.md). The preceding
paragraph records the status at the original review checkpoint; the pilot's own
manifest, validation, incomplete episodes and cost accounting are reported separately.

Benchmark reruns use new artifact directories and unchanged frozen scenarios. Historical
published results are retained; source hashes distinguish the corrected implementation.

## Post-review benchmark results

Completed across 28–29 September local time, after the validation above. The
[refund comparison](../benchmarks/post-review-refund/summary.md) and its
[standalone report](../benchmarks/post-review-refund/report.html) contain the fresh
fixture and local Laya runs: 32 frozen scenarios, five repetitions, 170 request
trials per arm and provider condition.

Both competent application controls and Decision Firewall matched all 170 initial
policy outcomes, with zero violating effects, duplicate effects, over-refunds,
missed expected effects or unresolved outcomes after recovery. Framework receipts
verified 160/160 in each provider condition. The direct-routing reference produced
95 violating effects (including 20 duplicates) and left 15 unresolved attempts.
It is intentionally minimal and is not the primary engineering comparator.

Matched paired framework overhead was 23.23 ms with fixtures and 28.18 ms with
Laya (25 timing pairs each). Laya used CUDA FP32 on the GTX 1650 without CPU
fallback; cold loading was 28.42 s and median recorded inference was 47.45 ms
across 34 assessments, including the first inference. Inference was reused across
arms and excluded from lifecycle timings. The model revision and SDK version are
recorded in the report. These are local desktop measurements, not isolated-machine
performance tests; source preparation also ran during part of the Laya benchmark.

The [fresh reuse/observability comparison](../benchmarks/post-review-observability/summary.md)
passed 60/60 cases per arm across two domains and two policy versions, with zero
extra effects. All eight measured lifecycle stages were exported; restart linkage,
redaction and exporter-failure isolation passed. Required local audit failure
blocked effects. Framework receipt verification and tamper rejection passed 60/60.
The metadata omissions described above remain visible in the report.

Framework operation p50 was 39.63 ms with telemetry off and 39.02 ms with telemetry
on; the median of 50 paired on-minus-off differences was +0.40 ms. The application
paired delta was negative, illustrating timing noise. This run does not resolve a
stable incremental telemetry cost. The bounded exporter held eight queued events
and reported 992 dropped events under the deliberate blocked-exporter stress test.

The public BANKING77/Bitext reports remain historical results, not reruns of those
39,955 rows. No new OpenRouter calls were made. A pinned partial Tau-bench checkout
failed to retrieve source blobs; neither Tau-bench nor AgentDojo was executed or
assigned a score in this validation pass.
