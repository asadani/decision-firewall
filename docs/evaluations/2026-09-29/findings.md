# Decision Firewall: independent review (role A)

Snapshot: `df-eval-20260929/source`. All file references are relative to it. Date 2026-09-29. Windows 11, Python 3.12.14.
This is a local review with simulated effects only. It does not establish production security.

## Tool results

- **pytest**: `cd review/work && PYTHONPATH=review/work/src C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe -m pytest -q -p no:cacheprovider` -> 274 passed, 1 skipped (opentelemetry not installed), 1 warning (Starlette/httpx deprecation), exit 0, ~30 s
- **ruff_check**: `C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe -m ruff check src tests scripts examples` -> All checks passed! exit 0
- **ruff_format**: `C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe -m ruff format --check src tests scripts examples` -> 83 files already formatted, exit 0
- **mypy**: `C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe -m mypy src/decision_firewall` -> Success: no issues found in 50 source files, exit 0
- **note**: Installed site-packages decision_firewall was diffed against the snapshot src and is identical; tests ran with PYTHONPATH pointing at the copied src.
- **mutation_testing**: review/mutation.txt: 9 hand-written mutants of core/runtime.py; 3 killed, 6 survived (DF-04)
- **reference_conformance**: deployments 17/17 PASS; access 16 PASS, 1 UNSUPPORTED

## Counts by category

- confirmed_defect: 4
- design_limitation: 12
- documentation_problem: 3
- unverified_concern: 2

## Findings

### DF-01 Approval binds to evidence resolved at review time, not to the evaluation the reviewer inspected
- Category: **confirmed_defect**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:370-394`, `src/decision_firewall/core/runtime.py:380`, `src/decision_firewall/core/runtime.py:389`, `docs/threat-model.md:7`
- Reproduction: `repros/r02_review_binds_unseen_evidence.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r02_review_binds_unseen_evidence.py`
  - Observed:
    - `reviewer inspects evaluation ... evidence: {... 'note': 'customer in good standing' ... 'record': '1'}`
    - `approval applied to evidence: {... 'note': 'customer flagged for chargeback abuse' ... 'record': '2'}`
    - `disposition: ALLOW_WITH_CONSTRAINTS permit: True`
    - `execute -> SUCCEEDED`
- Impact: review(rid, Review, revision=n) takes no evaluation id or evidence hash. It re-resolves evidence inside the review transaction and stores that hash as the approval binding. If trusted facts change between the REQUIRE_REVIEW evaluation the reviewer looked at and the approve call, the approval is silently attached to facts the reviewer never saw. Mandatory rules are re-run, so hard constraints still hold. The discretionary facts that review exists to judge are not protected. Evidence changes after approval are handled correctly (the permit and approval are invalidated).

### DF-02 Rejection is not durable: an older approval is resurrected when the rejecting reviewer's generation changes
- Category: **confirmed_defect**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:250-261`
- Reproduction: `repros/r03_rejection_not_sticky.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r03_rejection_not_sticky.py`
  - Observed:
    - `A approves at evidence v1 -> ALLOW_WITH_CONSTRAINTS`
    - `evidence -> v2, evaluate -> REQUIRE_REVIEW`
    - `bob rejects at v2 -> DENY`
    - `evidence back to v1, evaluate -> REQUIRE_REVIEW`
    - `bob deactivated, evaluate -> ALLOW_WITH_CONSTRAINTS permit: True`
    - `execute -> SUCCEEDED`
- Impact: _context filters approvals by reviewer active/generation before taking the latest (ORDER BY id DESC LIMIT 1 over currently valid reviewers). It then checks evidence/expiry only on that row. Two effects follow. A reject is lost as soon as evidence differs from the hash it was bound to (DENY becomes REQUIRE_REVIEW). If the rejecting reviewer is then deactivated or reconfigured, an earlier approval by another reviewer becomes effective again with no new review. Selecting the latest decision regardless of reviewer status, then validating it, would avoid resurrection. The trigger sequence is realistic but requires evidence to return to a previously approved hash.

### DF-03 Revocation is per-token: the requester can re-evaluate and receive a fresh permit from the same approval
- Category: **design_limitation**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:405-415`, `src/decision_firewall/core/runtime.py:276-363`, `src/decision_firewall/core/runtime.py:391`, `docs/framework/api.md:20`, `docs/framework/verification.md:13`, `docs/threat-model.md:15`, `src/decision_firewall/core/conformance.py:338-348`
- Reproduction: `repros/r01_revoke_then_reissue.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r01_revoke_then_reissue.py`
  - Observed:
    - `revoked token execute -> FirewallError Authorization missing, consumed or revoked`
    - `re-evaluate after revoke: ALLOW_WITH_CONSTRAINTS new permit: True`
    - `execute new permit -> SUCCEEDED`
- Impact: revoke() needs the reviewer role and records authorization_revoked, but it leaves the decision, the approval and the request status untouched. evaluate() has no status gate apart from pending executions, so the requester immediately obtains a new permit from the same approval, which stays valid for a hard-coded 3600 s. That lifetime is not configurable per domain and is not part of the manifest. The docs describe revoke as revoking 'an unclaimed permit', which is literally accurate. The threat model and verification table list 'revocation' as a control, and the conformance 'revoked' check only tests the single token. A reviewer cannot durably withdraw consent without a revision or an identity change.

### DF-04 Several claimed core invariants have no test that fails when they are removed (mutation survivors)
- Category: **confirmed_defect**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:487`, `src/decision_firewall/core/runtime.py:533-536`, `src/decision_firewall/core/runtime.py:258-259`, `src/decision_firewall/core/runtime.py:253`, `src/decision_firewall/core/runtime.py:280`, `docs/framework/architecture.md:17`, `tests/test_deployments.py:170-186`
- Reproduction: `mutate.py`, command `C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe review/mutate.py review C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe  (mutates a copy in review/mut, runs full pytest per mutant)`
  - Observed:
    - `M1 skip dispatch-time revalidation       -> SURVIVED | 274 passed`
    - `M2 UNKNOWN claims not counted            -> KILLED`
    - `M3 reconcile ignores fingerprint         -> SURVIVED | 274 passed`
    - `M4 permit expiry ignored                 -> KILLED`
    - `M5 approval evidence binding ignored     -> SURVIVED | 274 passed`
    - `M6 approval expiry ignored               -> SURVIVED | 274 passed`
    - `M7 evaluate skips pending check          -> SURVIVED | 274 passed`
    - `M8 revoke() is a no-op                   -> KILLED`
    - `M9 approval generation ignored           -> SURVIVED | 274 passed`
- Impact: The core suite still passes (274) after removing any one of these: the second validation immediately before dispatch (architecture.md:17 highlights it), the reconcile fingerprint guard, approval-to-evidence binding, approval expiry, reviewer-generation binding on approvals, and evaluate's refusal while an execution is unresolved. The deployments test for 'change after runtime revalidation' passes because the downstream simulator catches the change, not core. A regression in any of these would ship green. The behaviours are present today (verified independently in r13 and by code reading), but the test suite does not protect them.

### DF-05 Adapter-supplied detail with an integer outside the IEEE-754 safe range wedges an effected attempt in RESERVED
- Category: **confirmed_defect**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:492-502`, `src/decision_firewall/core/runtime.py:504-520`, `src/decision_firewall/core/runtime.py:537-543`, `src/decision_firewall/core/audit.py:15-20`, `src/decision_firewall/core/audit.py:92-107`, `src/decision_firewall/core/contracts.py:103-105`
- Reproduction: `repros/r10_adapter_large_int_detail.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r10_adapter_large_int_detail.py`
  - Observed:
    - `execute raised IntegerDomainError 1152921504606846983 exceeds safe integer domain for JSON floats`
    - `effects performed: 1 | request status: ALLOW_WITH_CONSTRAINTS | permit: RESERVED`
    - `reconcile #1 raised IntegerDomainError ...`
    - `reconcile #2 raised IntegerDomainError ...`
- Impact: ExecutionResult.detail accepts any JsonValue, including 64-bit integers such as provider ids. _finish then hashes the event with RFC 8785 canonicalisation, which rejects integers above 2^53. That exception is raised after the adapter call and outside the try/except that maps adapter errors to UNKNOWN, so the whole transaction rolls back after the effect happened. The permit stays RESERVED, which is safe because nothing re-dispatches. Every reconcile() fails the same way, though, so the attempt can never be resolved, the reservation is held forever, and the request is blocked from revise/evaluate. There is no operator override (see DF-10). The fix is local: validate or sanitise the adapter result before _finish, or store non-canonical detail separately. Unverified: evidence facts containing such integers would make every evaluation an EVALUATION_ERROR (fail-closed but unusable).

### DF-06 Signed audit chain gives no integrity against anyone who can write the runtime directory; tail truncation is invisible to investigate()
- Category: **design_limitation**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/audit.py:36-45`, `src/decision_firewall/core/audit.py:109-117`, `src/decision_firewall/core/audit.py:120-136`, `src/decision_firewall/core/investigation.py:134-151`, `docs/framework/release-tools.md:56`, `docs/framework/release-tools.md:70`, `docs/threat-model.md:26`
- Reproduction: `repros/r06_audit_truncation_and_resign.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r06_audit_truncation_and_resign.py`
  - Observed:
    - `(a) outcome: UNKNOWN | unresolved before: ['permit_...']`
    - `after deleting last 2 events: verify_receipt = True`
    - `investigate: audit_verified= True status= ALLOW_WITH_CONSTRAINTS unresolved= [] gaps= []`
    - `next_step: No unresolved execution recorded in this snapshot`
    - `simulated ledger still has effect: [('attempt_...', 'SUCCEEDED')]`
    - `(b) files in home: ['demo-effects.db', 'governance.db', 'signing.key']`
    - `rewritten chain verifies with pinned key: True`
    - `investigate now says status: OPEN unresolved: []`
- Impact: The Ed25519 key is a raw file next to governance.db, and the permit and audit signatures use the same key. receipt() signs a fresh checkpoint over whatever rows exist, so deleting trailing events yields a receipt that verifies under the pinned key. Anyone who can read the directory can also re-sign a rewritten history. After truncation, investigate() reports an effected, uncertain execution as 'No unresolved execution recorded' with audit_verified=True. The docs acknowledge that truncation before a trusted checkpoint and a compromised host are out of scope. Even so, the product has no mechanism to export or pin checkpoints externally, and the reassuring next_step text overstates what was established. The live runtime tables were not affected in (a); only the offline report was misled.

### DF-07 Authorization decisions read unsigned projection tables; investigate() does not flag a permit whose approval has no review event
- Category: **design_limitation**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:250-270`, `src/decision_firewall/core/investigation.py:87-109`, `docs/framework/release-tools.md:70`, `src/decision_firewall/core/runtime.py:56-57`
- Reproduction: `repros/r07_state_tables_unsigned.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r07_state_tables_unsigned.py`
  - Observed:
    - `evaluate: REQUIRE_REVIEW`
    - `after direct DB insert: disposition ALLOW_WITH_CONSTRAINTS permit: True`
    - `execute -> SUCCEEDED`
    - `investigate reviews: [] | approval_id on permit: 1 | gaps: []`
- Impact: Approvals, identities, permits and reservations are plain SQLite rows. A buggy adapter or plugin (which runs with host privileges and can open the same file) or a local actor can grant authority with no review_recorded event. The chain then records an authorization_issued event carrying an approval_id that matches no review in the chain, and investigate() reports no gap even though it could detect this from the receipt alone. The docs say the report does not invent a stronger approval link. The consequence is that the investigation cannot answer 'who approved this' reliably.

### DF-08 Role separation is nominal: one caller can act as requester, reviewer and executor; the CLI has no identity option
- Category: **design_limitation**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/contracts.py:108-115`, `src/decision_firewall/core/runtime.py:98-115`, `src/decision_firewall/core/audit.py:59-65`, `src/decision_firewall/framework_cli.py:19-44`, `src/decision_firewall/framework_cli.py:115-123`, `docs/framework/api.md:28`, `docs/threat-model.md:26`
- Reproduction: `repros/r12_cli_single_user_all_roles.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r12_cli_single_user_all_roles.py`
  - Observed:
    - `evaluate -> REQUIRE_REVIEW`
    - `same user review approve -> ALLOW_WITH_CONSTRAINTS | token printed to stdout: True`
    - `same user execute -> SUCCEEDED`
    - `recorded actors: ['requester', 'reviewer']`
- Impact: Each identity name has exactly one role, so the same name cannot request and review. Beyond that, identities are strings chosen by whoever constructs DecisionFirewall. All four roles are pre-seeded active. configure_identity() has no administrative check, so any holder of the object can create reviewers or reactivate executors. The generic CLI always uses the default identities. Self-approval is prevented only by deployment-level process and OS separation. This is documented as a local demonstration, but 'review' in audit records should not be read as independent approval.

### DF-09 Adapter I/O and evidence resolution run while holding the global SQLite write lock; all operations, including reads, serialize behind them
- Category: **design_limitation**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:481-502`, `src/decision_firewall/core/audit.py:23-28`, `src/decision_firewall/core/audit.py:67-78`, `src/decision_firewall/core/audit.py:109-111`, `src/decision_firewall/core/runtime.py:573-598`, `src/decision_firewall/core/runtime.py:56`
- Reproduction: `repros/r08_dispatch_holds_global_lock.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r08_dispatch_holds_global_lock.py`
  - Observed:
    - `detail(unrelated request)  started 0.3s into a 2.0s dispatch, waited 1.75s`
    - `receipt()                  started 0.3s into a 2.0s dispatch, waited 1.84s`
    - `submit(new request)        started 0.3s into a 2.0s dispatch, waited 1.76s`
- Impact: Correctness relies on BEGIN IMMEDIATE around dispatch. Serialized dispatch is documented, but the cost is wider than stated. Every transaction, including detail() and receipt(), opens BEGIN IMMEDIATE, so a slow adapter or resolver stalls the whole home across domains and processes. Waiters fail with 'database is locked' after the fixed 30 s busy timeout. This fits a local demo. It is a throughput and availability ceiling for any remote adapter, and a single hung adapter call blocks reconciliation of everything else.

### DF-10 No operator path to resolve an UNKNOWN/RESERVED attempt when the adapter cannot give an authoritative answer
- Category: **design_limitation**. Severity: **medium**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:522-543`, `src/decision_firewall/core/runtime.py:185-191`, `src/decision_firewall/core/runtime.py:458-480`, `docs/framework/executors.md:11`, `docs/framework/release-tools.md:41`
- Reproduction: none (code reading; see also r09 and r10 for two ways an attempt becomes stuck)
- Impact: reconcile() only relays the adapter's answer, and outcome() only appends a note. RESERVED is committed before the adapter is called, so a crash before the call is indistinguishable from a crash during it. For a queued or remote adapter that correctly returns UNKNOWN when it cannot prove absence (as executors.md requires), a crash before dispatch leaves the request, and any claims it holds, blocked indefinitely. No audited manual resolution or 'abandon with evidence' operation exists. Preserving uncertainty is a stated goal, but without an escape hatch operators will edit the DB directly, which the audit chain does not capture (DF-07).

### DF-11 Any policy-only upgrade strands unresolved attempts; only one pack version per domain name can be registered
- Category: **design_limitation**. Severity: **low**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:69-71`, `src/decision_firewall/core/runtime.py:530-536`, `src/decision_firewall/core/plugins.py:49-72`, `docs/framework/architecture.md:17`
- Reproduction: `repros/r09_reconcile_blocked_after_policy_change.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r09_reconcile_blocked_after_policy_change.py`
  - Observed:
    - `execute -> UNKNOWN`
    - `reconcile -> FirewallError Restore the original domain/adapter version for reconciliation`
    - `evaluate -> FirewallError Inspect or reconcile the existing execution first`
    - `revise -> FirewallError Inspect or reconcile the existing execution first`
    - `with original pack restored: reconcile -> SUCCEEDED`
- Impact: The reconcile guard compares the whole domain fingerprint (policy config, rules, schema, versions), not just the executor identity/version. Bumping a policy threshold therefore blocks reconciliation of old attempts. Because domains are keyed by name, a runtime cannot host the old pack for reconciliation and the new pack for new work at the same time. This is documented, but it makes routine policy rollouts operationally costly whenever UNKNOWN outcomes exist.

### DF-12 No cross-request deduplication: an identical resubmission while the first attempt is UNKNOWN dispatches again with a new key
- Category: **design_limitation**. Severity: **low**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:144-176`, `src/decision_firewall/core/runtime.py:458`, `docs/framework/deployment-example.md:40`
- Reproduction: `repros/r11_duplicate_request_no_dedup.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r11_duplicate_request_no_dedup.py`
  - Observed:
    - `request 1 -> UNKNOWN`
    - `identical request 2 -> UNKNOWN`
    - `ledger: [('attempt_...', 'SUCCEEDED'), ('attempt_...', 'SUCCEEDED')]`
- Impact: Idempotency is per request and attempt. The typical agent failure, retrying a timed-out submission as a new request, is only caught if the domain defines a resource claim or the downstream system deduplicates on business keys. The deployment example acknowledges this. The core contract should state it prominently next to the 'repeated execution cannot duplicate effects' claim.

### DF-13 Unavailable assessment returns REQUIRE_REVIEW that no review can satisfy
- Category: **documentation_problem**. Severity: **low**. Confidence: high
- References: `src/decision_firewall/core/policy.py:22-23`, `src/decision_firewall/core/runtime.py:370-403`, `docs/framework/build-a-domain.md:8`, `docs/framework/rules.md:17`
- Reproduction: `repros/r04_unavailable_assessment_dead_end.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r04_unavailable_assessment_dead_end.py`
  - Observed:
    - `evaluate: {... 'disposition': 'REQUIRE_REVIEW', 'reasons': ['assessment_unavailable'] ...}`
    - `after approval #1: REQUIRE_REVIEW ['assessment_unavailable'] permit: False`
    - `after approval #2: REQUIRE_REVIEW ['assessment_unavailable'] permit: False`
- Impact: The assessment_unavailable check runs before the review is consulted, so review() accepts and records approvals that can never take effect. The only way forward is revise() with a new assessment. build-a-domain.md says unavailable assessments 'cannot automatically authorize', which implies a manual path exists. rules.md does say the prerequisite 'remains in force'. Reviewers get a misleading disposition, and the audit log fills with ineffective approvals. The same holds for mandatory RuleSet rules that return status 'review' (e.g. refunds assessment_available).

### DF-14 Signing key is silently regenerated if missing; no rotation event; chmod(0o600) is ineffective on Windows
- Category: **design_limitation**. Severity: **low**. Confidence: high
- References: `src/decision_firewall/core/audit.py:36-45`
- Reproduction: `repros/r14_key_loss_silent_regeneration.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r14_key_loss_silent_regeneration.py`
  - Observed:
    - `key mode bits after chmod(0o600): 0o666 on nt`
    - `new key generated silently: True`
    - `old key -> InvalidSignature`
    - `new key -> InvalidSignature`
    - `event kinds (no key-rotation event): ['proposal_submitted', 'policy_evaluated', 'authorization_issued']`
- Impact: Restoring governance.db without signing.key, or deleting the key, produces no error. New events are signed with a new key, outstanding permits become invalid, and the receipt no longer verifies under any single key. There is no rotation or key-id support. On Windows the key file keeps inherited ACLs.

### DF-15 CLI examples use the receipt's adjacent .pub as the 'trusted' key and print bearer permits to stdout
- Category: **documentation_problem**. Severity: **low**. Confidence: high
- References: `src/decision_firewall/framework_cli.py:107-112`, `src/decision_firewall/framework_cli.py:146-156`, `docs/framework/release-tools.md:51`, `docs/framework/release-tools.md:56`, `docs/framework/api.md:39`
- Reproduction: `repros/r12_cli_single_user_all_roles.py`, command `cd review/repros && C:/Users/anuj_/gitrepo/claude-runs/df-eval-20260929/env/venv-framework/Scripts/python.exe r12_cli_single_user_all_roles.py`
  - Observed:
    - `same user review approve -> ... token printed to stdout: True`
- Impact: `firewall ... receipt receipt.json` writes receipt.pub from the same local key next to the receipt, and the documented investigate/verify commands consume that adjacent file. Line 56 of the same guide warns this provides no independent assurance. The CLI evaluate/review commands echo the full signed permit to stdout even with --save, which puts bearer authority into terminal logs and CI logs.

### DF-16 Domain fingerprint is self-declared metadata; code changes under unchanged version strings are not detected
- Category: **design_limitation**. Severity: **info**. Confidence: high
- References: `src/decision_firewall/core/plugins.py:49-72`, `docs/framework/architecture.md:25`
- Reproduction: none (code reading; documented)
- Impact: The manifest covers names, version strings, config, JSON schema and rule metadata. It does not cover policy, resolver or executor code. Replay 'matches' and the reconcile guard both assume developers bump versions. A different adapter with the same name/version passes the reconcile guard. This is documented ('not code attestation'), and it limits what the permit's 'adapter version binding' establishes.

### DF-17 Legacy v0.1 refund engine duplicates the security-critical lifecycle with weaker checks
- Category: **design_limitation**. Severity: **low**. Confidence: medium
- References: `src/decision_firewall/domains/refunds/engine.py:117-160`, `src/decision_firewall/domains/refunds/engine.py:227-259`, `src/decision_firewall/domains/refunds/engine.py:261-270`, `docs/framework/full-review-2026-09-28.md:16-22`
- Reproduction: none (code reading; legacy engine not reviewed in depth)
- Impact: The compatibility Firewall reimplements evaluate/review/revoke/execute over separate tables. revoke() performs no role check. review()/submit() take the actor name as a caller argument. The approval-selection pattern of DF-02 is repeated. The 2026-09-28 self-review found a revalidation gap that existed only in this copy. Two lifecycles must be kept in lockstep, and fixes to core do not flow into the legacy one.

### DF-18 Public execute() exposes a crash-injection test hook
- Category: **design_limitation**. Severity: **info**. Confidence: high
- References: `src/decision_firewall/core/runtime.py:448`, `src/decision_firewall/core/runtime.py:479-480`
- Reproduction: none
- Impact: execute(token, crash_after_reserve=True) is part of the production signature. It is harmless (the attempt stays RESERVED and reconciles), but it is test scaffolding in the public API.

### DF-19 Reported test count not reproduced
- Category: **documentation_problem**. Severity: **info**. Confidence: medium
- References: `docs/framework/release-tools.md:74`
- Reproduction: `none`, command `python -m pytest -q (in review/work)`
  - Observed:
    - `274 passed, 1 skipped, 1 warning`
- Impact: The doc states 276 tests passed. This snapshot collects 275: 274 pass and 1 is skipped because optional opentelemetry is not installed. The difference is small but unexplained.

### DF-20 Offline evaluation isolation depends on policy callables being pure
- Category: **unverified_concern**. Severity: **low**. Confidence: medium
- References: `src/decision_firewall/experiments.py:72-89`, `tests/test_workbench.py:274-296`
- Reproduction: none
- Impact: EvaluationPolicy drops the resolver and executor references but passes domain.evaluate, an arbitrary closure or object, straight through. The included packs' policies are pure, and the test confirms the pack's own resolve/executor are never called. Nothing prevents a policy closure that captures a client from causing effects during experiments or replay. This is a convention, not an enforced isolation boundary. No such leak was found in the shipped packs.

### DF-21 Multi-instance behaviour beyond one host's local filesystem is untested
- Category: **unverified_concern**. Severity: **low**. Confidence: low
- References: `src/decision_firewall/core/audit.py:23-28`, `docs/framework/product-direction.md:25`
- Reproduction: partial: repros/r05_multiprocess_claims.py shows correct capacity-1 behaviour across 8 local processes
- Impact: Resource and permit exclusivity rely entirely on SQLite file locking (rollback journal, synchronous=FULL). Correctness on network or synced filesystems, containers sharing a volume, or hosts with divergent clocks was not tested. Each instance uses its own clock for expiry. The docs disclaim distributed coordination.

## Domain-neutrality assessment

Core (src/decision_firewall/core) is domain-neutral in code. It contains no refund, payment, amount or access vocabulary, and a test enforces the import boundary. Generic primitives cover the lifecycle cleanly: Proposal/Evidence/Decision/Claim/ExecutionResult, a DomainPack of schema, resolver, policy and executor, and integer resource claims. The deployments pack shows a third domain with no core changes. Some model-centric residue remains. Every submission needs an Assessment (provider/model/revision) and a non-empty message, even for deterministic or human-originated actions, and core applies an assessment_unavailable rule before domain policy. That is mild ceremony for non-model integrations. The runtime is small (~600 lines) and its binding, revalidation and reservation logic delivers real value an integrator would otherwise hand-roll (r13). Optional layers (preparation, RuleSet, history/experiments, observation) add surface without being required. The legacy v0.1 engine duplicates the lifecycle (DF-17). Adapters still carry most of the hard safety work: durable idempotency keyed on the attempt, conflicting-payload rejection, authoritative reconciliation that returns UNKNOWN unless absence is provable, and last-mile atomic invariant checks, because evidence can change after the core resolves it. Deployments must provide real authentication and role separation (DF-08), protection and external pinning of signing keys and checkpoints (DF-06, DF-14), prevention of alternate execution paths, business-level deduplication (DF-12), and an operator process for stuck uncertain attempts (DF-10).

## Claims verified as true

- Core does not import domain packages, model SDKs or web tooling. Evidence: tests/test_framework.py core-import test passes; grep of src/decision_firewall/core finds no refund/access/payment vocabulary or domain imports
- Permit binds revision, proposal, assessment, evidence, domain fingerprint, approval, requester/executor generations and expiry; each change blocks dispatch. Evidence: repros/r13 checks 1-8 PASS; runtime.py:339-363, 417-445
- Evidence is re-resolved at reservation and again immediately before dispatch; change in the gap yields FAILED before dispatch with no effect. Evidence: repros/r13 'evidence change between reservation and dispatch' PASS (resolver called 3 times)
- Adapter exceptions and lost responses become UNKNOWN; reservations are held; restart + reconcile uses the original attempt key and never re-dispatches. Evidence: repros/r13 response-loss checks PASS; tests/test_framework.py adapter outcome tests pass; runtime.py:497-501, 537-543
- A reserved/consumed permit cannot be executed twice. Evidence: repros/r13 'second execute of reserved permit refused' PASS
- Capacity claims hold under concurrency, including 8 OS processes on one home. Evidence: repros/r05 modes A and B: exactly 1 ledger effect; existing thread test in tests/test_framework.py
- FAILED releases reservations; UNKNOWN retains them; retain_on_success counted. Evidence: repros/r13; runtime.py:240-249
- Replay uses the stored snapshot without calling resolver or executor and refuses a different fingerprint. Evidence: repros/r13 replay check PASS; tests/test_framework.py test_non_financial_lifecycle
- Offline experiments never resolve evidence or execute (for shipped packs). Evidence: tests/test_workbench.py:274 passes
- Approval cannot waive mandatory RuleSet rules; review-kind rules cannot deny. Evidence: core/rules.py:70-85; tests + conformance 'review_cannot_override' PASS
- Audit write failure after a downstream effect leaves the attempt RESERVED and reconcilable. Evidence: tests/test_framework.py test_crash_before_dispatch_and_after_effect passes
- verify_receipt rejects edited events / wrong key when the verifier lacks the private key. Evidence: tests/test_release_tools.py test_investigation_refuses_tampered_receipt_or_wrong_key passes
- Reference conformance: deployments 17/17 PASS; access 16 PASS + 1 UNSUPPORTED (resource_contention). Evidence: review/conformance.txt
- pytest, ruff check, ruff format --check and mypy all pass. Evidence: review/pytest.txt, ruff.txt, ruff_format.txt, mypy.txt

## Not checked

- Linux/macOS behaviour; everything was run on Windows 11 with Python 3.12.14.
- Real (non-simulated) adapters, remote queues, payment/IAM/deployment systems; all effects were local SQLite simulators.
- SQLite on network/shared filesystems, containers sharing volumes, multi-host clocks.
- OpenTelemetry export (package not installed; the telemetry test was skipped), web inspector/browser flows, CSRF/origin handling.
- Model adapters, Laya/OpenRouter paths, and all benchmark numbers in docs/benchmarks (not rerun; treated as unverified claims).
- python -m build / wheel installation (not run).
- The v0.1 legacy refund engine, history import, retrieval and preparation beyond what the existing tests exercise.
- Crash durability at the OS/power-loss level (synchronous=FULL was not fault-injected); only in-process crash simulation.
- Performance and throughput characteristics beyond the 2 s lock-blocking demonstration.
- Whether Windows ACLs on a real deployment directory expose signing.key to other accounts (only the chmod no-op was observed).

## Notes on prior self-reports

- docs/framework/full-review-2026-09-28.md and docs/benchmarks/* were treated as claims. The conformance counts and lint/type results reproduce. The test count differs by one (DF-19). The benchmark figures were not rerun.
- The self-review describes itself as 'by the implementing assistant'. It did not report DF-01 to DF-05, and its fixes were not protected by core tests in the cases listed in DF-04.
