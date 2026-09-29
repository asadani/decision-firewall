# Contributing

Keep changes within the [authorization and recovery product scope](docs/framework/product-direction.md). Prioritize the minimum integration contract, reusable conformance checks and incident reconstruction. Explain which [engineering goal](docs/framework/engineering-value.md) a change supports: integration effort, safeguard completeness, maintenance, investigation or consistent lifecycle behavior. Keep abstractions tied to concrete use cases and document their operating and migration costs. Broader orchestration and model tooling expansion is deferred; preserve existing APIs and integrations.

Claims of improvement need an equivalent competent application baseline. Functional checks, signed receipts and smaller integration files do not establish developer time saved. Preserve failures and denominators, declare evaluation criteria before runs, and label unmeasured benefits as goals. Never hide hard-invariant failures behind aggregate metrics.

Use Python 3.12, core/development locks and an editable install. Run pytest, Ruff check/format, mypy and build before submitting changes. Model-free tests must not download checkpoints. Model measurements must record versions and hardware.

Keep core independent of domain packages, browser tooling and model SDKs. Add domain packs instead of business-specific runtime branches. Test validation, hard constraints, review, stale authorization, resource contention, uncertain effects and reconciliation. Executors must document idempotency and authoritative-failure semantics. Models preserve output semantics and never hold execution authority.

Version changed domain/policy/executor semantics. Include migrations for persistent changes. Keep historical reports labeled with the measured implementation. Run `npm ci` and `npm run diagrams` for Mermaid exports. Inspector changes follow DESIGN.md and UX-CONTRACT.md plus browser checks on freshly seeded data.

Do not change `refer/`, commit secrets/weights/databases or introduce real financial effects in tests. New code is Apache-2.0; preserve reference rights and attribution.
