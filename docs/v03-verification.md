# v0.3 verification

Local verification on Windows 11, Python 3.12.14, 2026-09-27. Synthetic cases demonstrate framework behavior, not production effectiveness.

## Automated checks

- All 140 pre-existing tests retained; the new history, evaluation and observability suite adds 25 checks, including parameterized cases.
- Import atomicity, duplicate/revision conflicts, malformed CSV/JSONL, absent timestamps, independent labels, immutable hashes and grouped split leakage.
- Future/held-out/self retrieval protections, pinned custom-retriever results and whole-example budget handling.
- Offline resolver/executor poison checks, deterministic pinned decisions, missing/future snapshots, metrics and thresholds, named mandatory-rule failures, and per-rule persisted explanations.
- A v0.2 golden signed receipt verifies; its recorded policy fingerprint and historical replay still match using the retained implementation.
- In-process loopback OTLP collector verifies trace correlation across observer restarts and absence of content/secrets. A blocked/failing exporter exercises bounded queue drops. Malformed submitted identifiers/tokens are hashed before validation, so they cannot leak through correlation fields. Core callback tests acquire a write transaction to verify export occurs outside governance transactions and cannot change successful execution.
- Ruff, formatting, mypy, sdist/wheel build, local documentation links and runnable examples are checked by repository scripts/CI.
- A fresh temporary environment installs the built wheel and core lock only. It asserts Torch, Laya, FastAPI and OpenTelemetry are absent, then runs simulated execution, history import, reviewed annotations, snapshots, two policy variants, a custom invariant evaluator, CLI comparison, and both reference-domain examples.

Reproduce from the checkout:

```sh
python -m ruff check src tests scripts examples
python -m ruff format --check src tests scripts examples
python -m mypy src/decision_firewall
python -m pytest -q
python -m build
python scripts/verify-core-wheel.py
python scripts/check-doc-links.py
```

GitHub Actions configures model-free Windows/Linux verification and a separate optional telemetry job. Those hosted jobs have not been run from this local task. One existing Starlette/httpx deprecation warning remains; tests pass with the locked versions.

## Actual contextual Laya smoke

Command: `python scripts/smoke-contextual-laya.py .runtime-v03-smoke/result.json`.

| Measurement | Observed |
|---|---|
| GPU | NVIDIA GeForce GTX 1650, CUDA selected |
| Torch | 2.6.0+cu124 |
| SDK | Laya 0.3.20 |
| Checkpoint | `convaiinnovations/laya-typed-decisions` |
| Revision | `1a793eb568e6718f15941d08f85432581df534e3` |
| Precision / worker | FP32 / one |
| Selected historical examples | 1 development example |
| Current state with context | 126 tokens (256-token cap) |
| Loading | 27,272.74 ms, cached checkpoint files |
| Single inference | 3,009.38 ms, includes first-inference effects |
| Device fallback | None |
| Returned choice | `access` |

Dataset hash: `998cccce0c9fd1e653da7db248fe8a5b3daf55c9a6fc65dde0930882e959dd73`.

The complete current request and one prior same-domain example reached the context-aware adapter. Laya emitted a checkpoint-temperature warning and clamped an affected entry; confidence remains uncalibrated. This is one successful integration smoke, not a latency distribution, warm-performance benchmark or model-accuracy result. CPU fallback was not exercised on this successful CUDA run.

Raw runtime artifacts stay excluded from Git. Historical benchmark reports and `refer/` remain untouched. Optional OTLP interoperability is validated locally; no hosted Langfuse endpoint or real payment service was contacted. Plugins remain trusted Python code. Snapshot hashes detect content changes but do not establish source truth or defend a fully compromised host.
