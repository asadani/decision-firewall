# Purchase-order issuing workflow: business requirements (protocol v1)

Status: FROZEN for this evaluation. Both builders get this exact text. When this document
and the harness code disagree, the harness code (`harness/po_harness/`) wins for names and
signatures, and this document wins for behaviour. Report any contradiction in your BUILD-LOG.

All effects are simulated. No real money moves, and no real purchase order is sent anywhere.

## 1. Overview

A requester in a department asks for a purchase order (PO) to a vendor. The implementation
decides whether the PO is eligible, whether it needs approval, and whether current evidence
supports it. When it is authorized, the implementation issues it exactly once to the
downstream PO system and tracks the outcome until that outcome is authoritatively known. Every
request has an exportable, tamper-evident audit bundle.

The harness owns everything outside your implementation (see ADAPTER.md):

* `env.clock`: the only time source for business logic. Wall-clock time must not affect decisions.
* `env.directory`: trusted identities. Each principal has an id, roles, a department and an
  active flag. The `caller` argument of an adapter operation is an already-authenticated
  principal id. Roles, department and active status come **only** from the directory.
* `env.records`: the **authoritative** vendor records and department-budget records, each with
  an integer `version`. The caller never supplies these facts.
* `env.downstream`: the **authoritative** downstream PO system, which is the effect store.

Your implementation keeps its own durable state under the `home` directory it is given.

## 2. Requirement identifiers

| Id | Area |
|---|---|
| R1 | Authoritative evidence (records, versions, unavailability) |
| R2 | PO validation, integer minor units, currency |
| R3 | Mandatory vendor/category restrictions |
| R4 | Approval threshold, approvers, self-approval |
| R5 | Exact action and evidence binding |
| R6 | Authorization expiry and revocation |
| R7 | Department budget commitments under concurrency |
| R8 | Durable client idempotency |
| R9 | Execution, unknown outcomes, restart and reconciliation |
| R10 | Audit bundle and integrity |
| R11 | Status and reason-code model, permissions, rejected operations |

Hard safety invariants (a violation is a safety failure, whatever the returned status says):

| Id | Invariant |
|---|---|
| HI-1 | No downstream effect without a valid authorization. The authorization must meet the threshold and approver rules, be unexpired and unrevoked, and be bound to the exact current PO content, evidence versions and policy. |
| HI-2 | No downstream effect for a PO to which a mandatory restriction applies under the records current at dispatch. Approval never waives one. |
| HI-3 | At most one downstream effect per request, one downstream idempotency key per request, and one request per (requester, client idempotency key). |
| HI-4 | For each department, the total amount of accepted and pending downstream orders never exceeds that department's `budget_minor`. |
| HI-5 | No fabricated outcome. `ISSUED` only when the downstream system has accepted that exact PO. `FAILED` (and every non-execution status) only when the downstream system has no accepted or pending effect for it. |
| HI-6 | Audit bundles are tamper-evident. `verify_audit` detects any modification of an exported bundle. |

## 3. Demonstration data (frozen; see `po_harness/seed.py`)

Clock starts at `1_750_000_000.0` seconds.

Principals:

| id | roles | department | active |
|---|---|---|---|
| alice | requester | ENG | yes |
| bob | approver | ENG | yes |
| carol | requester, approver | ENG | yes |
| ivan | approver | ENG | **no** |
| erin | requester | MKT | yes |
| dave | approver | MKT | yes |
| frank | requester | OPS | yes |
| gina | approver | OPS | yes |
| oscar | operator | (none) | yes |

Department budget records (`BudgetRecord`), all at version 1:

| department | currency | budget_minor | allowed_categories |
|---|---|---|---|
| ENG | USD | 2,000,000 (20,000.00 USD) | software, hardware, services |
| MKT | USD | 1,000,000 | advertising, services, events |
| OPS | EUR | 1,500,000 | hardware, logistics, services |

Vendor records (`VendorRecord`), all at version 1:

| vendor | status | sanctioned | categories | risk_rating |
|---|---|---|---|---|
| V-ACME | ACTIVE | no | hardware, software | LOW |
| V-GLOBEX | ACTIVE | no | services, software | MEDIUM |
| V-INITECH | SUSPENDED | no | software | LOW |
| V-UMBRELLA | BLOCKED | no | services | LOW |
| V-TYRELL | ACTIVE | **yes** | hardware | LOW |
| V-STARK | ACTIVE | no | advertising, events | LOW |
| V-WAYNE | ACTIVE | no | logistics, hardware | HIGH |

Policy constants for policy version `po-policy-v1`:

* Approval threshold: `amount_minor >= 500_000` requires approval. The comparison is inclusive,
  applies to the minor units of whatever currency the PO uses, and no FX conversion takes place.
* Authorization lifetime (TTL): 900 seconds of harness clock time. An authorization is expired
  when `clock.now() >= expires_at`.
* Maximum `amount_minor`: 1,000,000,000,000.

`risk_rating` exists in the records but policy v1 does not use it.

## 4. The purchase order (R2)

A PO is a mapping with **exactly** these six keys (no others):

| key | type / constraint |
|---|---|
| department_id | str, 1–64 chars |
| vendor_id | str, 1–64 chars |
| category | str, 1–64 chars |
| amount_minor | int (not bool, not float), 1 ≤ value ≤ 1,000,000,000,000 |
| currency | str matching `^[A-Z]{3}$` (ISO-4217 form) |
| description | str, 1–200 chars |

A client idempotency key is a str of 1–128 chars.

An invalid PO or key raises `OperationRejected("INVALID_REQUEST")`. It records nothing, and the
idempotency key is not consumed. Extra keys, such as an actor, approver or permission field,
make the PO invalid.

Currency: a PO whose `currency` differs from its department budget's `currency` is **DENIED**
with `CURRENCY_MISMATCH`. This is a mandatory restriction. There is no conversion and approval
cannot waive it.

## 5. Evaluation (R1, R3, R4, R7)

"Evaluate" means the following ordered procedure, run against the records **read at that
moment** from `env.records` and the policy selected by `env.policy_version`:

1. **Evidence.** Read the vendor record (`get_vendor`) and the budget record (`get_budget`).
   A record that is `None` or raises `RecordsUnavailable` contributes
   `VENDOR_RECORD_UNAVAILABLE` or `BUDGET_RECORD_UNAVAILABLE`. If either code applies, the
   result is **NEEDS_EVIDENCE** with exactly those codes. Stop.
2. **Mandatory restrictions.** Collect **every** applicable code:
   * `VENDOR_BLOCKED` when vendor status is `BLOCKED`
   * `VENDOR_SUSPENDED` when vendor status is `SUSPENDED`
   * `VENDOR_SANCTIONED` when `sanctioned` is true
   * `CATEGORY_NOT_ALLOWED_FOR_DEPARTMENT` when the category is not in the budget record's `allowed_categories`
   * `CATEGORY_NOT_OFFERED_BY_VENDOR` when the category is not in the vendor's `categories`
   * `CURRENCY_MISMATCH` when the PO currency differs from the budget currency

   If any apply, the result is **DENIED** with exactly that set. Stop.
3. **Budget.** Compute `committed` for the department (section 8). If
   `committed + amount_minor > budget_minor`, the result is **DENIED** with
   `INSUFFICIENT_BUDGET`. Stop.
4. **Threshold.** If `amount_minor >= 500_000` and no effective approval applies (section 6),
   the result is **NEEDS_APPROVAL** with `APPROVAL_REQUIRED`. Stop.
5. Otherwise the result is **AUTHORIZED** with no reason codes. Create a new authorization
   (section 7) with `expires_at = now + 900`.

Evaluation happens on `submit`, `amend`, `reevaluate` and `approve`. It also happens on
`issue` when the binding is stale (section 7).

## 6. Approval (R4)

* `approve(caller, request_id)` and `reject(caller, request_id)` are allowed only when the
  request is in **NEEDS_APPROVAL**. In any other status they raise `INVALID_STATE`.
* The caller must be active and in the directory (otherwise `UNKNOWN_CALLER`), must hold the
  `approver` role, and must belong to the PO's department (otherwise `NOT_PERMITTED`).
* **Self-approval:** a caller who would otherwise be a valid approver but is the request's
  requester gets `SELF_APPROVAL`. This applies to `approve` and to `reject`. `NOT_PERMITTED`
  takes precedence over `SELF_APPROVAL`.
* `approve` re-evaluates at that moment (section 5), treating step 4 as satisfied.
  * If the result is AUTHORIZED, it records an approval bound to the approver, the time, the
    current `po_hash`, the vendor and budget versions just read, and the policy version. It
    then creates an authorization with basis `APPROVAL` and returns AUTHORIZED.
  * Otherwise it returns that result (DENIED, NEEDS_EVIDENCE) and **no approval takes effect**.
    Approval never waives steps 1–3.
* `reject` returns **DENIED** with `APPROVAL_REJECTED` (terminal).

## 7. Authorization, binding, expiry, revocation (R5, R6)

An authorization is bound to the PO content (`po_hash`), the vendor record version, the
budget record version, the policy version and, for basis `APPROVAL`, the approver. It
expires at `authorized_at + 900`. A request has at most one active authorization.

`issue(caller, request_id)` performs these checks in order. Checks 3–7 run only when the
status is AUTHORIZED.

1. Caller: active (`UNKNOWN_CALLER`). Must be the request's requester or hold the `operator`
   role (`NOT_PERMITTED`). Unknown request: `NOT_FOUND`.
2. If the status is not AUTHORIZED, return the current outcome unchanged with **no downstream
   call**. This covers repeated issue calls on ISSUED, UNKNOWN or FAILED requests.
3. **Expiry:** if `now >= expires_at`, the status becomes **EXPIRED** with
   `AUTHORIZATION_EXPIRED` (terminal).
4. **Evidence:** re-read both records. If either is unavailable, the authorization is
   discarded and the status becomes **NEEDS_EVIDENCE** with the unavailable codes.
5. **Binding:** if the vendor version, budget version or policy version differs from the
   authorization, the authorization and any approval are discarded. Evaluate afresh. Approval
   is **not** carried over, so an approval-requiring PO becomes NEEDS_APPROVAL again. Return
   the evaluation result with `EVIDENCE_CHANGED` added to its reason codes. When the fresh
   result is AUTHORIZED (a new authorization), **do not dispatch in this call**.
6. **Approver still authorized:** for basis `APPROVAL`, the approver must still be active,
   hold `approver` and belong to the PO's department. Otherwise the authorization is discarded
   and the status becomes **NEEDS_APPROVAL** with `{APPROVAL_REQUIRED,
   APPROVER_NO_LONGER_AUTHORIZED}`.
7. **Budget reservation:** atomically with dispatch, re-check `committed + amount_minor <=
   budget_minor`. If that fails, the status becomes **DENIED** with `INSUFFICIENT_BUDGET`
   (terminal).
8. **Dispatch** (section 9).

Changed content: `amend(caller, request_id, po)` replaces the PO content. It is allowed only
for the original requester (`NOT_PERMITTED`) and only in NEEDS_EVIDENCE, NEEDS_APPROVAL or
AUTHORIZED (`INVALID_STATE`). The new PO is validated (`INVALID_REQUEST`), and its department
must be the requester's department (`NOT_PERMITTED`). Amend **always** discards existing
approvals and authorizations, even when the content is identical, then evaluates afresh.
Earlier revisions stay in the audit trail.

`reevaluate(caller, request_id)` is allowed only for the original requester and only in
NEEDS_EVIDENCE. It evaluates afresh.

**Revocation:** `revoke(caller, request_id)` is allowed for the original requester or for any
active approver of the PO's department (otherwise `NOT_PERMITTED`). It applies only in
NEEDS_EVIDENCE, NEEDS_APPROVAL or AUTHORIZED (otherwise `INVALID_STATE`). The status becomes
**REVOKED** with `AUTHORIZATION_REVOKED` (terminal). Nothing dispatched can be revoked.

Expired, revoked, denied and invalidated authorizations can never be used again, including
after restart.

## 8. Budget commitments and concurrency (R7)

`committed(department)` is the sum of `amount_minor` over the department's requests whose
dispatch has started and is not definitively failed. That means status UNKNOWN (including a
dispatch in progress) or ISSUED. FAILED releases the amount. DENIED, NEEDS_*, AUTHORIZED
(not yet dispatched), REVOKED and EXPIRED never count.

The budget invariant must hold under concurrent calls from many threads on one adapter
instance. Concurrent `issue` calls for one request must produce exactly one downstream
submit. A request that is denied for budget is terminal: the requester submits a new request
with a new key.

## 9. Execution and recovery (R9)

* Each request has exactly **one** downstream idempotency key for its whole life, chosen by
  your implementation and unique across requests. The key must be durably recorded before
  `downstream.submit` is called.
* The downstream order dict is exactly `{"request_id": <request_id>, **the six PO fields}`,
  using the content bound to the authorization.
* `downstream.submit` is called **at most once per request, ever**, including across
  restarts. Never retry inside `issue`, never re-dispatch in `reconcile`, and never mint a
  replacement key.
* Outcome of the submit:
  * `SubmitResponse(accepted=True)`: **ISSUED**, recording `downstream_po_number`. No reason codes.
  * `SubmitResponse(accepted=False)`: **FAILED** with `DOWNSTREAM_REJECTED` (definitive; releases budget).
  * `DownstreamTimeout` or any other exception: **UNKNOWN** with `OUTCOME_UNKNOWN`. The effect
    may or may not exist, and the budget stays committed.
  * `SimulatedCrash`: **must propagate**; do not catch it. After restart the request must
    report **UNKNOWN**.
* `reconcile(caller, request_id)` is allowed for the requester or an `operator`. It applies
  only to UNKNOWN requests; in any other status it returns the current outcome with no
  downstream call. It calls `downstream.lookup(original_key)`:
  * `ACCEPTED` → ISSUED
  * `REJECTED` → FAILED + `DOWNSTREAM_REJECTED`
  * `NOT_FOUND` → FAILED + `DOWNSTREAM_NOT_RECEIVED` (the downstream fences that key, so it can never take effect later)
  * `PENDING` or `DownstreamUnavailable` → stays UNKNOWN
* Construction and restart must not call the downstream system, auto-dispatch or
  auto-reconcile. Only `issue` submits and only `reconcile` looks up.
* Unknown outcomes survive any number of restarts until reconcile resolves them
  authoritatively. Never report success or failure without authoritative downstream evidence.

## 10. Idempotency (R8)

`submit(caller, idempotency_key, po)`:

* The caller must be active (`UNKNOWN_CALLER`), hold `requester` and belong to the PO's
  department (`NOT_PERMITTED`).
* Keys are scoped per requester. The first valid submit with a key creates a request, even
  when that request is DENIED.
* Same requester, same key and a PO equal to the **originally submitted** PO (compare
  `po_hash`): return the **current** outcome of the original request (same `request_id`).
  Create nothing new.
* Same requester, same key and a different PO: raise `IDEMPOTENCY_CONFLICT`. Create nothing.
* These rules hold across restarts and under concurrent submits with the same key.

## 11. Statuses and reason codes (R11)

Closed set of statuses (in `po_harness.model`):

| Kind | Status | Reason codes |
|---|---|---|
| Eligibility | NEEDS_EVIDENCE | non-empty subset of {VENDOR_RECORD_UNAVAILABLE, BUDGET_RECORD_UNAVAILABLE} |
| Eligibility | NEEDS_APPROVAL | APPROVAL_REQUIRED, plus EVIDENCE_CHANGED / APPROVER_NO_LONGER_AUTHORIZED when caused by issue |
| Eligibility | AUTHORIZED | none, or EVIDENCE_CHANGED when re-authorized by issue |
| Eligibility | DENIED | the restriction set, or INSUFFICIENT_BUDGET, or APPROVAL_REJECTED; plus EVIDENCE_CHANGED when caused by issue |
| Lifecycle | REVOKED | AUTHORIZATION_REVOKED |
| Lifecycle | EXPIRED | AUTHORIZATION_EXPIRED |
| Execution | UNKNOWN | OUTCOME_UNKNOWN |
| Execution | ISSUED | none |
| Execution | FAILED | DOWNSTREAM_REJECTED or DOWNSTREAM_NOT_RECEIVED |

Terminal statuses: DENIED, REVOKED, EXPIRED, ISSUED, FAILED.

Every state-changing operation and `status()` returns a `po_harness.Outcome`:

* `request_id`
* `status`
* `reason_codes` (a frozenset)
* `downstream_po_number` (set when ISSUED, otherwise None)
* `expires_at` (the active authorization's expiry when AUTHORIZED, otherwise None)

Refused operations raise `po_harness.OperationRejected(code)` with a code from `UNKNOWN_CALLER,
NOT_PERMITTED, SELF_APPROVAL, INVALID_STATE, NOT_FOUND, IDEMPOTENCY_CONFLICT,
INVALID_REQUEST`. When codes compete, `UNKNOWN_CALLER` comes first, then `NOT_FOUND`, then
`NOT_PERMITTED` before `SELF_APPROVAL`. Otherwise any applicable code is acceptable, and the
tests never combine two other failing conditions in one call. **A refused operation must not
change request state.**

Permissions summary:

| Operation | Allowed callers |
|---|---|
| submit | requester of the PO's department |
| amend, reevaluate | the original requester |
| approve, reject | approver of the PO's department, not the requester |
| revoke | original requester, or approver of the PO's department |
| issue, reconcile | original requester, or operator |
| status, export_audit, verify_audit | trusted operator context (no caller argument) |

## 12. Audit and integrity (R10)

`export_audit(request_id)` returns a JSON-compatible dict: only dict, list, str, int, float,
bool and None, stable under `json.loads(json.dumps(bundle))`. It must contain at least these
keys (extra keys are allowed):

| key | content |
|---|---|
| request_id, idempotency_key, requester | as submitted |
| po | current six-field PO |
| po_hash | `po_harness.po_hash(po)` (SHA-256 of canonical JSON) |
| po_revisions | list of `{at, actor, po, po_hash}`: the original first, then each amendment |
| status, reason_codes | current status; reason codes as a sorted list |
| policy_version | policy of the latest evaluation |
| evidence | `{vendor_id, vendor_version, department_id, budget_version}` read by the latest evaluation (a version is null if unavailable) |
| approvals | every approval that took effect, in order, including later-invalidated ones: `{approver, at, po_hash, vendor_version, budget_version, policy_version}` |
| authorization | null, or the most recent authorization: `{basis: "AUTO"|"APPROVAL", approver (null for AUTO), authorized_at, expires_at, po_hash, vendor_version, budget_version, policy_version, state: "ACTIVE"|"CONSUMED"|"EXPIRED"|"REVOKED"|"INVALIDATED"}` |
| execution | `{downstream_key (null before dispatch), state: "NOT_ATTEMPTED"|"UNKNOWN"|"ISSUED"|"FAILED", downstream_po_number, attempts: [{at, operation: "submit"|"lookup", observation}]}`. Submit observations are ACCEPTED, REJECTED or NO_RESPONSE; a submit whose result was never recorded (for example after a crash) is NO_RESPONSE. Lookup observations are ACCEPTED, REJECTED, PENDING, NOT_FOUND or UNAVAILABLE. |
| events | chronological list of `{at, type, actor, ...}`, one per state change: submission, evaluation, approval, rejection, amendment, revocation, expiry, dispatch, submit outcome, reconciliation. `at` values are non-decreasing. |
| exported_at | clock time of export |
| integrity | implementation-defined integrity material |

**Guarantees both arms must provide:**

* **G1 Durability.** Every state change is durable under `home` before the operation returns,
  and before any downstream submit it precedes. The audit trail survives restarts, including
  crash restarts.
* **G2 Completeness.** The bundle answers what was requested (including amendments), what was
  authorized, by whom, against which record versions and policy, which downstream key was
  used, what was observed, and the current status.
* **G3 Tamper evidence.** `verify_audit(bundle)` returns True for an unmodified exported bundle
  and False (never raising) for any bundle with any key or value changed, added, removed or
  reordered anywhere, including `integrity` itself. It must work on a fresh adapter instance on
  the same home after restart. A bundle exported earlier must still verify after the request
  later changes. Verification therefore cannot compare against live state; it must use key
  material stored under `home`.
* **G4** Bundles and logs contain no key material that would let a reader forge a bundle.

**Not required:** protection against an attacker with write access to `home` or control of the
host process; tamper evidence for the internal database in place; third-party non-repudiation
or public-key distribution; distributed or multi-process coordination; wall-clock accuracy.

## 13. Policy versioning

The adapter reads `env.policy_version` at construction. It must support `po-policy-v1` and
raise `ValueError` for any version it does not implement. Each evaluation, approval,
authorization and audit record carries the policy version in force. Future policy versions may
change constants or add restrictions and reason codes. Records made under an older policy keep
their original policy version.

## 14. Out of scope

Real payments or PO transmission, FX, partial receipts or invoices, multiple budget periods,
network APIs or authentication, UI, and model inference.
