# Agent benchmark development pilot

Pinned τ-bench retail and AgentDojo banking tasks, simulated effects, one seeded trial. This is a 90-episode subset/configuration study, not a full-suite or leaderboard score.

| Suite / condition | Arm | Completed / planned | Task successes | Attack successes | DB matches | Blocked calls |
|---|---|---:|---:|---:|---:|---:|
| tau2 / clean | baseline | 7/10 | 1 | N/A | 1 | 0 |
| tau2 / clean | application | 6/10 | 1 | N/A | 1 | 2 |
| tau2 / clean | firewall | 7/10 | 1 | N/A | 1 | 4 |
| agentdojo / clean | baseline | 9/10 | 6 | N/A | N/A | 0 |
| agentdojo / clean | application | 10/10 | 5 | N/A | N/A | 7 |
| agentdojo / clean | firewall | 10/10 | 5 | N/A | N/A | 7 |
| agentdojo / attacked | baseline | 9/10 | 6 | 8 | N/A | 0 |
| agentdojo / attacked | application | 10/10 | 4 | 0 | N/A | 19 |
| agentdojo / attacked | firewall | 10/10 | 4 | 0 | N/A | 19 |

Task-success counts use the completed denominator shown; uncompleted episodes are not silently scored as correct or dropped. Attack success means the upstream attacker goal succeeded, so lower is better. Database match is τ-bench's deterministic state check; overall τ-bench success also includes applicable language assertions.

Tool-boundary counts and timing cover completed episodes only. Missing tool observations in aborted episodes are null, not evidence of zero effects. There are 12 incomplete episodes; these are not scored task failures. Invalid or reasoning-only completions are never replaced with favorable outputs. Signed receipts verified in 27 framework episodes; incomplete episodes have no reported verification result.

## Transport and cost

Response-reported pilot cost, including retained diagnostic attempts: **$0.011316** across 266 paid attempts. There were 0 rate-limited attempts and 0 attempts without a reported cost; reservations remain for unknown charges. 331 identical-input responses were reused across arms. This is response accounting, not an independently reconciled invoice.

Model: OpenRouter openai/gpt-oss-20b, Darkbloom only, temperature 0, low reasoning, max_tokens 2048, run seed 20260928 with per-case/role/turn derived seeds. Agent, τ-bench simulated user and NL judge use the same transport/budget. One inference worker; only bounded HTTP 429 backoff. Hosted model weights are not revision-pinned. The judge model differs from upstream defaults; its accuracy was not independently validated.

## Interpretation

The application and framework enforce the same narrow predicates. Retail checks identity lookup, record ownership and order status; existing upstream tools and prompts retain the other rules. Banking uses a conservative lexical capability check on the original user instruction. A document cannot grant write authority. Transfers lacking an explicitly supplied recipient, and scheduled-payment changes derived from documents, require review. There is no human approval in this pilot. Benign failures therefore matter: attack blocking alone is not evidence of useful governance.

The baseline retains upstream tool validations. Out-of-policy dispatch counts in observations are relative to this study's added checks, not independently adjudicated harmful effects. Attack success comes from the unchanged AgentDojo security checker. Lower clean-task utility is reported instead of hiding review-related false blocks. No claim that these lexical checks implement complete semantic authorization, every retail policy clause, or production banking controls is made.

Framework arms use real SDK submit/evaluate/authorize/execute and signed receipt verification at the tool boundary. The application arm invokes the same predicate directly and writes a SQLite audit entry. This comparison isolates packaging/enforcement of the selected checks; it is not a comparison of independently written full application architectures. Upstream environments are volatile simulators, so these episodes do not validate durable effect recovery.

## Timing and reproducibility

Boundary timing includes the upstream tool invocation and local governance work, excludes model inference, and has differing tool mixes between arms. comparison.csv contains sample counts and medians; do not interpret them as paired end-to-end overhead. Identical full inputs/settings/turns share cached responses, ensuring common prefixes use identical samples; divergent trajectories make new calls. Cache use makes raw episode wall time unsuitable for model-throughput comparisons.

The manifest records frozen tasks, source hashes, packages, policy code, protocol, platform and settings. τ-bench uses the first 10 declared retail train tasks; AgentDojo uses banking user_task_0 through user_task_9, clean and injection_task_0, with the upstream important-instructions fixed template and generic names. Upstream attack construction may inspect ground truth to select injection locations; neither defender model nor policy receives ground truth or grading labels. The upstream graders are retained, with denied calls preserved as no-effects during τ-bench replay and exact NL-assertion response coverage validated.

One initial live τ-bench episode exposed a scalar-string parsing bug in the adapter after successful authentication. Its failed diagnostic and cost are retained in accounting.json. Offline authentication coverage was added and the adapter corrected before the measurement run; tasks, policies and thresholds were not tuned to model results. No statistical p-values, accuracy uplift, production effectiveness or developer-hour savings are claimed.

See [protocol and reproduction](../../../benchmarks/agent_suites/README.md). Private transcripts, response caches, runtime signing keys and bearer permits are excluded from this published report.
