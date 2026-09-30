# 0.3.1 corrective release — 2026-09-30

Decision: **narrow to a tested reference implementation and conformance kit**.
Feature expansion and adoption/migration claims have stopped. This release repairs
confirmed core defects and missing regression coverage; it does not rerun the paired
pilot or establish an adoption benefit.

## Independent evidence preserved

The [comparison](../../evaluations/2026-09-29/COMPARISON.md) and
[findings](../../evaluations/2026-09-29/findings.md) are unchanged copies of the
user-provided independent evaluation. The original source snapshot, builds, tests,
protocol and reproduction scripts remain untouched in the evaluation directory.
The report's 9× figure is the measured held-out-suite duration, not a universal
per-request slowdown. The approval-after-outage test ambiguity remains a protocol
limitation, not a claimed framework improvement.

## Corrected behavior

| Finding | Correction | Evidence |
|---|---|---|
| DF-01: approval bound to unseen evidence | Require the latest inspected evaluation ID; compare its proposal, assessment, evidence and policy to current material facts before recording approval | Stale, missing, superseded and wrong-request IDs fail without creating a review or authorization |
| DF-02: rejection disappears and older approval returns | Select the latest review before validating it; retain rejection as a veto for its revision | Evidence restoration, reviewer deactivation/generation changes and expiry cannot revive prior approval |
| DF-05: large integer result wedges an effected attempt | Losslessly encode oversized metadata integers for canonical audit; preserve valid execution status | Direct success and lost-response/restart recovery both complete once, with verifiable receipts |
| DF-04: six surviving mutations | Add core-specific tests independent of downstream checks | All nine reviewed fault classes detected in an isolated mutated copy |

Old approvals without inspected-evaluation provenance fail closed on new dispatch.
Existing uncertain executions still reconcile using their original keys, and existing
signed records are not rewritten. The [migration guide](../../framework/migration.md)
documents the required approval-call change, metadata envelope and scope boundary.

## Verification

- Windows, Python 3.12.14: **298 tests passed**, including **22 corrective tests**.
- [Mutation report](mutations.json): baseline passed; **9 killed, 0 survived, 0 errors**.
  This is a targeted nine-fault check, not comprehensive mutation coverage. M9 uses
  an updated textual mutation for the new latest-review-first implementation while
  removing the same reviewer-generation invariant. Runtime/test hashes are recorded.
- The original DF-01, DF-02 and DF-05 reproductions demonstrated the defects before
  fixes. Regression tests exercise DF-01/02 using the new explicit evaluation API;
  the untouched old scripts omit this required argument and therefore fail closed.
- The original large-integer reproduction now records `SUCCEEDED`, one effect and a
  completed request. Further reconciliation correctly refuses an already resolved
  attempt. The original positive binding/recovery reproduction passes **16/16**.
- Ruff and mypy pass. The full suite retains an existing Starlette/httpx deprecation
  warning. Windows/Linux CI includes the mutation check; Linux was not run locally.
- The 0.3.1 wheel and source distribution build successfully. A fresh core-only wheel
  installation passes starter approval/execution, history/evaluation, conformance
  and incident reconstruction without model, web or telemetry dependencies.

Reproduce the bounded regression and mutation checks:

```sh
python -m pytest tests/test_corrective_release.py -q
python scripts/check-safety-mutations.py --output .runtime-corrective/mutations.json
python -m pytest -q
python -m ruff check src tests scripts examples benchmarks
python -m ruff format --check src tests scripts examples benchmarks
python -m mypy src/decision_firewall
python -m build
python scripts/verify-core-wheel.py
```

## Test-count reconciliation

The previous **276 passed** result included two optional OpenTelemetry tests. The
independent environment did not install OpenTelemetry: its **274 passed, 1 skipped**
result counts the skipped module once, rather than collecting its two tests. These
are different dependency profiles, not two missing core tests. Historical result files
are preserved; future reports must state the optional-dependency profile.

## Deliberately unchanged limitations

The global SQLite write lock still spans adapter I/O. The fixed approval lifetime,
per-runtime identity, per-permit revocation, full-pack reconciliation fingerprint,
local signing trust and lack of operator resolution for permanently ambiguous effects
are not redesigned. The separate v0.1 refund compatibility engine/browser is not
covered by these generic-runtime fixes and retains its documented duplicated lifecycle.
No new domains, paid benchmarks, human-productivity claims or follow-up study are included.
