# Framework architecture

`DecisionFirewall` accepts registered `DomainPack` instances and validated assessments. Packs define business semantics; core lifecycle code never imports domains or model libraries. A test enforces that boundary.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/framework-dark.svg">
  <img alt="Decision Firewall architecture: proposals, trusted evidence, policy, bound authorization, idempotent execution and signed records." src="../diagrams/framework.svg">
</picture>

[Interactive walkthrough and diagram sources](../diagrams/README.md).

The core owns submission revisions, assessment snapshots, identity checks, policy snapshots, reviews, authorization bindings, reservations, execution attempts, reconciliation and signed receipts. Domain code owns action validation, evidence resolution, deterministic rules and executor implementation. Applications choose trusted plugins and actors.

Both `refund_domain()` and `access_domain()` run on the same core. Refunds reuse the existing deterministic evaluator and payment ledger through an adapter. Access validates employee/resource/hour actions without refund imports. A generated document-review domain demonstrates extension outside the repository.

## Persistence and execution

`governance.db` contains decisions, checks, approvals, permits, reservations, identities and events. Current rows are projections; original revision/evaluation/review snapshots remain in the signed chain. The v0.1 `firewall.db` remains a separate compatibility database.

Evaluation captures the domain manifest, intent, model output, evidence versions, resource usage, review and time. An allowed result becomes a signed permit bound to material inputs, executor identity generation, revision, domain/policy/adapter versions, constraints, claim definitions and expiry. Errors, missing evidence, unavailable assessments and unsupported constraints cannot authorize.

Execution revalidates and atomically claims the permit/resources. A second validation immediately before dispatch closes the reservation/dispatch gap. SQLite's write lock excludes concurrent dispatch/reconciliation in this store. Adapter exceptions remain `UNKNOWN`; reservations persist. Reconciliation queries the original key and never dispatches a replacement. Changing the registered domain/adapter fingerprint blocks reconciliation until the original implementation is restored.

## Resources and replay

Policies can return integer `Claim` records: key, units, capacity, exhaustion disposition and whether success continues consuming allowance. Pending/unknown claims always count. Balance reservations typically release on success because the authoritative ledger accounts for the effect. Date-qualified budget claims retain successful usage. Review may change policy-produced claims but must not waive hard domain constraints.

Resources are scoped to a domain in one governance database. Separate runtime directories do not coordinate. Downstream systems must enforce invariants atomically; the payment simulator checks balance, destination and evidence version. The generic simulator only records actions.

Replay requires the original manifest and implementation. It uses stored context without model/evidence calls. Version strings identify application-supplied code; they are not code attestation. Increment versions on semantic changes and retain old implementations for historical replay.

Canonical JSON, SHA-256 and Ed25519 primitives are shared with the legacy facade. Receipt verification needs an independently trusted public key. Snapshot integrity does not prove evidence truth; plugins have host privileges.

Packaging inspiration: [Paperclip](https://github.com/paperclipai/paperclip) separates server/UI/packages and documents adapters; [Hindsight](https://github.com/vectorize-io/hindsight) foregrounds quickstarts, SDKs and concepts. No source code was copied. This project uses one Python distribution with optional integrations.
