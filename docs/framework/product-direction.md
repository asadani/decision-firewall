# Product direction: authorization and recovery for consequential actions

## Decision

Focus Decision Firewall on a reusable execution lifecycle for actions that need explicit permission, reliable recovery and an explanation afterward. Its central contract is authorization bound to an exact action and its supporting facts, with durable tracking through execution and reconciliation.

The target user is an engineer adding consequential actions to multiple application integrations. A human, deterministic program or model may originate a proposal. The lifecycle must work without inference or an external observability service.

This is reusable application engineering. Equivalent correct controls should produce equivalent decisions. The framework must earn adoption through usable integration contracts and dependable lifecycle behavior, not a claim of inherently better decisions.

## Scope

| Area | Role |
|---|---|
| Action-bound authorization, review, reservations, execution tracking and reconciliation | Core runtime |
| Authoritative evidence, domain rules and durable idempotent executors | Explicit application extension contracts |
| Signed records and incident reconstruction | Core investigation capability |
| OpenTelemetry correlation and export | Optional integration with existing observability tools |
| History, named rules and offline evaluation | Supporting tools for testing explicit policy changes |
| Model adapters | Optional sources of assessments; no execution authority |
| General prompt orchestration, fine-tuning, retrieval infrastructure and workflow builders | Outside current scope |

Keep existing public APIs and historical record compatibility. Narrowing priorities does not remove existing history, evaluation or model integrations. It does not move authority into a model or replace deployment authentication and credential isolation.

The current embedded SQLite runtime does not promise distributed coordination. Adapter code remains trusted. Preventing alternate execution paths and protecting audit against a fully compromised host require deployment work.

## Immediate deliverables and acceptance

The [release tools](release-tools.md) now provide bounded conformance checks and offline incident reconstruction using the existing integration API. The scope below records the intended deliverables; use that guide for actual coverage and limits. Broader feature expansion is frozen pending the independent adoption exercise.

1. **Minimum integration path.** Document one model-free SDK path with explicit caller, evidence, policy and executor responsibilities. Exercise it with refunds and access without changing core for either domain. Keep optional conveniences separate from the required contract.
2. **Conformance suite.** Let domain/executor authors run reusable checks for action binding, mandatory denials, review limits, expiry/staleness, resource contention, definitive failure, ambiguous success, restart and idempotent reconciliation. Report each applicable invariant and unsupported capability. A green happy path alone is insufficient.
3. **Incident reconstruction command.** Given a decision identifier, reconstruct its proposal, evidence versions, policy/review, authorization, execution attempts and known outcome from durable records. Distinguish customer-request status from execution status. Verify available audit integrity and expose gaps; never infer success from a missing response. Exclude reusable authorization credentials from exported output.

The reconstruction tool should answer: what was requested, what was authorized, against which facts and rules, whether that exact effect happened, and what remains unresolved. Ordinary tracing helps navigate to these records; lossy telemetry cannot establish execution truth.

## First adoption experiment

Hypothesis: an engineer unfamiliar with this implementation can add another consequential-action integration, change its policy and investigate an uncertain execution with less effort and comparable correctness than with an equally capable shared application library.

Use refunds and access for onboarding. Use a separate simulated domain for the measured integration, with authoritative evidence, a constrained resource, review and recoverable execution. Freeze its requirements and hidden test cases before the exercise; do not build the participant's solution into the starter. Concrete task materials, sample size, time limits and analysis choices must be finalized before data collection. This document is a study brief, not a registered or completed study.

Both arms may reuse libraries, transactions, signatures, logs, telemetry and development tools. Give both the same correctness and investigation requirements. Record onboarding separately from implementation, policy-change and investigation time. Preserve failures, assistance and unfinished tasks. An unsafe or incomplete integration cannot count as a time-saving success.

The [measurement plan](engineering-value.md) defines fairness and reporting requirements. Repeated executions are functional observations, not independent developer samples. A single participant can expose usability problems but cannot establish a general productivity advantage.

## Continue, revise or stop

Use the first exercise to discover missing contracts and friction. Treat tasks used to make fixes as development-informed. Require fresh tasks and independent integrations before generalizing a benefit.

Continue as an adoption-oriented framework if independent evidence supports useful gains at comparable correctness and acceptable operating cost. Narrow further if gains exist only in certain workflows. If the shared application baseline remains equally easy to use and investigate, keep this as a tested reference implementation without claiming that teams should migrate.

The five engineering outcomes remain evaluation dimensions. They do not justify expanding the product into unrelated abstractions. More classification or agent benchmark runs will not answer this adoption question.
