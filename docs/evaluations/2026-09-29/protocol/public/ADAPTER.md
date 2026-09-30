# Adapter interface and common harness (protocol v1)

Both implementations plug into one harness, `harness/po_harness/`. The harness gives both the
same test semantics and expected outcomes, and judges results by inspecting the
**authoritative downstream effect store and records**, not only the statuses an implementation
returns.

## 1. Factory

```python
def create_adapter(home: pathlib.Path, env: po_harness.Environment) -> POAdapter: ...
```

* `home` is an existing directory. All of the implementation's durable state goes here:
  databases, logs, keys. The harness never looks inside it during tests.
* `env` holds the harness services: `clock`, `directory`, `records`, `downstream` and
  `policy_version`. Keep a reference to it. The same objects survive a restart.
* The factory is selected with `PO_ADAPTER=package.module:function`.
  `PO_ADAPTER_PATH=<dir>[;<dir>...]` (os.pathsep-separated) is prepended to `sys.path`.
* Construction must raise `ValueError` for an unsupported `env.policy_version`. It must not
  call `env.downstream`; the harness checks this.

## 2. Interface (`po_harness/adapter.py`)

```python
class POAdapter(Protocol):
    def submit(self, caller: str, idempotency_key: str, po: Mapping[str, Any]) -> Outcome: ...
    def amend(self, caller: str, request_id: str, po: Mapping[str, Any]) -> Outcome: ...
    def reevaluate(self, caller: str, request_id: str) -> Outcome: ...
    def approve(self, caller: str, request_id: str) -> Outcome: ...
    def reject(self, caller: str, request_id: str) -> Outcome: ...
    def revoke(self, caller: str, request_id: str) -> Outcome: ...
    def issue(self, caller: str, request_id: str) -> Outcome: ...
    def reconcile(self, caller: str, request_id: str) -> Outcome: ...
    def status(self, request_id: str) -> Outcome: ...
    def export_audit(self, request_id: str) -> dict[str, Any]: ...
    def verify_audit(self, bundle: Mapping[str, Any]) -> bool: ...
    def close(self) -> None: ...
```

* Return `po_harness.Outcome(request_id, status, reason_codes, downstream_po_number, expires_at)`.
* Raise `po_harness.OperationRejected(code)` for refused operations.
* Request ids are strings of your choosing, unique within a home.
* Behaviour is specified in REQUIREMENTS.md.

## 3. Harness services (`po_harness/services.py`)

Adapter-facing methods are listed below. Methods marked TEST CONTROL in the source are for
the harness only, and adapters must not call them.

| Service | Adapter-facing API | Notes |
|---|---|---|
| `env.clock` | `now() -> float` | Controlled clock. Tests advance it. |
| `env.directory` | `get(principal_id) -> Principal \| None` | `Principal(principal_id, roles, department_id, active)` |
| `env.records` | `get_vendor(id) -> VendorRecord \| None`, `get_budget(dept) -> BudgetRecord \| None` | May raise `RecordsUnavailable`. Versions increase on every change, including restores. |
| `env.downstream` | `submit(key, order) -> SubmitResponse`, `lookup(key) -> LookupResponse` | The authoritative effect store. See below. |

### Downstream PO system contract

* `submit(key, order)`:
  * `key` is your downstream idempotency key: a non-empty str of at most 200 chars.
  * `order` must be exactly `{"request_id", "department_id", "vendor_id", "category",
    "amount_minor", "currency", "description"}`. Otherwise it is rejected with `INVALID_ORDER`.
  * Returns `SubmitResponse(accepted, po_number, code)`, or raises `DownstreamTimeout`
    (outcome unknown).
  * The harness may inject `SimulatedCrash`, a `BaseException`. Let it propagate.
  * Re-submitting an existing key with an identical order returns the original response and
    creates no new effect. With a different order it is rejected with
    `KEY_REUSED_DIFFERENT_ORDER`.
* `lookup(key)` returns `LookupResponse(state, po_number, code)`, where `state` is one of
  `ACCEPTED | REJECTED | PENDING | NOT_FOUND`, or raises `DownstreamUnavailable`.
  * `NOT_FOUND` is authoritative. It also *fences* the key: a later submit with that key is
    rejected with `KEY_FENCED`.
  * `PENDING` means the order was received but is not final.
* Rejections are definitive.
* The downstream system does **not** enforce budgets, restrictions or approvals.

### Fault injection (harness-controlled)

Each fault applies to the next `submit` call:

| Fault | Effect | What the adapter sees |
|---|---|---|
| `REJECT` | none | rejected response |
| `LOSE_RESPONSE_AFTER_ACCEPT` | applied | `DownstreamTimeout` |
| `LOSE_REQUEST` | never received | `DownstreamTimeout` |
| `QUEUE_THEN_TIMEOUT` | pending until the harness settles it | `DownstreamTimeout` |
| `CRASH_BEFORE_RECEIVE` | never received | `SimulatedCrash` |
| `CRASH_AFTER_ACCEPT` | applied | `SimulatedCrash` |

Lookup fault: `LOOKUP_UNAVAILABLE`.

The downstream system can add latency, which tests use to widen race windows.

## 4. Restart semantics

* **Graceful restart:** the harness calls `close()` on the current instance, discards it and
  calls the factory again with the **same** `home` and the **same** `env`.
* **Crash restart:** after a `SimulatedCrash` propagates out of an operation, the harness
  discards the instance **without** calling `close()` and constructs a new one on the same
  `home`. Anything not durably written by then is lost.
* A discarded instance is never called again. File handles or connections it left open must
  not stop the new instance from working. Do not rely on finalizers.
* The harness services keep their state across restarts, because they model external systems.

## 5. Concurrency

* A single adapter instance is called concurrently from many threads in one process. Every
  operation must be thread-safe, and the budget, idempotency and single-dispatch invariants
  must hold under that concurrency.
* At most one live adapter instance exists per `home` at any time. Multiple processes and
  multiple simultaneous instances on one home are **not** required.
* Tests do not mutate records while a dispatch is in flight.

## 6. How outcomes are judged

After every test, the harness checks the following against the downstream store:

* Oracle violations recorded at the moment an order was received: mandatory restriction,
  budget exceeded, duplicate effect for a request.
* At most one accepted or pending effect and at most one key per request.
* Effect content equal to the PO last submitted or amended for that request.
* For every request id the test has seen, `status()` consistent with the downstream store.
  ISSUED needs an accepted effect with a matching `downstream_po_number`. FAILED, and every
  eligibility or lifecycle status, needs no live effect.

## 7. Running the visible tests

```sh
# from protocol/public/tests (copy the directory if you want to add your own tests)
PO_ADAPTER=my_po.adapter:create_adapter PO_ADAPTER_PATH=/path/to/src python -m pytest -q
```

Optional `PO_REPORT=report.json` writes a per-test JSON summary with requirement and invariant
tags. Tests use pytest's `tmp_path` for `home`.

Do not modify `harness/` or `tests/`. Held-out tests use exactly the same harness and loading
mechanism.
