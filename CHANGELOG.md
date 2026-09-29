# Changelog

## Unreleased — Preparation and public benchmarks

Added a core-only, 17-check simulated integration conformance runner with explicit
unsupported/failure results, and offline incident reconstruction from a verified
receipt and separately trusted key. Added CLI commands, reference fixtures and tests.
Existing signed formats and runtime decision behavior are unchanged.

Added a simulated deployment domain using the existing core interfaces, with named
registry restrictions, production review, environment-slot claims, durable idempotency
and restart reconciliation. Added a model-free example and domain tests; core and
historical benchmark artifacts are unchanged. This is not an independent adoption study.

Narrowed product direction to an authorization and recovery runtime for consequential
actions. Prioritized a minimum integration contract, reusable conformance suite and
incident reconstruction before an independent adoption exercise. Broader feature
expansion is deferred; these priorities are planned, not completed deliverables.

Repositioned the project around reusable application governance and five engineering
outcomes: integration effort, safeguard completeness, maintenance, investigation and
consistency. Added a fair-comparison measurement plan and prioritized roadmap. These
benefits remain unmeasured; existing benchmark artifacts and runtime APIs are unchanged.

Added optional pinned τ-bench retail and AgentDojo banking adapters, a frozen three-arm
development pilot, shared-input response caching, durable capped OpenRouter accounting,
and standalone reports. Agent, simulated-user and language-judge calls share one budget.
The tool-boundary checks never read hidden task solutions. Dependency locks and offline
integration checks keep these suites separate from the core installation.

Added full-source paired classification measurements for BANKING77 and Bitext, with separate official
test/out-of-fold metrics and explicit SDK/preparation overhead. Added pinned agent-suite source inspection
and local tool-calling endpoint preflight. No τ-bench/AgentDojo task-success claims are made without runs.

Added optional SDK/CLI preparation with trusted evidence snapshots, selected existing mandatory rules,
bounded model context, explicit structured routing, signed preparation records and telemetry linkage.
Final authorization and dispatch checks remain unchanged. Added a core-only example and starter command,
measured preparation overhead/avoided calls, and a hash-pinned BANKING77 baseline on official train/test
splits. Public dataset scores measure interpretation, not execution safety. Existing reports remain
historical snapshots of the implementations they measured.

## 0.3.0 — History, evaluation, rules and observability

Added atomic CSV/JSONL history import with linked revisions, reviewed annotations, immutable grouped dataset splits, guarded historical retrieval, capability-limited offline policy/model experiments, custom evaluators and standalone reports. Added named rule composition, versioned reference policies retaining v1 replay, bounded optional OTLP export, and a complete core-only generated workflow. Existing signed payload formats and historical benchmark artifacts are unchanged.

## 0.2.0 — Framework refactor

Added domain-neutral contracts/runtime, plugin interfaces, generic CLI, domain starter and configurable Laya questions. Extracted shared audit and isolated refund code. Added an independent access domain and optional inspector dependencies. Preserved v0.1 APIs and database format. New runtime data uses `governance.db`; no implicit migration.

## 0.1.0 — Refund reference implementation

Deterministic policy, durable payment simulator, local Laya, loopback inspector, synthetic benchmarks and signed receipts. Historical measurements remain under `docs/benchmarks/`.
