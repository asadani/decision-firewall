# Security boundary and reporting

This embedded local framework is not production IAM or a hostile-plugin sandbox. Application code, registered plugins, identities and runtime filesystem are trusted. Local signing cannot resist host compromise. Deployments must isolate credentials, authenticate callers, prevent alternate execution paths and anchor audit independently.

Never give models execution credentials or expose operator methods to untrusted callers. Unknown outcomes retain reservations; do not retry them with fresh idempotency keys.

No private security reporting address/channel is configured for this local repository yet. Before public publication, maintainers must establish and document one. Do not put secrets or exploitable deployment details in public issues. There is no production support or certification claim.
