# History → evaluated configuration

v0.3 adds a file-based developer workflow around the same deterministic gate used by runtime authorization. No external service, model download, web dependency or execution adapter is needed to evaluate cases. Historical decisions are observations, not ground truth or permissions.

## A runnable starting point

With the core installed from this checkout:

```sh
firewall init my-decision-app
python my-decision-app/run.py
python my-decision-app/workflow.py
```

The first script executes a simulated document action through review. The second imports `history.jsonl` using `mapping.json`, adds independent expected labels, declares three splits, and compares two named rule configurations with a custom evaluator. Open `my-decision-app/.runtime/experiment/report.html`. The candidate intentionally removes required review and fails a threshold declared before execution; the script asserts this expected failure. It never promotes the candidate.

From the generated directory:

```sh
python -m decision_firewall.cli history validate history.jsonl --mapping mapping.json --home .runtime/history
python -m decision_firewall.cli policy inspect --plugin plugin:create_policy
python -m decision_firewall.cli experiments run experiment.json .runtime/validation
python -m decision_firewall.cli experiments compare .runtime/validation .runtime/validation
```

Use `python -m` from that directory so local `plugin.py` and `evaluators.py` are importable. Installed plugin modules work with `firewall` directly. Output directories must be new; snapshot files are created exclusively. Both CLI and SDK reject overwriting a previous experiment.

## Import and curate

`decision_firewall.history` exports `HistoryStore`, `HistoryMapper`, `FieldMapper`, `HistoricalDecision`, `ExpectedLabels`, `SnapshotCase` and `DatasetSnapshot`.

| Data | Meaning |
|---|---|
| `proposal` | Original request and proposed domain action |
| `evidence`, `evidence_available_at` | Facts available at the recorded decision time |
| `assessment` | Recorded model output, including model/revision and signal semantics |
| `historical_decision` | What the previous system decided, including mistakes |
| `review`, `review_available_at` | Review actually available to that decision |
| `outcome`, `outcome_available_at` | Later observations; excluded from policy/model inputs |
| `usage` | Explicit resource-state snapshot; `{}` means a known empty state, `null` means unknown |
| `source`, `source_id`, `source_revision` | Provenance and revision identity |
| `decision_at`, `available_at` | Unix UTC seconds; missing timestamps stay missing |
| annotations | Later reviewed expected labels with reviewer, reason and availability |

JSONL can contain the contract directly. CSV and differently shaped JSONL use an explicit mapping: target dotted field → source dotted field. `json_fields` explicitly decodes JSON strings in selected cells; `constants` supplies declared metadata. Missing mapped fields are errors. A trusted Python mapper can implement `__call__(row) -> HistoricalDecision` for date conversion or application schemas. Do not guess missing facts or translate blank values into approvals.

```python
from decision_firewall.history import HistoryStore, ExpectedLabels

history = HistoryStore(".runtime-history")
preview = history.import_file("historical.jsonl", dry_run=True)
assert preview["valid"], preview["errors"]
result = history.import_file("historical.jsonl")
case_id = result["record_ids"][0]
history.annotate(case_id, ExpectedLabels(disposition="REQUIRE_REVIEW"),
                 reviewer="curator", reason="Reviewed expected behavior", available_at=2000)
snapshot = history.snapshot("refund-policy-cases", {"development": [case_id]})
snapshot.save("dataset.json")
```

Imports are atomic. A malformed row or conflicting explicit source revision rolls back the entire import and returns row errors. Repeated identical imports reuse IDs. Changed content under a new revision links to the previous record; with no source revision, the canonical content hash is the revision identity. Annotations append; snapshots pin the selected annotation. History uses `history.db`, separate from runtime governance storage. Importing an approval creates no authorization, effects, signatures or locally verified receipts.

CLI groups expose `history validate/import/inspect/annotate` and `datasets create/validate/inspect/mark-informed`; use each command's `--help` for arguments. Membership files map `development`, `validation`, `evaluation` to explicit record IDs. A case belongs to one split. Canonical request duplicates and revisions of the same source cannot cross splits. `--group-by customer` or `case_family` also prevents mapped groups crossing splits. This detects exact normalized request duplicates, not semantic paraphrases; curate families explicitly.

## Compare changes without executing them

`decision_firewall.experiments` exports `EvaluationCase`, `EvaluationPolicy`, `ExperimentSpec`, `ExperimentVariant`, `ExperimentRunner`, `Evaluator`, `Score`, and `ExperimentResult`.

Policy mode reuses the recorded assessment, evidence, review, usage and time. Model mode replaces only the assessment, optionally using permitted context. Both use `core.policy.evaluate_context`, the runtime gate. Missing time, evidence availability, usage or required recorded assessments produce incomplete results. Evidence/reviews from the future cannot be used. Ordinary Python policies remain supported.

The runner receives a capability-limited `EvaluationPolicy`, not a runtime: no resolver, permit issuer, governance database or executor is passed. Built-in CLI policies are constructed in temporary isolated simulator directories. Plugins, mappers and evaluators are trusted Python code; this is capability separation, not an OS sandbox against malicious callbacks or closures.

```json
{
  "dataset": "dataset.json",
  "spec": {
    "name": "access-duration", "mode": "policy", "split": "validation", "seed": 42,
    "thresholds": [{"metric": "false_allows", "maximum": 0}]
  },
  "variants": [
    {"name": "baseline", "domain": "access", "policy": {"automatic_max_hours": 8}},
    {"name": "more-review", "domain": "access", "policy": {"automatic_max_hours": 2}}
  ]
}
```

For refunds use `domain: "refunds"` and parameters such as `auto_amount_minor`, `daily_auto_limit_minor`, `cancellation_days`. Amounts are integer INR minor units. Run both SDK examples from the checkout:

```sh
python examples/workbench/run.py .runtime-comparisons
```

These synthetic examples show a lower automatic threshold changing an otherwise eligible case to review. They are workflow checks, not accuracy benchmarks. Existing historical files under `evaluations/` are unchanged; their old measurements are not v0.3 results.

Model variants add `model: {"kind": "fixture", "assessment": {...}}`, or `kind: "laya"` with typed `questions` and `device`. External models declare an installed `factory` and explicit `manifest`. Named variants can change questions, policy and context independently; use controlled comparisons when attributing changes. Laya loads lazily, one checkpoint at a time, and is released between variants. Python randomness is seeded; adapters can implement `set_seed(seed)`. Arbitrary providers may still be nondeterministic and must disclose that in their manifests.

Custom evaluators implement `name`, `version`, and `__call__(case, observation) -> list[Score]`. Mark boolean invariant results with `hard_invariant=True`. Individual failures remain in observations and fail the experiment independently of aggregate metrics. Evaluator exceptions fail the case. The generated evaluator demonstrates the contract.

Artifacts contain a pre-execution manifest, pinned dataset, JSON/CSV observations, Markdown summary and self-contained HTML comparison with case-level rule explanations. Reports record code hash, package/platform, dataset hash, complete variant policy/model/retrieval settings, evaluator versions, seed and thresholds. External callback source is outside the package code hash: supply meaningful immutable versions and manifests. Wall latency, model metadata, RSS when psutil is installed, and CUDA allocation when already loaded are reported; unavailable measurements are null. Latency and resource observations are not deterministic. Decision results should reproduce under identical pinned inputs and deterministic implementations.

Agreement, false allows/blocks and review rate expose denominators; historical agreement is separately labeled diagnostic. Signals retain choice accuracy, binary Brier/fixed ten-bin calibration, or ordinal absolute error. Missing labels and labeled-but-unscored signals are counted separately. Confidence is uncalibrated. Thresholds apply to named scalar summary fields and must specify bounds; missing metrics fail. CLI returns 2 for incomplete/error/invariant/threshold failure, while preserving reports. No threshold is invented after results are seen.

## Historical context

`decision_firewall.context` exports `HistoryRetriever`, `LexicalHistoryRetriever`, `ContextAwareModel`, `AssessmentInput`, `HistoricalExample`, `ContextualModel` and `RenderedContextModel`.

Explicit context settings in an experiment variant:

```json
{"context": {"reference_ids": ["a-development-record-id"], "limit": 3, "budget": 4096}}
```

Lexical ranking is deterministic token Jaccard similarity with record ID tie-breaking; default maximum is three positive-overlap examples from the same domain. Reference pools must consist only of development records. Self/source revisions, held-out records, duplicate requests, future records and unknown availability times are excluded. Both decision and availability times must strictly precede the current case. Replaceable retrievers must declare `reference_ids` in `manifest()`; the contextual wrapper validates returned examples against pinned records and these boundaries again.

Examples contain original request, historical disposition and version metadata. They contain no later outcomes, annotations or authoritative evidence. They remain untrusted model context and cannot change eligibility or satisfy evidence requirements. Ordinary `assess(message)` remains unchanged. Context providers implement `assess_context(AssessmentInput)`; `RenderedContextModel` is explicit opt-in for a message-only provider.

The complete current request is retained. Oversized current input fails. Optional examples are omitted whole to fit the budget and their IDs/reasons are recorded, alongside selected versions, retrieval configuration and rendered-input hash. Default units are characters; Laya uses its tokenizer with the existing 256-token current-state limit and 192-token question-template limit.

## Adopt explicitly

Edit named policy/model/question/context variants, compare on development and validation, then run the frozen evaluation split once configuration is selected. Manually adopt the exact tested configuration in application setup and retain its manifest/hash. There is no promotion API or automatic policy learning. If held-out results guide fixes, use `datasets mark-informed original.json new.json "reason"`; this creates a linked development-informed snapshot. The framework cannot infer what a human has seen, so accurate marking is the operator's responsibility. Historical replay verifies a recorded implementation; counterfactual experiments evaluate another configuration and never overwrite replay history.
