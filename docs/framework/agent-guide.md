# Agent entry guide

Use this guide to integrate Decision Firewall into a use case or contribute to this repository. Read the repository's [AGENTS.md](../../AGENTS.md) first. User instructions determine the task; this guide does not authorize paid inference, publishing or real external effects.

## Read in this order

1. [Product direction](product-direction.md): authorization and recovery for consequential actions; scope and planned work.
2. [Build a domain](build-a-domain.md): action schema, evidence, policy and registration.
3. [SDK and CLI](api.md) and [executor contract](executors.md): available operations and recovery semantics.
4. [Architecture](architecture.md), then the implementation and tests relevant to the requested change.

For optional work, use the [model guide](models.md), [preparation guide](preparation.md), [rules guide](rules.md), [history/evaluation guide](history-and-evaluation.md) or [observability guide](observability.md). Do not install every optional dependency to complete a core integration.

The [deployment example](deployment-example.md) shows a third domain using the existing plugin interface, including an atomic downstream registry check and restart recovery. It is development-informed evidence, not a held-out adoption task.

## Set up and establish a baseline

Run from the repository root in an activated Python 3.12 virtual environment:

```sh
python -m pip install -r requirements-core.lock -r requirements-dev.lock
python -m pip install --no-deps -e .
firewall framework --domain access demo
firewall framework --domain refunds demo
```

These commands use simulated effects and local runtime storage. No model download or API key is needed. Use a separate runtime directory for experiments and tests; do not reuse a user's database without task-specific authorization. Do not read or print `.env` contents.

## Task A: integrate a new use case

First identify the action, authoritative evidence, mandatory restrictions, review requirements, resource limits and execution system. Missing business requirements must remain explicit; do not invent eligibility rules or treat a model's assertions as verified facts.

Generate the working example into a new directory:

```sh
firewall init my-decision-app
python my-decision-app/run.py
```

Edit its `plugin.py` to implement the domain. Use [the domain tutorial](build-a-domain.md) for contracts; compare the included [access pack](../../src/decision_firewall/domains/access/pack.py) and [refund pack](../../src/decision_firewall/domains/refunds/pack.py). Keep business logic outside core.

The minimum path is `submit` → `evaluate` → authorized `execute`, with `review` when required and `reconcile` for uncertain execution. Caller identity comes from trusted runtime configuration. Start with a fixture assessment and simulated executor; model integration is optional.

Validate the integration with tests appropriate to its requirements:

- Mandatory denial and missing evidence prevent execution; approval cannot waive hard constraints.
- Changed action/evidence, expired authorization and unsupported constraints prevent dispatch.
- Applicable resource limits survive concurrent requests.
- Repeated execution cannot duplicate effects.
- A lost success response remains uncertain until authoritative reconciliation; restart preserves the original idempotency key and reservations.
- Records distinguish the customer's request from an execution attempt; receipts verify and pinned evaluations replay.

Use the [reusable conformance runner](release-tools.md) through `firewall conformance trusted.module:factory`. Supply simulated fixtures and an authoritative effect-count oracle. Retain domain-specific tests; report unsupported or untested cases rather than claiming complete conformance.

Deliver the adapter, runnable example, relevant tests and instructions covering setup, policy versions and execution limitations. Explain what belongs to the framework versus the integrating deployment.

## Task B: continue framework development

Use the [roadmap](../../ROADMAP.md) and the requested task to select a bounded change. Conformance and offline incident reconstruction are implemented; see [release tools](release-tools.md). Feature expansion is frozen pending independent adoption evidence. Preserve existing `detail` / CLI `inspect`, receipt and replay operations.

Preserve public APIs, old signed payloads and historical benchmark artifacts. Version semantic changes and test compatibility. Do not add general orchestration, model tuning or retrieval infrastructure merely to broaden the framework. Preserve unknown execution outcomes until authoritative resolution.

For substantive code changes, run:

```sh
python -m pytest -q
python -m ruff check src tests scripts examples
python -m ruff format --check src tests scripts examples
python -m mypy src/decision_firewall
python -m build
```

Also validate any changed benchmark code or optional integration with its relevant checks. Core tests must remain model-free. For documentation-only work, check commands against current code and validate local links; report that runtime tests were not rerun.

In the handoff, state what changed, exact checks run and results, remaining limitations and any incomplete acceptance criteria. Never describe a plan as implemented or a fixture run as actual model inference. Engineering benefits require independent measurement under the [measurement plan](engineering-value.md); automated scenario results do not establish developer productivity.

## Example task prompts

Integration:

> Read AGENTS.md and docs/framework/agent-guide.md. Integrate my specified use case as a DomainPack, using fixture assessments and simulated execution first. Keep business rules out of core. Implement the relevant lifecycle tests and provide setup instructions. Ask for missing business requirements before implementing dependent rules.

Framework development:

> Read AGENTS.md and docs/framework/agent-guide.md. Inspect the existing conformance and investigation tools, then address the specific reported integration defect. Preserve compatibility and run the relevant release checks. Do not broaden scope beyond the reported defect.
