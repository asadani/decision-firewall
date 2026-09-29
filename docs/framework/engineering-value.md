# Engineering value and measurement plan

Decision Firewall focuses on an authorization and recovery runtime for consequential actions. The [product direction](product-direction.md) defines the scope and first adoption experiment. The five outcomes below evaluate that runtime; they are not separate product features. Proposals may originate from humans, programs or models; an assessment never grants authority.

Correct application controls and correct framework controls given equivalent inputs should produce equivalent decisions. Repackaging controls does not create an inherent accuracy or safety advantage. Adoption must justify the additional latency, dependencies, abstraction and shared failure risks.

## Product goals and evidence

None of the five benefits below has yet been established by an engineering study. Current capabilities support testing these hypotheses; their existence alone is not proof of benefit.

The bounded [conformance and investigation tools](release-tools.md) are now implemented. The table describes the wider measurement program; independent integration and timed investigation studies remain unrun. Feature expansion is frozen while gathering that evidence.

| Goal | Existing foundation | Next deliverable (planned) | Primary measurement |
|---|---|---|---|
| Faster integration | Domain hooks, model adapters, starter and two reference domains | Acceptance checklist and repeatable first/second-domain integration tasks | Active developer time to a conforming integration, completion rate and assistance required |
| Fewer omitted safeguards | Shared authorization/recovery lifecycle and adversarial tests | Reusable domain/executor conformance kit with independent integration tests | Missing safeguards and defects by severity per independent integration |
| Easier maintenance | Named versioned rules, offline comparisons and historical replay | Reproducible policy/adapter change tasks and compatibility checks | Change time, regressions and historical replay failures |
| Faster investigation | Linked signed records, receipts and optional telemetry | Domain-neutral incident reconstruction command/report and complete safe correlation metadata | Time to a correct explanation, answer completeness and incorrect conclusions |
| Consistent governance | Shared core used by refund and access examples | Contract tests across separate service integrations and configuration versions | Authorization, recovery and audit contract mismatches per applicable check |

The current runtime is embedded and uses local SQLite. Shared behavior across integrations does not establish distributed atomicity or centralized enforcement. Those need deployment-specific designs and separate validation.

## Responsibilities and adoption

The framework owns the common lifecycle: validated records, review processing, bound authorization, resource reservation, dispatch/reconciliation tracking and signed audit. Domain authors supply authoritative evidence, business rules, resource definitions and executors with durable idempotency. Deployments supply identity, credential isolation and enforcement that prevents bypassing the governed path.

Telemetry helps locate an operation and measure its behavior. Durable audit records support reconstructing the decision; lossy asynchronous telemetry cannot substitute for required audit. Historical evaluation helps test changes before explicit adoption. Neither history nor model confidence can waive mandatory checks.

The intended audience is teams repeatedly implementing these requirements across workflows. An existing application with complete controls and effective investigation tools may gain little from migration. A small application may reasonably prefer its existing controls. Integration and migration effort, operating costs, upgrade compatibility and shared-core defects belong in the adoption decision.

## Fair comparison protocol

Compare the framework against a competent modular application implementation with the **same requirements**. The application baseline may use shared libraries, reusable controls, database transactions, signatures and telemetry tooling. Do not require duplication to make reuse look better. Keep direct model routing only as a diagnostic arm, not the primary engineering baseline.

Before recruiting participants or collecting results, freeze the task specifications, correctness criteria, evaluation cases, time limits, sample size rationale, primary endpoints and analysis method. Record participant experience, prior familiarity, tool/AI assistance, training and environment. Use independently authored integrations and independent scoring where feasible. Counterbalance equivalent tasks and ordering to reduce learning effects; retain failed and incomplete attempts.

Measure setup/training, active implementation, debugging and elapsed waiting separately. Report first-use and subsequent-use costs separately, including framework-specific work moved into domain adapters or configuration. Any claimed time benefit requires comparable correctness and completion; a fast unsafe or incomplete submission is not a successful integration. Report individual invariant failures even when aggregate results look favorable.

### Integration and safeguard tasks

Give builders equivalent refund and access requirements, then an unfamiliar third domain. Include review, evidence versions, expiry, original action binding, resource contention and ambiguous execution outcomes where applicable. Publish acceptance requirements while keeping concrete adversarial test cases separate from implementation guidance. Apply the same cases to both arms. Count independently built integrations as the sampling unit; repeated requests do not become independent developer observations.

### Maintenance tasks

Start from conforming integrations. Apply predeclared changes such as a review threshold, a new mandatory evidence field, and an executor reconciliation contract change. Measure time to pass both new and retained requirements, including replay of old policy versions and verification of existing receipts. Report regressions and migration effort, not just changed lines of code.

### Investigation tasks

Use matched incidents: a lost success response, a stale authorization, concurrent resource claims and a rejected execution attempt whose customer request remains open. Give investigators the normal tools and records available in each implementation. Ask them to identify what was requested, which evidence/policy applied, who authorized it, whether the effect occurred and what recovery is needed. Score against a frozen answer key and measure time to a correct reconstruction. Do not withhold equivalent logs from the application arm.

### Consistency tasks

Run the same lifecycle contract against separately integrated services, including restart and policy-version changes. Compare authorization bindings, unknown-outcome handling and required audit fields. Compare shared lifecycle invariants, not legitimate domain-policy differences. Record adapter and deployment failures as well as core failures. Do not infer cross-service transactional guarantees from matching local behavior.

## Reporting and decision gates

Publish a manifest with code/configuration hashes, environments, task versions and any protocol deviations. Report raw anonymized task observations where permitted, denominators, failures, missing data, uncertainty and paired comparisons when the design supports pairing. Keep participant data and credentials out of repository artifacts.

Predeclare any adoption thresholds before observing the study. Do not collapse time, safety and investigation quality into a score that hides failures. Lines of code, API counts and demonstration success are supporting descriptions, not developer productivity measurements. Mark tasks used to improve the framework as development-informed and use fresh held-out tasks for subsequent claims.

The release priorities are in the [roadmap](../../ROADMAP.md). Existing [refund](../benchmarks/post-review-refund/summary.md), [observability](../benchmarks/post-review-observability/summary.md), [classification](../benchmarks/paired-public/summary.md) and [agent](../benchmarks/agent-pilot/summary.md) reports establish their stated scenario results and costs. They do not establish the human engineering outcomes in this plan.
