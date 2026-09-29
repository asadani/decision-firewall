# Architecture decisions

1. **Refunds anchor v0.1.** Clear amount/balance constraints, duplicate prevention, and customer-versus-revenue incentives make the workflow inspectable. Procurement remains a later generality test.
2. **Python and SQLite first.** Small local installation and explicit transactions. Single-machine serialized dispatch is intentional; distributed scaling is deferred.
3. **Pure policy evaluator.** Validated configuration and deterministic code make the initial safety properties testable. Cedar/OPA remain future adapters; no source reference fixes that choice.
4. **Separate simulator ledger.** Fault injection must model the uncertain boundary between an authorization database and a downstream effect, not merely roll both back together.
5. **Auditable local sandbox, not production IAM.** Seeded roles and loopback review are explicit demonstration affordances. OS trust remains a prerequisite.
6. **Uncalibrated local Laya.** Model metadata and probability semantics are preserved. Evidence, balances, and authority never come from model scores.
7. **Server-rendered inspector.** Shared Jinja templates and a small script avoid a second application build/runtime on an 8 GB machine.
8. **Synthetic evaluation with honest denominators.** Curated policy fixtures test conformance; a separately reported language benchmark measures model behavior. There is no implied real-world refund accuracy.
9. **Bind customer intent independently of assessment.** The proposal includes a customer-declared reason. Model classification cannot choose its own eligibility path; disagreement routes to review. This closes a bypass found during the initial local benchmark; the initial measurements and correction are preserved in the verification report.

