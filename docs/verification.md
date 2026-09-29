# Local verification — 27 September 2026

Implementation: Python 3.12.14, Windows 11, NVIDIA GeForce GTX 1650 (4096 MiB), driver 616.56, approximately 8 GB installed system RAM. All payments were simulated.

## Measured benchmark

Each provider processed the same 240 cases (40 curated and 200 seeded variations), seed 42. The family split contains 159 development and 81 evaluation cases. The table uses the 81-case evaluation split for accuracy and latency; false allows/blocks cover all 240 cases.

| Provider | Evaluation n | Classification | Policy agreement | False allows / blocks | Warm inference p50 / p95 ms | Gate p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| fixture | 81 | 100.00% | 100.00% | 0 / 0 | 0.03 / 0.05 | 13.95 |
| baseline | 81 | 100.00% | 100.00% | 0 / 0 | 0.04 / 0.07 | 15.44 |
| laya | 81 | 97.53% | 100.00% | 0 / 0 | 75.25 / 104.02 | 11.97 |

Laya ran the pinned checkpoint on CUDA in FP32 with one worker, batch size one, and no CPU fallback. Cold loading took 9.344 seconds. Peak sampled process RSS was 3,147,436,032 bytes; PyTorch peak allocation was 1,703,006,208 bytes. These are process/allocator measurements, not total machine memory or total driver VRAM consumption. Initial checkpoint download time is excluded from the warm-cache cold-load result.

Across each final 240-case run there were zero observed over-refunds, duplicate effects, or unresolved executions. The fault-injection tests separately exercise unknown outcomes; benchmark requests awaiting review are not automatically approved. Full denominators, Brier scores, fixed-bin calibration, cue sensitivity, missing ordinal labels, versions, dataset/policy hashes and source hashes are in [Laya results](benchmarks/laya-results.json), [fixture results](benchmarks/fixture-results.json), and [baseline results](benchmarks/baseline-results.json). Standalone charts: [Laya](benchmarks/laya-report.html), [fixture](benchmarks/fixture-report.html), [baseline](benchmarks/baseline-report.html). Raw observations and runtime databases remain excluded from Git under `runs/`.

## What the diagnostic run changed

The first Laya run produced two false allows: a general service complaint was classified as a duplicate claim against a ledger containing a verified duplicate. The model label could select the eligibility path and bypass manual review. [The initial measurements are retained](benchmarks/diagnostic-before-intake-binding.json).

The corrected contract binds the customer's declared reason into the proposal independently of the model output. Eligibility uses that declaration plus trusted evidence; disagreement requires review. Regression tests exercise this boundary. Final results above are a rerun after that correction. Although the family split remains disjoint, the evaluation cases informed this policy fix; these are development/regression measurements, not an untouched independent validation set. No model-accuracy threshold was chosen after observing results. The keyword baseline's perfect result reflects simple synthetic language, not superiority on real customer traffic.

## Verification performed

- A fresh `.venv-clean` installed the core/development locks and built package without Torch or Laya. All 73 tests passed again, the 20-request CLI demo ran, and its exported receipt verified successfully.
- 73 pytest cases passed, including concurrent balance and daily-budget contention, binding/tampering, expiry, revoked/re-enabled identities, review hard constraints, missing evidence, policy/audit failures, downstream evidence races, delayed completion, response loss, restart, idempotency, receipt verification and historical replay.
- Ruff checks and formatting passed; mypy checked all ten Python modules; source distribution and wheel built successfully.
- Playwright in local Chrome passed keyboard navigation, filtering, empty state, review validation/save/re-evaluation, approve/reject/request-evidence actions, narrow layout, evaluation views and error routing. Axe detected zero violations on the tested review page; this is not a full accessibility certification. Screenshots were visually inspected. Browser evidence is local under `.runtime/browser-evidence/`.
- Strict premium UI audit: zero findings. DESIGN.md lint: zero errors, four documentation-only orphan-token warnings.
- Six Mermaid SVGs rendered successfully. Original reference hashes are recorded in [reference-hashes.json](reference-hashes.json).

Source hashes in benchmark manifests identify the measured snapshot before the final UI-only Origin/referrer fix and formatting. Policy, provider and execution behavior was unchanged by that final browser fix.

## Reproduction and remaining boundaries

See [setup](windows-setup.md), [walkthrough](walkthrough.md), and [evaluation protocol](evaluation.md). GitHub Actions defines Windows/Linux model-free CI but has not run remotely; Linux execution was not available in this local Windows session. Production authentication, credential isolation, alternate-path prevention and independently anchored audit require deployment integration. Signing on this host does not protect against full host compromise. CUDA succeeded here; the CPU fallback path is implemented but its resource performance was not measured on this machine.
