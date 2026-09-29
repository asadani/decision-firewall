# With and without Decision Firewall

Paired synthetic diagnostic results. The competent application baseline is the primary comparator; direct model routing is a deliberately minimal reference arm.

## What was held constant

The 32 frozen scenarios contain 34 requests per pass, including two concurrent pairs. Five repetitions give 160 scenario trials and 170 request trials per arm and provider condition. Repetitions are runtime samples, not additional independent efficacy cases. All arms receive identical applied model signals, requests, evidence and fault schedules, and use the same payment simulator with balance/destination/idempotency protections enabled.

Cases were designed with knowledge of the implementation. This is not a held-out model accuracy benchmark or production effectiveness estimate. Two declared model-fault cases inject disagreement/unavailability even in the Laya condition; raw outputs and applied labels are recorded separately.

## controlled_fixture

| Measurement | Model-directed | Application controls | Decision Firewall |
|---|---:|---:|---:|
| Scenario trials | 160 | 160 | 160 |
| Request trials | 170 | 170 | 170 |
| Initial policy matches | 110 | 170 | 170 |
| Completed simulated refunds | 155 | 60 | 60 |
| Unsafe processor calls | 115 | 0 | 0 |
| Contract-violating effects | 95 | 0 | 0 |
| Duplicate effects (subset of violations) | 20 | 0 | 0 |
| Over-refunded minor units | 0 | 0 | 0 |
| Expected successful effects missed | 0 | 0 | 0 |
| Unresolved attempts after recovery | 15 | 0 | 0 |
| Initial review referrals | 10 | 30 | 30 |
| Matched straightforward success p50, ms | 5.60 | 22.14 | 44.74 |
| Matched straightforward success p95, ms | 7.33 | 31.62 | 52.90 |
| Initial storage/key setup p50, ms | 17.37 | 29.03 | 63.51 |

Paired median framework overhead on matched straightforward successes: **22.53 ms**, n=25 paired trials. This is the median of within-case/repetition differences, not subtraction of unrelated percentiles. The matched set contains two basic eligibility patterns and three incentive-cue variants; it is small and synthetic.

Signed framework receipts verified: 160/160. The application baseline has plain transactional audit records; signed receipt verification is unsupported there, not a failed-verification count.

## local_laya

| Measurement | Model-directed | Application controls | Decision Firewall |
|---|---:|---:|---:|
| Scenario trials | 160 | 160 | 160 |
| Request trials | 170 | 170 | 170 |
| Initial policy matches | 110 | 170 | 170 |
| Completed simulated refunds | 155 | 60 | 60 |
| Unsafe processor calls | 115 | 0 | 0 |
| Contract-violating effects | 95 | 0 | 0 |
| Duplicate effects (subset of violations) | 20 | 0 | 0 |
| Over-refunded minor units | 0 | 0 | 0 |
| Expected successful effects missed | 0 | 0 | 0 |
| Unresolved attempts after recovery | 15 | 0 | 0 |
| Initial review referrals | 10 | 30 | 30 |
| Matched straightforward success p50, ms | 5.89 | 22.96 | 43.82 |
| Matched straightforward success p95, ms | 7.31 | 28.09 | 49.39 |
| Initial storage/key setup p50, ms | 17.23 | 28.79 | 63.93 |

Paired median framework overhead on matched straightforward successes: **20.57 ms**, n=25 paired trials. This is the median of within-case/repetition differences, not subtraction of unrelated percentiles. The matched set contains two basic eligibility patterns and three incentive-cue variants; it is small and synthetic.

Signed framework receipts verified: 160/160. The application baseline has plain transactional audit records; signed receipt verification is unsupported there, not a failed-verification count.

Local model: `convaiinnovations/laya-typed-decisions` at `1a793eb568e6718f15941d08f85432581df534e3`; device `cuda`, FP32, Laya SDK 0.3.20. Cold loading 28207.20 ms; median recorded inference 47.41 ms across 34 request assessments (includes the first inference). Inference is reused and excluded from arm latency. Fallbacks: ['None']. Confidence remains uncalibrated.

## Interpretation

The framework did not improve observed safety over the competent application baseline: both had zero violating effects. It added measured latency. Its demonstrated differences here are reusable lifecycle implementation and verified signed receipts, not unique safety capability.

The direct arm illustrates what goes wrong when favorable request classifications are mapped straight to actions without application controls. It is not evidence that Laya autonomously authorized these refunds, nor that a framework is the only remedy. Downstream balance/destination protections remain responsible for preventing some failures in every arm.

Duplicate effects are included in contract-violating effects; do not add those columns. Over-refunding is separately measured against payment balance and may remain zero despite duplicate or ineligible refunds. Review referrals measure workflow burden, not reviewer time. A blocked malformed attempt does not mean the customer's underlying refund request is ineligible.

## Engineering tradeoff

Nonblank source lines (including comments/docstrings): independent application policy/control module **205**; benchmark framework integration class **45**; reusable core package **1116**. The wrapper relies on the existing refund domain pack and core; these are not total-system size comparisons. The framework moves complexity into a dependency, it does not remove it. No developer-hour, productivity or maintenance-cost measurement was performed.

Both governed approaches implement eligibility checks, review permissions, action/evidence binding, expiration/revocation, transactional resource reservations, durable attempt keys, reconciliation and required local audit. The framework additionally provides signed portable records, versioned policy replay and reusable domain interfaces; this experiment verifies receipts but does not quantitatively value long-term maintenance or independently benchmark every capability.

## Limits and reproducibility

Measured locally on Windows, Intel Core i5-9300H, approximately 8 GB RAM, GTX 1650 for Laya. Arms run in seeded randomized order; initialization is measured separately. Fresh-process recovery startup is included in lifecycle latency but is absent from the matched straightforward subset. Required local audit/simulator costs are included. No per-arm memory, throughput scalability or human integration-time claims are made.

These are design-informed conformance cases with a fully specified favorable/other-classification execution mapping. No legal entitlement, production incident reduction, general model accuracy or compliance certification follows. The application baseline targets one daily budget window and one local process dispatch lock, as does this test. No real payment API was called.

The one-pass diagnostic was retained under the ignored `.runtime-value/diagnostic-fixture` directory; it was not used to alter the frozen cases, rules or pass criteria. Public files contain synthetic observations and applied assessments only; runtime databases, signing keys and bearer permits are excluded.

Reproduce with the [protocol and runner](../../../benchmarks/framework_value/README.md). Each result contains source hashes, protocol/dataset hashes, repetitions and environment metadata. Read all case-level outcomes before interpreting aggregate numbers.
