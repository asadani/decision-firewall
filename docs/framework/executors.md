# Execution adapter contract

Executors expose `name`, semantic `version`, `supported_constraints`, `execute(key, proposal, evidence)` and `reconcile(key)`. Both methods return `ExecutionResult`:

- `SUCCEEDED`: the bound action took effect durably.
- `FAILED`: it definitively did not take effect and cannot complete later.
- `UNKNOWN`: uncertainty remains and resources stay reserved.

Persist the idempotency key with the exact action before/atomically with effects; reject reuse with another payload. Timeouts, exceptions, malformed responses or temporary lookup absence are not proof of failure. Core treats arbitrary adapter exceptions as unknown. Reconciliation never generates a replacement key or calls `execute` again.

Reconciliation must query the same authoritative system after restart. Absence proves failure in the included synchronous local simulators while the dispatch lock is held. A remote queue may still complete an unseen request: return `UNKNOWN` unless its contract proves otherwise.

Core binds action, evidence, policy, adapter version and constraints. Downstream systems must enforce invariants at the effect boundary: evidence may change after resolution. Refund execution passes the expected payment version and atomically checks balance/destination. Listing a constraint does not implement it.

`SimulatedExecutor` records arbitrary actions in a separate SQLite ledger. Modes `delayed`, `response_loss`, `fail` and `success` exercise recovery; `settle(key)` explicitly completes a delayed effect. It never grants real permissions, publishes content or moves money.

Production adapters, credential isolation and prevention of alternate execution paths belong to the integrating application. Models must not receive credentials or the governance runtime object.
