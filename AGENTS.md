# Project instructions

Start with [the agent entry guide](docs/framework/agent-guide.md) for setup, reading order, integration steps and verification. Read [product direction](docs/framework/product-direction.md) before expanding scope. Roadmap deliverables are planned unless implementation and tests establish otherwise.

All financial effects must remain simulated unless a future user explicitly scopes a real integration.
Keep assessment, trusted evidence, policy, and execution authority separate.
Core must not import domain packages, model SDKs, or web tooling. Implement business rules in explicit domain packs.
New integrations use DecisionFirewall; retain v0.1 refund compatibility and document migrations explicitly.
Do not let model confidence bypass mandatory controls. Preserve unknown outcomes until reconciliation.
Use integer minor units. Do not modify refer/.
Run pytest, Ruff, mypy, and the package build after substantive changes. Model-free CI must not download weights.
Document the actual device, model revision, and dataset split for benchmark claims.
Use shared templates/tokens and maintain DESIGN.md and UX-CONTRACT.md for UI work.
On this Windows machine prefer Git Bash for ordinary shell work; if the execution wrapper resolves to unavailable WSL, use native PowerShell without mixing syntax.

