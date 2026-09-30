# Evaluation protocol (public, non-sensitive part)

Frozen on 2026-09-29, before any builder ran. The held-out test cases, the maintenance-change
details and the incident answer key are sealed and are not described here.

## Question

When two builders implement the same new consequential-action workflow (the simulated
purchase-order workflow in REQUIREMENTS.md), does building on Decision Firewall (DF) change
completion, correctness, maintenance effort or investigation quality, compared with an
ordinary application implementation?

This is **one paired diagnostic pilot**, not a statistical study. It can expose friction,
missing contracts and failure modes. It cannot establish a general productivity or safety
advantage. **No numerical improvement thresholds are predeclared, and none will be used to
declare a winner.**

## Arms

| Arm | Builder | May use |
|---|---|---|
| C (framework) | agent C | DF source, docs and public guides (read-only snapshot), plus ordinary libraries |
| D (baseline) | agent D | Ordinary libraries only (sqlite3, cryptography, pydantic, stdlib logging, pytest, ...); no DF |

Both arms get the same model, tools, tool budget, REQUIREMENTS.md, ADAPTER.md, harness,
visible tests and BUILDER-BRIEF.md. The only difference in their instructions is a short
arm-specific note.

**Recorded context asymmetry:** arm C may read DF documentation and source. Arm D gets only
the requirements and harness. Arm C therefore has more material to read, and also
ready-made components.

Python 3.12 environments: `venv-framework` (DF installed) for C and `venv-baseline` for D.
Otherwise the packages are identical. No installs are allowed.

## Phases

1. **Build.** Each builder gets one agent run with a maximum of **300 tool calls**. Builders
   are told to stop and hand off whatever state they have reached. Tokens are recorded, not
   capped.
2. **Scoring.** The evaluator runs visible and held-out tests through the common harness via
   each arm's adapter factory.
3. **Maintenance.** A predeclared policy change (details sealed until this phase) is handed to
   a maintainer of each arm. Scoring covers the new tests plus regressions on the original
   tests.
4. **Investigation.** Deterministic incident scenarios are run against each implementation.
   Investigators get only the artifacts an operator of that implementation would normally
   have and answer fixed questions. Answers are scored against a frozen answer key.

## Tests

* **Visible:** `public/tests/`, 26 test cases covering the basic path of each requirement.
* **Held-out:** sealed. They use the same harness and the same `PO_ADAPTER` loading mechanism.
  They cover edge cases and every hard invariant, including concurrency stress, crash and
  restart windows, binding, expiry and revocation, idempotency conflicts, and audit contents
  and tamper detection.
* Each test is tagged with a requirement id and either a hard invariant (HI-1 to HI-6) or
  "functional".
* After every test, the harness judges the outcome against the authoritative downstream effect
  store and records, not only against returned statuses.

## Primary measurements (reported per arm, never collapsed into one score)

1. Completion status: complete, partial, or not runnable.
2. Visible pass count and held-out pass count, with denominators.
3. A list of individual hard-invariant test failures, with test id and invariant.
4. Agent tokens, elapsed time and tool calls where available; otherwise null.
5. Framework core changes and workarounds, from BUILD-LOG.md and a diff against the
   read-only snapshot.
6. Maintenance: completion, new-test pass counts, regressions, and effort.
7. Investigation: score out of 48, number of incorrect conclusions, and any artifact gaps.

## Handling incomplete work

* Implementations are scored as handed off.
* A test that errors, times out, or needs a missing operation counts as failed.
* There are no reruns and no fixes by the evaluator. Any rerun that happens for an
  infrastructure reason is reported separately, labelled, and alongside the original result.
* A missing adapter or factory means every test fails.
* Builders' own tests and claims are reported but not scored.

## Integrity

* The protocol, harness, visible tests, held-out tests, maintenance change and answer key are
  hashed (`MANIFEST.sha256`) before the build phase.
* Any later protocol deviation is recorded and reported.
