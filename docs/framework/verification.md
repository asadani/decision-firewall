# Framework 0.2 verification — 27 September 2026

Verified locally on Windows 11 with Python 3.12.14. All action effects were simulated.

| Check | Observed result |
|---|---|
| Full pytest suite | 140 passed; one upstream Starlette/httpx deprecation warning |
| Refund compatibility | Original 73 tests still pass after extraction |
| Generic refund policy | All 40 curated scenarios match expected dispositions on the new core |
| Independent domain | Access request validation, review, execution, replay and receipt verification pass |
| Generated extension | Starter executes successfully from a temporary directory outside the repository |
| Resource contention | Concurrent balance/daily-budget tests block excess execution and retain unknown reservations |
| Authorization | Tampering, expiry, revocation, re-enabled identities, changed policy/evidence and revisions prevent execution |
| Failure recovery | Delays, response loss, restart, pre-dispatch crash, post-effect audit failure and malformed adapter responses reconcile safely |
| Extension failures | Missing evidence, model/provider errors, policy errors and unsupported constraints fail closed |
| Static verification | Ruff checks/formatting and mypy (32 modules) pass |
| Packaging | Source distribution and wheel build successfully |
| Minimal installation | Fresh `.venv-core` installs the wheel and core lock; access/refund demos and starter work without Torch, Laya, FastAPI, Jinja or Uvicorn |
| References | Four original reference-file hashes match the recorded originals |

Two actual optional Laya smoke assessments also succeeded on the GTX 1650 using CUDA, FP32 and no CPU fallback: a generic access/urgency question set and the existing refund facade. The former returned `access`; the latter returned `duplicate`. See [recorded smoke outputs](laya-smoke.json). These are single-inference compatibility checks, not an accuracy or warm-inference benchmark. The access cold load ran alongside packaging work. Laya's temperature warning remains recorded as uncalibrated confidence.

The seven Mermaid sources render to SVG, including the new framework architecture. The generic runtime's core import-boundary test prevents dependencies on domain packages, model runtimes and browser tooling.

## Limits and reproducibility

Run the commands in the repository README to reproduce verification. CI now covers both reference domains and the generated starter in the configured Windows/Linux matrix. Hosted CI and local Linux execution have not run during this Windows session.

The browser inspector is still the refund reference application; this refactor did not add generic-domain browser views. Its API tests passed; the previous browser evidence remains historical. The 240-case v0.1 model benchmark is also historical and has not been relabeled as a framework 0.2 benchmark. No new model-accuracy threshold or production effectiveness claim was introduced.

Remaining production boundaries: authenticated callers, isolated executor credentials, independently anchored audit, multi-process/distributed coordination across separate stores, and real provider failure/idempotency guarantees. See the executor contract, migration guide, security notes and roadmap.
