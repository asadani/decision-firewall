# Independent control-conformance pilot

Test existing application controls without installing or adopting the Decision Firewall
runtime. This is a Python 3.12 package using only the standard library. It is a bounded
development pilot, not a certification suite or a new workflow engine.

From a checkout of this repository:

```sh
python -m pip install ./conformance
python -m control_conformance benchmarks.control_conformance.adapters:application --output report.json
```

This installs `decision-control-conformance`, not `decision-firewall`. The example
application imports the unchanged application controls and simulated service from the
historical benchmark sources in this checkout. Your own adapter does not need them.
The package is not published to PyPI.

## Three declared behaviours

| Scenario | Required observation |
|---|---|
| Stale approval | After approval, material evidence changes. The old approval must not dispatch, even if the new evidence would still qualify after fresh review. |
| Duplicate effect | Execute a successful approved action twice. Refusal or returning the original success is acceptable. Exactly one effect; any repeat dispatch must retain the original key. |
| Lost response | The downstream effect succeeds but its response is lost. Keep the outcome unknown, restart, and recover by querying the original key without another dispatch. |

Only stale approval requires human review. Automatic actions can run the duplicate
and recovery checks with `prepare()` returning `READY`; the runner does not call
`approve()` in that case. Declare stale approval unsupported in the factory if it
does not apply, rather than inventing an approval step. The pilot
does not check every way of creating stale approval (for example, evidence changes
*before* approval), all resource reservations, concurrency, authentication or signatures.
The older `firewall conformance` command still provides its 17 runtime-specific checks.

## Connect your own application

Implement a trusted `factory(home: Path, scenario: str) -> Target`. The runner supplies
a fresh temporary directory for each scenario. Use synthetic data and a simulated
effect service; never point it at live financial or deployment systems.

The `Target` protocol has six operations:

- `prepare()` returns `REVIEW_REQUIRED`, or `READY` for an automatically authorized action.
- `approve()` performs authorized review and returns `READY`.
- `execute()` calls the application, returning `SUCCEEDED`, `UNKNOWN`, `BLOCKED` or `FAILED`.
- `change_evidence()` changes a material fact after approval, without changing the action.
- `recover_after_restart()` restarts the application and recovers its original attempt.
- `observe()` returns the observation below from an independent simulated effect ledger
  and call recorder, not the application's own claim of success.

```python
from control_conformance import Observation

observation = Observation(
    effects=1,
    dispatch_keys=("original-attempt",),
    lookup_keys=("original-attempt",),
    expected_effect="fingerprint-of-the-fixture-action",
    effect_fingerprints=("fingerprint-of-the-fixture-action",),
    evidence_fingerprint="fingerprint-of-current-authoritative-facts",
)
```

Compute fingerprints from canonical representations of the complete action and
material evidence. The expected action comes from the test fixture; effect fingerprints
come from actual downstream records. Do not derive both from the application's requested
action. The suite rejects a wrong effect even when the aggregate count is one.

The oracle must be cumulative and read-only. Preparation and approval must not dispatch
or change the evidence. The stale hook must demonstrably change the material evidence
fingerprint. Recovery requires a **new** authoritative lookup after the recovery method
starts, with the original dispatch key; an earlier lookup is insufficient. Malformed
observations are errors. These stricter checks are recorded as suite `control-conformance-pilot-2`.

The adapter may translate native refusal results/exceptions. Unexpected errors must
propagate: the runner reports `ERROR`, which is never a safe refusal or a pass. The
adapter must not add missing approval validation, deduplication or recovery logic.
Record calls before downstream validation so an unsafe dispatch is visible even if
the service refuses the effect. Keys may be opaque; no Decision Firewall token format,
database schema, model, signing library or exception class belongs in the suite.

Raise `Unsupported(reason)` **from the factory** for missing test hooks, before any
scenario runs. Raising it during execution is an error, not a way to downgrade a
failed/partly executed scenario. CLI exit codes: 0 all pass, 1 a
failure/error, 2 unsupported with no failures/errors. All three statuses remain
visible separately. Factories are executable trusted code, not isolated plugins.

## Reproduce the comparison

To exercise the Decision Firewall arm as well, install the root project and its core
dependencies separately, following the root README. Then from the repository root:

```sh
python -m benchmarks.control_conformance.run --output .runtime-independent-pilot
```

The new bridges wrap existing `benchmarks/reuse_observability` implementations; historical
implementations/results are unchanged. Recovery reconstructs the application in a
fresh Python interpreter using persisted state. This is not an OS process-kill or
power-loss test; the original harness remains alive and does not service recovery calls.
The service independently records calls and effects in SQLite. The plain application
arm needs no framework import, including during recovery.

The six declared injections disable stale validation or introduce a new dispatch key
on repeat/recovery. They are isolated behavioural faults at engine method boundaries,
not a source-mutation coverage score. Detection requires a targeted `FAIL`; crashing
the adapter with `ERROR` does not count. See `benchmarks/control_conformance/faults.py`.

Measured reports live in `docs/benchmarks/independent-conformance/`. Both bridges share
one simulated export domain and were written with knowledge of the implementations.
This establishes portability for these examples and sensitivity to these faults. It
does not establish low integration effort for an unfamiliar application or human time
saved. Adapter source inventory is provided as implementation size, not productivity.
