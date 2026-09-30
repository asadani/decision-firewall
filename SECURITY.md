# Security boundary and reporting

This embedded local framework is not production IAM or a hostile-plugin sandbox. Application code, registered plugins, identities and runtime filesystem are trusted. Local signing cannot resist host compromise. Deployments must isolate credentials, authenticate callers, prevent alternate execution paths and anchor audit independently.

Never give models execution credentials or expose operator methods to untrusted callers. Unknown outcomes retain reservations; do not retry them with fresh idempotency keys.

Report security concerns through [GitHub private vulnerability reporting](https://github.com/asadani/decision-firewall/security/advisories/new). Include the affected version, a minimal simulated reproduction and expected versus observed behavior. Do not put secrets or exploitable deployment details in public issues. There is no production support, response-time guarantee or certification claim.

Version 0.3.1 corrects inspected-evaluation approval binding, rejection durability and oversized outcome metadata handling in the generic runtime. Read the [migration guide](docs/framework/migration.md) before upgrading approval callers. The legacy v0.1 refund workbench has a separate lifecycle and is not covered by all generic-runtime corrections. The global SQLite write lock spans adapter I/O; this is a documented concurrency limitation, not a production throughput guarantee.
