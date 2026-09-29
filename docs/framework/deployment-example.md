# Third-domain integration: simulated deployment approval

This example tests whether the existing authorization/recovery interfaces can support a domain beyond refunds and access. It adds a domain pack and durable simulator without changes to core or the generic CLI. It is an implementation exercise by the framework's implementing assistant, **not an independent integration or productivity study**.

## Run it

From a checkout with the core package installed:

```sh
python examples/deployments/run.py --home .runtime-my-deployment
firewall framework --home .runtime-my-deployment --plugin decision_firewall.domains.deployments.pack:deployment_domain domains
```

Choose a new `--home` for each example run. The example seeds synthetic trusted registry records, requests production deployment, records local reviewer approval, simulates a lost response after success, creates a new runtime instance, reconciles and verifies receipt/replay. It prints statuses and verification results, not authorization tokens. Nothing deploys to a real environment.

Use the returned request ID with the existing generic inspector:

```sh
firewall framework --home .runtime-my-deployment --plugin decision_firewall.domains.deployments.pack:deployment_domain inspect REQUEST_ID
```

This is the existing raw request inspection operation. For offline reconstruction from a verified receipt, use [the investigation command](release-tools.md).

## Demonstration rules

The action names a service, SHA-256 artifact identifier and staging/production environment. The local registry is authoritative for artifact approval, service association, allowed environments and environment enablement. These are explicit example rules, not a production deployment policy.

- Missing registry records require evidence.
- Unapproved artifacts, service mismatches, prohibited environments and frozen environments are mandatory denials.
- Staging may proceed automatically; production requires an authorized local reviewer.
- Authorization expires after 120 seconds; artifact/registry changes invalidate the evidence binding.
- Each environment permits one unresolved simulated deployment at a time. Claims are released after a definitive outcome; unknown outcomes retain their reservations.

The artifact identifier has SHA-256 syntax, but this simulator does not download or cryptographically verify a build artifact. Registry approval is trusted input, not a signature verification service. Registry updates increment versions, including when values are restored.

## Adapter and recovery semantics

[The domain pack](../../src/decision_firewall/domains/deployments/pack.py) supplies a Pydantic action schema, resolver, named mandatory/review rules and execution adapter. `deployments.db` stores registry records and effects separately from the core governance database.

At dispatch the simulator uses a SQLite write transaction to recheck the registry snapshot, apply mandatory restrictions, enforce the environment slot and persist the idempotency key with the action. Reusing a key with another payload is rejected. A definitive failure remains failed for that key. A different business request may intentionally deploy the same artifact again; this does not provide deduplication across distinct proposals.

Modes are `success`, `fail`, `delayed` and `response_loss`. A delayed job retains its slot until the explicit test-only `settle` operation completes it. Settlement represents completion of the already accepted action, not a new authorization; later registry updates do not cancel an accepted job. Production cancellation semantics would require an explicit adapter contract.

Reconciliation reads the original durable key after restart. Absence establishes failure only because this simulator dispatches synchronously and has no remote queue. Real deployment systems must retain `UNKNOWN` whenever a job could still complete. The downstream registry check covers the gap between core evidence resolution and effect commit; advertising a constraint without enforcing it would not suffice.

## Validation and abstraction findings

Local validation on Windows with Python 3.12.14: **19 deployment tests passed;
263 tests passed in the full suite**. Ruff check/format, mypy (46 source files),
package build and local documentation links passed. The built wheel contains the
deployment pack and the existing CLI successfully loads it through `--plugin`.
The runnable example produced `REQUIRE_REVIEW` → `UNKNOWN` → `SUCCEEDED`, with
request status `COMPLETED`, matching replay and a verified receipt. The suite
reported one existing Starlette/httpx deprecation warning. The example is added to
Windows/Linux CI, but Linux execution was not performed in this local validation.

Run the model-free domain checks with:

```sh
python -m pytest tests/test_deployments.py -q
```

They cover production review, mandatory restrictions, absent evidence, stale/revoked/expired authorization, action revisions, success/failure/uncertainty, restart, duplicate dispatch, slot contention, crash before dispatch and a registry change after runtime revalidation. They also verify historical evaluation replay and signed receipts.

The integration needed **no core business-logic changes**. The existing resource claim represents an in-flight deployment slot, rather than money or access duration; existing review and reconciliation APIs handled the rest.

Limits exposed by this exercise:

- Durable idempotency, authoritative lookup and atomic last-mile checks still require domain adapter implementation. The framework does not remove that work.
- The slot is domain-scoped in core and local to this simulator downstream. This establishes no distributed or cross-domain reservation guarantee.
- Generic CLI plugin loading works, but the browser inspector remains refund-specific.
- Domain-specific tests are supplemented by the [reusable conformance runner and offline investigation report](release-tools.md). Those tools have bounded coverage and retain explicit unsupported cases and reconstruction gaps.
- Functional success does not establish integration time saved, fewer independently introduced defects or production suitability. This example is now development-informed and cannot serve as a fresh held-out adoption task.

No paid model call or expanded agent benchmark is needed for these lifecycle checks. The next independent adoption exercise must use fresh tasks under the [measurement plan](engineering-value.md).
