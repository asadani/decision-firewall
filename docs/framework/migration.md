# From the refund workbench to the framework

## 0.3.1 corrective upgrade

Generic `DecisionFirewall.review(..., decision="approve")` now requires `evaluation_id` from the evaluation the reviewer actually inspected. In code, the decision remains a `Review(decision="approve", reason=...)` object. The CLI equivalent is `--evaluation-id`. Missing, superseded or materially stale snapshots fail closed; re-evaluate and request review again. Bundled examples, starter and benchmark callers have been updated.

New signed review events include the evaluation ID, approval ID and evidence hash. Old approvals without this provenance cannot authorize new dispatch; existing unclaimed permits bound to such approvals fail revalidation. Obtain a fresh evaluation and approval. Outstanding uncertain attempts continue to reconcile with the original adapter/key; do not resubmit them. Existing signed records and receipts are not rewritten, and historical replay continues to use recorded contexts.

The latest review is selected before validating its actor, evidence or expiry. A rejection remains a veto for its proposal revision even if its reviewer is deactivated, evidence changes or time passes. A new proposal revision is the explicit correction/appeal path. Invalidating a newer approval never revives an older one. Revocation still applies to an individual unclaimed permit; it is not a durable withdrawal of all consent.

Adapter result metadata integers outside ±(2^53−1) are recorded losslessly as decimal strings in a `safe-integers-v1` envelope with typed paths to converted values. Status remains authoritative; other non-canonical detail is explicitly omitted. Actual required audit write failures still block/roll back the recording transaction and leave the original attempt available for reconciliation.

These corrections apply to the generic runtime, not the separate v0.1 refund compatibility engine/browser. That legacy engine has a duplicated lifecycle and remains a historical demonstration with known limitations, not a production path. Global write locking, fixed approval lifetime, host authentication and external audit anchoring are not redesigned in this release.

v0.1 imports (`engine.Firewall`, refund contracts/providers) and top-level CLI commands remain compatible. Their code now lives under `domains.refunds`, with compatibility re-exports. Shared audit/SQLite primitives live in core.

New applications import root `DecisionFirewall`, `Proposal` and `Assessment`. Register `refund_domain(home)` to use the generic lifecycle or register your pack. `RefundModelAdapter(old_provider)` maps old outputs; the old refund proposal becomes the generic proposal's `action`.

v0.1 uses `firewall.db`; core uses `governance.db`. There is no implicit migration or reinterpretation of old signatures. Preserve old exports/keys. Do not submit the same business action to both runtimes: different governance IDs require application-level deduplication. Prefer separate demonstration home/evidence directories. Shared downstream ledgers must independently enforce invariants.

The refund inspector and existing benchmark runner remain on the compatibility facade; they do not display generic requests. Laya inference is now shared with the configurable generic adapter. Historical v0.1 reports remain labeled; refactor tests do not create new model-accuracy measurements.

## v0.3 additive upgrade

History uses a separate `history.db`; rule reports use an additive table and new audit events. Existing signed payloads are not rewritten. Default generic packs now use new rule-set versions; select their `pack_v1` factories for old-policy replay. See [named-rule compatibility](rules.md) and the [history workflow](history-and-evaluation.md).
