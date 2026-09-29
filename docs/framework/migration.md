# From the refund workbench to the framework

v0.1 imports (`engine.Firewall`, refund contracts/providers) and top-level CLI commands remain compatible. Their code now lives under `domains.refunds`, with compatibility re-exports. Shared audit/SQLite primitives live in core.

New applications import root `DecisionFirewall`, `Proposal` and `Assessment`. Register `refund_domain(home)` to use the generic lifecycle or register your pack. `RefundModelAdapter(old_provider)` maps old outputs; the old refund proposal becomes the generic proposal's `action`.

v0.1 uses `firewall.db`; core uses `governance.db`. There is no implicit migration or reinterpretation of old signatures. Preserve old exports/keys. Do not submit the same business action to both runtimes: different governance IDs require application-level deduplication. Prefer separate demonstration home/evidence directories. Shared downstream ledgers must independently enforce invariants.

The refund inspector and existing benchmark runner remain on the compatibility facade; they do not display generic requests. Laya inference is now shared with the configurable generic adapter. Historical v0.1 reports remain labeled; refactor tests do not create new model-accuracy measurements.

## v0.3 additive upgrade

History uses a separate `history.db`; rule reports use an additive table and new audit events. Existing signed payloads are not rewritten. Default generic packs now use new rule-set versions; select their `pack_v1` factories for old-policy replay. See [named-rule compatibility](rules.md) and the [history workflow](history-and-evaluation.md).
