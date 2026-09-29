# Public SDK and CLI

For reusable adapter checks and offline receipt-based reconstruction, see [release tools](release-tools.md): `firewall conformance` and `firewall investigate`. SDK functions live in `core.conformance` and `core.investigation`.

Primary imports from `decision_firewall`: `DecisionFirewall`, `Proposal`, `Assessment`, `Signal`, `Decision`, `DomainPack`. Additional contracts/protocols live in `decision_firewall.core`.

| SDK operation | Purpose |
|---|---|
| `DecisionFirewall(home, domains, identity=..., clock=...)` | Register trusted plugins/identities |
| `assess(model, message)` | Validate provider output; propagate failure |
| `prepare(proposal, spec=None)` | Persist evidence, prechecks and model-routing result; no permits |
| `inspect_preparation(id)` | Read the preparation snapshot as its requester |
| `assess_prepared(id, model=None)` | Check snapshot freshness; infer or use the recorded deterministic assessment |
| `submit(proposal, assessment)` | Validate action and append revision 1 |
| `revise(id, proposal, assessment)` | Append revision; revoke unclaimed permits |
| `evaluate(id)` | Persist snapshot and conditionally issue permit |
| `review(id, Review(...), revision=...)` | Record authorized review and re-evaluate |
| `execute(token)` | Revalidate, reserve, claim and dispatch once |
| `reconcile(permit_id)` | Resolve original attempt without retry |
| `revoke(permit_id)` | Revoke an unclaimed permit |
| `outcome(id, description, kind=...)` | Append outcome, appeal or correction |
| `detail(id)` | Inspect request, events and execution states |
| `replay(evaluation_id, domain=...)` | Replay with recorded implementation |
| `receipt()` | Export chain and signed checkpoint |
| `verify_receipt(receipt, trusted_public_key)` | Verify signatures, links and checkpoint |
| `configure_identity(name, role, active=...)` | Trusted administration; bump authority generation |

`RuntimeIdentity` comes from trusted host code. Seeded roles are a local demonstration, not network authentication. Proposals/assessments forbid extra actor/permission fields.

Options precede generic CLI commands:

```sh
firewall framework --home .runtime-app --domain access domains
firewall framework --home .runtime-app --domain access submit proposal.json assessment.json
firewall framework --home .runtime-app --domain access evaluate REQUEST_ID --save authorization.json
firewall framework --home .runtime-app --domain access execute authorization.json
firewall framework --home .runtime-app --domain access inspect REQUEST_ID
firewall framework --home .runtime-app --domain access receipt receipt.json
firewall verify receipt.json receipt.pub
```

Use `--plugin installed_module:create_domain` for custom packs. Authorization files are scoped expiring permits, with no reusable provider credentials. API 0.2 is experimental. Records carry `schema_version`; domain/policy/adapter versions identify semantic behavior. Changes require versioning, compatibility tests and migration notes.
