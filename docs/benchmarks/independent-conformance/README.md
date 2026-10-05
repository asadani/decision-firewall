# Independent conformance extraction, October 5, 2026

This is a new development pilot, separate from the historical framework adoption
comparison. [summary.md](summary.md) and [results.json](results.json) contain measured
results, source hashes and integration inventory.

## What was tested

- Existing plain application controls: 3/3 healthy scenarios pass.
- Existing Decision Firewall integration: 3/3 healthy scenarios pass.
- Three declared behavioural injections in each arm: all six targeted scenarios
  produce FAIL, with no errors counted as successful detection.
- Plain application wheel smoke: 3/3 pass in a fresh Python environment without
  Decision Firewall or Pydantic installed, including recovery in a new interpreter.
- The independent wheel contains only `control_conformance`; the framework wheel
  contains no copy of that package. Installing one does not install the other.

The revised suite is `control-conformance-pilot-2`. The plain application returns
cached success on a repeat; Decision Firewall refuses
the consumed authorization. Both behaviours pass because neither creates a second
effect. For stale approval, observing a downstream rejection alone is insufficient:
the call recorder exposes the unsafe dispatch even when the service prevents an effect.

Review found and closed false-pass paths: effects during preparation/approval, wrong
effect payloads hidden by a count of one, a no-op evidence-change hook, and a pre-restart
lookup mistaken for recovery. Regression tests also cover malformed oracles, late
unsupported declarations and a detection summary hiding unrelated errors. Automatic
actions can exercise duplicate/recovery checks without a fabricated review.

Recovery here reconstructs the application in a fresh interpreter; it is not a process
kill or power-loss experiment. Source hashes normalize CRLF to LF for cross-platform
verification. The mutation gate requires the targeted FAIL and PASS for every other
scenario, not merely any failure somewhere in the run.

## Reproduce

See the [package guide](../../../conformance/README.md) for installation and adapter
contracts. From the repository root, with the framework's development dependencies
and the independent package installed:

```sh
python -m pytest tests/test_independent_conformance.py -q
python -m benchmarks.control_conformance.run --output .runtime-independent-pilot
python -m build conformance
python scripts/verify-conformance-wheel.py
```

The Windows/Linux CI matrix runs these checks. Local measurements here are Windows
11, Python 3.12.14; Linux was not executed locally. No model, GPU or paid API is used.

## Interpretation

The test contract can travel between these two existing implementations without
requiring the framework runtime. This is narrower than establishing that a new team
can integrate it cheaply. The common bridge/oracle is 136 nonblank lines, plus a
13-line recovery worker; it also relies on the existing engines listed in the report.
Those counts include comments and do not measure developer effort or total system size.

The evidence supports keeping this small extraction available for testing. It does
not establish runtime superiority, exhaustive control coverage or production safety.
The fault injections are explicit behavioural failures at engine method boundaries,
not a general mutation-testing score. Stale-before-review races, reservation semantics,
concurrency, and signed receipt formats remain outside this three-scenario profile.
