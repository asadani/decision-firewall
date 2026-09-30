# Public evidence and claim boundaries

Current disposition: **narrow to a tested reference implementation and conformance kit**.
There is no established adoption, migration, accuracy, safety or productivity advantage
over equivalent competent application controls. All financial and deployment effects
in the examples and evaluations are simulated.

| Claim or question | Evidence | Boundary |
|---|---|---|
| Agent integration, maintenance and investigation | [Independent paired pilot](evaluations/2026-09-29/COMPARISON.md), [numerical observations](evaluations/2026-09-29/results/observations.json), [CSV](evaluations/2026-09-29/results/observations.csv) | One task/run per arm; correctness tied; effort differences not statistical evidence; investigator CLI unavailable; human productivity untested |
| Framework execution cost in that pilot | Same comparison: 39.6 s versus 4.5 s for the held-out suite | Approximately 9× suite time, not universal request latency; global write lock remains |
| Independent defects and limitations | [21 findings](evaluations/2026-09-29/findings.md) | Four confirmed defects; design limits and unverified concerns kept distinct; original snapshot predates fixes |
| Corrective behavior | [0.3.1 verification](verification/0.3.1/README.md), [nine-fault mutation results](verification/0.3.1/mutations.json), regression tests | 298 local tests with optional telemetry; nine specific mutation classes, not exhaustive fault coverage; fixes are not a rerun of the adoption pilot |
| Simulated refund safeguards and recovery | [Post-review paired results](benchmarks/post-review-refund/summary.md) | Both governed arms pass selected synthetic cases; no unique safety benefit demonstrated |
| Telemetry/reuse | [Post-review observations](benchmarks/post-review-observability/summary.md) | Instrumentation, export failure and runtime costs; not developer hours or investigation time saved |
| Classification | [BANKING77/Bitext comparisons](benchmarks/paired-public/summary.md) | Same classifier accuracy across arms; framework/preparation adds cost; source/split denominators differ |
| Tool-using agents | [τ-bench/AgentDojo pilot](benchmarks/agent-pilot/summary.md) | 90 scheduled, 78 scored, 12 incomplete; selected domains/attack, not full suites or leaderboard results |
| Domain-neutral interfaces | [Deployment exercise](framework/deployment-example.md) | Third domain needed no core changes; implementation by the framework author, not independent productivity evidence |

## Documentation and reproduction entry points

- [Agent guide](framework/agent-guide.md), [domain tutorial](framework/build-a-domain.md), [SDK/CLI](framework/api.md) and [executor contract](framework/executors.md).
- [Conformance/investigation commands](framework/release-tools.md) and [0.3.1 migration](framework/migration.md).
- [Architecture](framework/architecture.md), [threat model](threat-model.md), [security reporting](../SECURITY.md) and [reference assessment](reference-assessment.md).
- Benchmark source directories carry their own protocols, dependency pins and report-generation commands. Historical outputs retain their measured versions; do not interpret old reports as reruns of 0.3.1.

## Public artifact scope

The [independent evaluation artifact index](evaluations/2026-09-29/README.md) describes
the unchanged numerical results, scoring files, task documents and source/protocol hashes
included here. The public selection is not the full raw agent study archive. Original
machine paths in historical reports identify the evaluator's environment, not portable
reproduction commands. No new study was run to prepare this publication.

Credentials, runtime signing keys, bearer permits, databases, model weights, raw
conversation trajectories and large per-row exports are excluded. Benchmark runners
can regenerate supported local artifacts; externally hosted model outputs need not
reproduce bit-for-bit. Published hashes identify artifacts, not independent attestation.

Earlier plans and self-reviews are historical context. The independent findings,
corrective-release notes and explicit limitations take precedence over old aspirational
language. The legacy refund workbench has a separate lifecycle and is not covered by
all generic-runtime fixes. No certification, production security or distributed
coordination guarantee is claimed.
