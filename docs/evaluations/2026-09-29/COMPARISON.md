# Decision Firewall evaluation: comparison and recommendation

**Recommendation: NARROW.** Stop feature expansion and adoption/migration claims. Keep Decision Firewall as a tested reference implementation and conformance kit for action-bound authorization and recovery. Continue only if a harder, independent adoption test (see the end) shows a benefit that this pilot could not detect.

This is one paired diagnostic pilot: one task, one agent builder per arm, same model. It is not a statistical study, and nothing below generalizes beyond these two builds.

Evaluated snapshot: `hashes/source-sha256.txt` (337 files, manifest sha256 `6a7b8331…07d8`). Protocol frozen at 14:40:24Z, before either builder started (`hashes/protocol-*-freeze.sha256`). The public and sealed protocol files were re-verified unchanged after all phases.

## 1. Measured agent-based results

| Measure | Framework arm (DF) | Baseline arm (no DF) |
|---|---|---|
| Completion | complete | complete |
| Visible acceptance tests | 26/26 | 26/26 |
| Held-out acceptance tests | 114/115 | 114/115 |
| Hard-invariant test failures | 1 (same test, HI-1)¹ | 1 (same test, HI-1)¹ |
| Build tool calls | 45 | 34 |
| Build agent elapsed (transcript) | ~18.0 min, in two segments² | ~11.0 min |
| Setup before first source write | 5.6 min | 2.2 min |
| Implementation vs debugging split | unavailable | unavailable |
| Build tokens | unavailable² | 176,412 (subagent_tokens) |
| Interventions | 1 (resume after API-limit termination) | 0 |
| Workarounds recorded by builder | 8 (all against DF contracts) | 2 (pytest/tmp paths only) |
| Requests for core changes | 7 | 0 |
| Framework core changes | 0 (installed package byte-identical to snapshot) | n/a |
| Source / own-test LOC | 1,429 / 468 | 1,398 / 507 |
| Harness execution time, held-out suite (same 115 tests) | 39.6 s | 4.5 s |
| **Policy change CR-1**: v2 visible / v2 held-out | 5/5, 10/10 | 5/5, 10/10 |
| CR-1: v1 regressions (141 tests) | 0 | 0 |
| CR-1: maintainer tool calls / elapsed | 32 / 11.9 min | 20 / 6.2 min |
| CR-1: source lines +/- | +95 / −17 | +52 / −13 |
| **Investigation** (4 incidents, blind-scored) | 48/48, 0 incorrect conclusions | 48/48, 0 incorrect conclusions |
| Investigation tool calls / elapsed | 24 / 7.9 min | 23 / 5.8 min |

¹ `test_hidden_eligibility.py::test_h_records_outage_at_issue_blocks_dispatch`. After an evidence outage at issue with records returning **unchanged**, both implementations keep the prior approval and re-authorize; the test expects NEEDS_APPROVAL. Both builders flagged this spec ambiguity in their logs before scoring (REQUIREMENTS §7 step 4 discards "the authorization", step 5 discards "the authorization and any approval"). No downstream effect occurred in either arm. Under the frozen protocol it is scored as a failure. I treat it as a protocol/spec defect, not a differentiator.

² The framework builder was terminated at 14:55Z by an account spend-limit error (HTTP 429) after 37 calls. It was resumed once with its context intact and a neutral "continue" message, and finished with 8 more calls. Its interrupted state scores identically (26/26, 114/115; `builds-interrupted/`). Token usage for the first segment was lost.

**Reading.** Correctness was identical in every phase. The framework arm used somewhat more agent effort to build and to maintain, but a single run cannot separate that from run-to-run noise. The investigation exercise reached its ceiling and does not discriminate. The one clear, repeatable difference is execution cost: the DF implementation ran the same held-out suite about 9× slower (DF serializes operations under one SQLite write lock and runs adapter I/O inside it; review finding DF-09).

## 2. Functional and security findings within tested scenarios

Independent review (`review/findings.md`, `findings.json`) produced 21 findings: 4 confirmed defects, 12 design limitations, 3 documentation problems, 2 unverified concerns. None is critical or high. I re-ran all 14 reproductions after the measured phase and they reproduced (`results/repro-rerun/output.txt`).

Confirmed defects:
- **DF-01** (medium): approval binds to evidence re-resolved at review time, not the evaluation the reviewer saw. An approval for evidence v1 executed against v2 (r02).
- **DF-02** (medium): a rejection is not durable. Deactivating the rejecting reviewer revives an older approval, which then executes (r03).
- **DF-04** (medium): mutation testing of `core/runtime.py` caught only 3 of 9 injected faults. Removing the pre-dispatch second validation, the reconcile fingerprint guard, approval/evidence binding, approval expiry or reviewer-generation binding still passes the repository suite.
- **DF-05** (medium): an adapter result detail with an integer above 2^53 wedges an already-effected attempt in RESERVED, and every reconcile fails (r10).

Main design limitations:
- **DF-03:** revoke is per-permit; the same approval yields a new permit (r01).
- **DF-06 / DF-07:** the signing key sits beside the data; tail truncation is invisible; approval rows are unsigned and `investigate()` does not cross-check them (r06, r07).
- **DF-08:** roles are labels; one CLI user can request, approve and execute (r12).
- **DF-09:** the global write lock is held during adapter I/O (r08).
- **DF-10:** there is no operator path for an attempt the adapter can never resolve.
- **DF-11:** a policy-only upgrade strands unresolved attempts until the old pack is re-registered (r09). The framework builder and maintainer both had to work around this.

Claims that held up (r13 16/16, r05): permits are bound to action, evidence, versions, identity generation and expiry; evidence is re-resolved before dispatch; lost responses stay UNKNOWN with reservations held; reconcile reuses the original key; a capacity-1 claim admitted exactly one dispatch across 8 OS processes; replay calls neither resolver nor executor. Repository pytest: 274 passed, 1 skipped (the docs claim 276, DF-19). ruff and mypy are clean.

How DF-specific defects did and did not surface in the pilot: none of DF-01, DF-02 or DF-03 caused a failing acceptance test in the framework arm. The builder re-implemented the issue-time checks (expiry, versions, approver validity, budget) in its own layer before calling `execute`, because `execute` reports all refusals as one generic error (workaround 2). The framework arm therefore ended up carrying most of the same checks as the baseline, plus DF's checks underneath.

Domain neutrality: the core contains no refund or access concepts, and the ~600-line runtime does real lifecycle work. The residue is model-centric (every submission needs an assessment and a message), plus one fixed identity per runtime instance. The PO builder ran one DF instance per approver to fit a per-call identity model (workaround 1). Adapters and deployments still own authentication, the downstream idempotency and effect boundary, reconciliation truth, key and checkpoint protection, cross-request deduplication (DF-12), and the directory of who may approve.

Nothing here establishes production security. All results come from local, simulated, single-host runs on Windows.

## 3. Human productivity and adoption claims: untested

- No human developers took part. Agent tool calls and minutes are not developer hours.
- Detailed, prescriptive requirements are a strong confound. REQUIREMENTS.md (374 lines) spelled out the lifecycle: binding, expiry, check order, budget accounting, unknown handling and audit fields. That removes much of what a framework's design is supposed to supply. A team without such a spec might benefit more from DF's built-in lifecycle; this pilot cannot show that either way.
- The framework arm had asymmetric context (it could read DF docs and source) and a different kind of learning cost (5.6 min vs 2.2 min before first source write).
- Onboarding across several integrations, where reuse would pay off, was not measured. This was one integration.
- The investigation incidents included an operator export of the downstream effect store for both arms. That made "did the effect occur" answerable without the implementation's own records. A harder incident set (no downstream export, or conflicting records) is needed to test DF's reconstruction value.

## Why "narrow" rather than "continue" or "stop"

- **Not continue:** under equal requirements, DF showed no measured advantage in correctness, build effort, maintenance effort or investigation. It cost about 9× in execution time and needed 8 workarounds and 7 core-change requests for ordinary needs: per-call caller identity, structured refusal reasons, a configurable approval lifetime, returning the evidence used, key-order-preserving signing, and legacy-pack reconciliation. The repository's own product-direction.md says that if the baseline is equally easy to use and investigate, DF should stay a tested reference implementation without claiming teams should migrate.
- **Not stop:** the core lifecycle claims largely verified (binding, recovery without re-dispatch, multi-process claims). The defects found are medium and fixable. The conformance idea has value as a checklist independent of the runtime.
- **What would change the call** (proposed only after the evaluation, not implemented): a fresh task with a less prescriptive spec, several integrations sharing one runtime, incidents without a downstream export, and ideally human participants. Fix DF-01, DF-02, DF-04 and DF-09 first, and label that run separately.

## Protocol deviations and limitations (full list in `log/setup.md`)

1. The original repo had no commits at start, so an isolated snapshot copy was used instead of a worktree. Later, the owner made the first commit to the original repo at 14:03:39Z, during Phase 1. No evaluation agent touched the original repo (0 references in all subagent transcripts), and all 337 snapshot files still match it.
2. Filesystem separation was not enforced (same OS user). Held-out tests, the review and the answer key lived outside the evaluation tree during building, and a post-hoc audit of every builder tool call found no access to them. They were withheld, not access-controlled.
3. Prompt asymmetry: the baseline builder prompt added "build it as a competent engineer would…; do not cut corners", and the framework prompt added "do not modify the framework; record workarounds".
4. The framework builder was interrupted by an API spend limit and resumed once (see ²). Its self-reported timestamps before the interruption were estimates later than the real transcript times; only transcript timestamps are used.
5. Token metrics are incomplete and of undocumented semantics. Setup/implementation/debug splits are only partly available.
6. Investigators could not run either implementation's operator CLI, because both import the harness package, which was not in `_implementation/`. The gap is symmetric; both read the SQLite state directly.
7. Dependencies were installed from the public package index during setup.
