# Conformance checks and incident reconstruction

Status after independent evaluation: reference implementation and conformance kit, with no adoption advantage established. The [0.3.1 corrective release](../verification/0.3.1/README.md) supersedes the earlier test counts below and documents the approval API migration. Historical measurements remain labelled as such.

These core-only tools are the bounded release-candidate deliverables. They do not require a model, telemetry service or browser. Existing application APIs and signed record formats are unchanged.

## Run conformance checks

```sh
firewall conformance decision_firewall.conformance_fixtures:deployments --save deployment-conformance.json
firewall conformance decision_firewall.conformance_fixtures:access --save access-conformance.json
```

The runner creates a fresh temporary directory per check and removes it afterward. Factories are explicitly imported trusted Python code, not sandboxed plugins: supply only synthetic data and simulated executors. It does not accept your live runtime directory. Reports contain individual results, counts, domain fingerprints, suite version and Python/platform metadata.

Exit codes: **0** all checks pass, **1** at least one failed, **2** no failures but one or more unsupported checks. Unsupported is not a pass. The access fixture intentionally reports resource contention as unsupported because that example has no resource claim. The deployment fixture exercises all 17 checks.

Checks cover success, consumed authorization, tampering, expiry, revocation, hard denial, missing/stale evidence, review, review unable to waive hard denial, definitive failure, lost responses, delayed completion, crash before dispatch, receipt/replay, direct adapter idempotency and concurrent resource contention. This is a bounded suite, not exhaustive verification or production certification.

### Supply your domain

Create an installed module exporting `factory(home: Path, scenario: str) -> ConformanceFixture`, then run:

```sh
firewall conformance my_tests.fixtures:create_fixture --save conformance.json
```

Import `ConformanceFixture` and `CHECKS` from `decision_firewall.core.conformance`. See the complete [reference fixtures](../../src/decision_firewall/conformance_fixtures.py). Each fixture supplies:

| Field | Contract |
|---|---|
| `domain`, `proposal`, `assessment` | Fresh pack and normally eligible structured request; fixture assessment is sufficient |
| `effects()` | Count actual successful effects from the authoritative simulated ledger, initially zero; do not count framework outcome records |
| `restart()` | Recreate the original domain/executor against the same durable state without reseeding it |
| `deny()` | Change trusted evidence so a mandatory rule denies the request |
| `missing()` | Remove material evidence so evaluation requires evidence |
| `stale()` | Change material evidence after authorization |
| `settle(attempt_id)` | Complete an already accepted delayed simulated action using its original key |
| `resource_contention` | True only when two individually eligible requests compete for one unresolved-action resource slot |

Choose an executor failure mode from the scenario: `failure` definitively fails, `response_loss` commits an effect but loses its response, and `delayed`/`resource_contention` initially remain unknown. `review` and `review_cannot_override` must initially require review; other scenarios normally start eligible. The runner uses a controlled clock starting at 1000 seconds. Adapt any fixture timestamps accordingly.

Raise `NotImplementedError` from the factory for a scenario you cannot represent. Missing optional hooks are also reported as unsupported. Crash-before-dispatch assumes authoritative absence is a definitive failure in a synchronous simulator; a queued adapter that cannot make that guarantee must declare that scenario unsupported. The direct idempotency check reuses one key, then changes proposal content with that key; the adapter must reject the conflicting payload without another effect.

The fixture/oracle is trusted test code, so an incorrectly implemented oracle can invalidate results. Tests deliberately exercise a missing effect and a duplicating adapter to ensure those failures are visible. Keep domain-specific adversarial and last-mile checks alongside this suite.

## Reconstruct an incident

Export a receipt from the runtime. For the deployment example:

```sh
firewall framework --home .runtime-my-deployment --plugin decision_firewall.domains.deployments.pack:deployment_domain receipt receipt.json
firewall investigate receipt.json receipt.pub DECISION_ID --save incident.json
```

For other domains use their normal `framework --domain` or `--plugin` registration when exporting. The `investigate` command itself is offline: it reads only the receipt and public-key files and does not load domain plugins, resolve live evidence, reconcile or execute actions.

Use a public key established through a trusted channel; accepting an attacker's receipt and adjacent key provides no independent identity assurance. The SDK is `decision_firewall.core.investigation.investigate(receipt, trusted_public_key, request_id)`.

The JSON report includes proposal revisions/hashes, evaluation IDs, policy versions/fingerprints, evidence versions/hashes, reasons, rule results, reviewers, authorization bindings, execution attempts, outcome history and an ordered event timeline. Request status is reconstructed separately from execution status. A reserved attempt without an outcome remains unresolved; absence of a response never becomes assumed success or failure. Superseded authorizations remain visible.

No report narrative is returned if receipt verification fails. Exit **1** means invalid/unreadable input, wrong key or absent request; exit **2** means a verified report has explicit reconstruction gaps, such as an unavailable evaluation snapshot. An unknown execution is a valid recorded state and may return exit **0**; inspect `unresolved_authorizations` before taking action.

Default output omits action values, messages, evidence bodies, model outputs, execution detail, signatures and bearer tokens. For explicit action-value export:

```sh
firewall investigate receipt.json receipt.pub DECISION_ID --action-field service --action-field environment --save incident.json
```

The allowlist is opt-in, not automatic secret detection: do not select fields containing credentials. Policy/review reasons are application-provided text and may also be sensitive. Treat exported reports accordingly. Raw receipt inputs contain more information than the reconstruction report.

The report describes the supplied historical checkpoint, not live external truth. It cannot detect events removed before a newly trusted checkpoint was created, a compromised signing host, or rejected calls never recorded in audit. Existing receipts do not bind every human-readable review field directly to an approval database ID; the report preserves recorded order, reviewer/revision and authorization approval references without inventing a stronger link. Follow unresolved authorization IDs through the existing reconciliation API; do not issue a new idempotency key blindly.

## Release boundary

Local Windows validation: 276 tests passed (13 tool tests), including detection of
missing effects, duplicate adapter effects, invalid receipts and incomplete snapshots.
The reference deployment fixture passed 17/17 checks; access passed 16/17 with one
explicitly unsupported resource-contention check. Ruff, mypy and documentation links
passed. These are scenario results, not productivity measurements.

Package build and a fresh core-only wheel installation also passed, including the
deployment conformance runner and unresolved-incident reconstruction without model,
web or telemetry dependencies. Windows/Linux CI includes these checks; Linux was
not executed locally. The full suite retains one existing Starlette/httpx deprecation warning.

Use these tools with a fresh independent integration next. Freeze feature expansion while gathering adoption feedback. Passing checks establishes the stated scenario behavior; it does not establish developer-time savings, complete security, distributed guarantees or a reason to migrate an already adequate application.
