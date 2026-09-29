# Roadmap

The product is a reusable authorization and recovery runtime for consequential actions. See the [scope and adoption experiment](docs/framework/product-direction.md). Integration effort, safeguard completeness, maintenance, investigation and consistency are measures of its value, not separate product lines.

## Release-candidate delivery

The [conformance and investigation tools](docs/framework/release-tools.md) are implemented: a 17-check simulated fixture runner and offline reconstruction from verified receipts. Existing integration interfaces remain unchanged. These tools have bounded coverage and do not certify production integrations.

**Next: freeze feature expansion and run an independent adoption exercise.** No additional domain or paid benchmark expansion is scheduled in this phase.

## Delivery sequence and adoption plan

1. **Small integration contract.** Document and exercise the minimum stable SDK path for proposal, evidence, policy, authorization, execution and reconciliation. Preserve existing APIs; defer new abstractions until an integration requires them.
2. **Reusable conformance suite — delivered.** The simulated runner tests bound actions, mandatory constraints, stale authorization, resource contention, idempotency and recovery. Deployment/access reference fixtures demonstrate extension; unsupported cases remain visible.
3. **Incident reconstruction — delivered.** The offline command links proposal revisions to evidence/policy references, reviews, authorization, attempts and outcomes. It verifies receipt integrity and reports gaps and uncertainty. Broader telemetry metadata changes remain deferred; reconstruction depends on durable records.
4. **One adoption experiment.** Freeze a protocol, then ask an engineer unfamiliar with the implementation to integrate another use case, change a policy and investigate an ambiguous execution. Compare with an equally capable shared application library. Measure correctness and effort together, following the [measurement plan](docs/framework/engineering-value.md).

Pause broader feature expansion until this exercise identifies a concrete need. The independent study requires a participant and frozen task materials; existing automated benchmarks cannot stand in for that evidence. If adoption shows no useful benefit, retain the project as a reference implementation rather than claiming a framework advantage.

Existing functional and adversarial tests remain release gates. More model-accuracy benchmarks are not the primary evidence for these engineering goals. New abstractions should support a concrete integration requirement; retain existing SDK/domain APIs and avoid unnecessary migration.

## Implemented in 0.3

- Third-domain [simulated deployment exercise](docs/framework/deployment-example.md): existing plugin API, atomic registry checks, production review, resource slots and restart recovery. This is development-informed functional evidence, not an independent adoption study.
- File history import, immutable datasets and independent reviewed labels.
- Offline model/policy variants, explicit thresholds, custom evaluators and HTML reports.
- Named mandatory/review rules and retained previous policy implementations.
- Optional historical context with time/split/budget protections.
- Optional bounded OpenTelemetry export and Langfuse setup guide.

## Implemented in 0.2

- Domain-neutral contracts/runtime and explicit plugin interfaces.
- Refund and temporary-access domains using the same lifecycle.
- Configurable Laya questions, callable/fixture model adapters.
- Generic CLI, custom-domain starter, receipts, replay and reconciliation.
- Optional inspector/model dependencies and v0.1 compatibility.

## Deferred — outside the next delivery

- Generic inspector driven by domain metadata/form schemas.
- Versioned database migrations and explicit v0.1 import tooling.
- Production executor integrations beyond the planned model-free conformance kit.
- Deployment authentication, external audit anchors and distributed reservations.
- Independent evaluation datasets and substantive procurement example.
- Package publication, release automation and private security reporting.

General prompt orchestration, model tuning infrastructure, general retrieval and a workflow builder are outside the product scope. Existing history/evaluation/model integrations remain supported; expanding them is not the next priority.

No dates are promised. Publishing and real financial execution require separately scoped work.
