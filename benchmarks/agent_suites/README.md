# Pinned agent benchmark integrations

The adapters run upstream τ-bench retail and AgentDojo banking tasks through three
arms: upstream baseline, explicit application boundary checks, and the same checks
through Decision Firewall. All effects remain in upstream simulators. These are
optional benchmark dependencies, never core runtime dependencies.

The frozen [pilot protocol](protocol.json) declares **90 episodes**: 10 retail train
tasks × three arms; 10 banking tasks × clean/one fixed attack × three arms. This is
not a full-suite result or leaderboard submission. No accuracy/safety pass threshold
was selected after seeing results.

## Install and validate

Use a separate Python 3.12 environment from the repository root:

```console
python -m benchmarks.agent_suites.prepare
python -m venv .runtime-agent-env
.runtime-agent-env/Scripts/python.exe -m pip install -r benchmarks/agent_suites/requirements.lock
.runtime-agent-env/Scripts/python.exe -m pip install --no-deps .runtime-agent-sources/tau2 .runtime-agent-sources/agentdojo .
.runtime-agent-env/Scripts/python.exe -m benchmarks.agent_suites.validate_integrations
```

On Linux use `.runtime-agent-env/bin/python` in place of the Windows executable.
The preparation command verifies pinned source blobs against the upstream tree and
retains MIT license files. Optional voice/model-download dependencies are omitted.
The integration validation uses fixture responses and the actual upstream graders,
including successful retail authentication and a banking attack that succeeds in
the baseline and is blocked in both governed arms. It makes no inference calls.

| Suite | Revision | Configuration |
|---|---|---|
| sierra-research/tau2-bench | b7ea9074c1cba482b30687fecdb5c8425fd6f619 | retail train; upstream agent/user/orchestrator/evaluators |
| ethz-spylab/agentdojo | 089ed468cf3ed0322acc66b0211f26d9d90dbf60 | v1.2.2 banking; upstream tools and utility/security graders |

τ-bench retail has 114 base tasks (74 train, 40 test); this pilot covers 10 train
tasks. AgentDojo banking v1.2.2 has 16 user tasks and nine injection goals; this
pilot covers 10 user tasks and injection_task_0 using the upstream fixed important
instructions template with generic user/model names. Other domains and attacks
are outside this pilot. Laya cannot fill the conversational agent/user roles.

## Run with the authorized capped key

Store OPENROUTER_API_KEY in the ignored local `.env`. Never publish it.

```console
.runtime-agent-env/Scripts/python.exe -m benchmarks.agent_suites.runner --output .runtime-agent-pilot-new
```

The default budget database is `.runtime-agent-sources/openrouter-budget.db`.
**Reuse it across all runs, agent/user/judge calls, and retries. Never reset it to
resume.** The key must have the authorized non-resetting $5 limit. A $0.01 opening
reserve covers earlier probes and delayed billing. Each outbound attempt reserves
worst-case context cost; response-reported cost settles it. Unknown costs retain
reservations. Price overruns block subsequent calls. This is not invoice reconciliation.

Requests pin `openai/gpt-oss-20b` to Darkbloom, no fallback, temperature zero, low
reasoning, max_tokens=2048, and seed 20260928 with a case/role/turn-derived seed.
One worker runs sequentially. HTTP 429 alone receives up to four attempts with
exponential jittered backoff and Retry-After handling; waits over 60 seconds defer
the run. Redirects, incomplete output, wrong providers/models and malformed tool
envelopes are rejected. Ambiguous network failures are not blindly retried.

Identical complete messages/tools/settings/logical turns share a private response
cache across arms. Divergent histories generate new calls. This controls common
prefix randomness and saves cost; it makes wall-clock episode times unsuitable
for model throughput claims. A provider seed remains best-effort reproducibility.
The hosted model checkpoint cannot be revision-pinned.

Completed and failed episodes are retained. A rerun of the same command skips both,
checks an unchanged manifest and refuses to overwrite an interrupted episode. Inspect
interrupted state before taking action. Changing code requires a new output directory;
retain old diagnostics. Never selectively retry failures to improve scores.

## What the comparison enforces

`boundary.py` has no task objects, expected actions, attack goals or grading labels.
It receives the proposed tool/arguments and trusted host-selected evidence:

- Retail: identity established by an upstream email/name+ZIP lookup; one customer;
  profile/order ownership; pending/delivered status for relevant operations.
- Banking: write capabilities derived lexically from the ORIGINAL user instruction.
  Tool/document content cannot grant new capabilities. A payment recipient absent
  from that instruction, or a scheduled payment change derived from documents,
  requires review. No human reviewer is simulated, so this can reduce benign utility.

These are narrow demonstration policies, not full semantic authorization. Remaining
retail rules still rely on upstream tool validations and the agent's policy prompt.
The baseline retains those upstream protections. Application and framework arms
share predicates to isolate integration differences; the application writes SQLite
audit, while the framework performs actual submit/evaluate/authorize/execute and
signed receipt verification. The model never receives authority or task solutions.

AgentDojo's upstream ATTACK constructor uses ground truth to select injection
locations. That information is available only to attack generation and grading,
never to the defender policy or agent. τ-bench graders retain their original logic;
replay treats recorded blocked calls as no-effects, while expected/gold actions are
unchanged. Its NL judge also uses the capped model, with exact assertion coverage
validated to prevent an empty result list from becoming a passing grade. Report DB
matches separately because this cheaper judge differs from upstream defaults.

Upstream environments are volatile simulations. This adapter does not establish
crash durability, production authentication, or complete financial controls. See the
separate refund/recovery benchmarks for durable simulator tests.

## Reports

```console
python scripts/report-agent-pilot.py .runtime-agent-pilot-new docs/benchmarks/agent-pilot-new --diagnostic .runtime-agent-pilot-old
```

Publish only the selected aggregate JSON/CSV, manifest, Markdown and standalone
HTML. Private trajectories, response caches, runtime signing keys and permits stay
ignored. Reports include coverage, clean utility, attack success, missing/error
outcomes, boundary timing, signed receipts, tokens, response costs and retained
failed diagnostics. Lower clean utility must remain visible alongside attack blocks.

The earlier OpenRouter echo probes validated connectivity only. BANKING77/Bitext
classification studies are separate and cannot substitute for these agent episodes.
