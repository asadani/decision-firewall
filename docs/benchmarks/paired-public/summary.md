# Full-data before/after results

For the unchanged classifier on these datasets, the framework produced no accuracy gain. It added measured latency. Preparation also supplied signed records, but those records are not needed to improve a pure intent classifier. These results do not establish whether governance improves an agent's actions: no action-execution benchmark was run here.

Measured on Windows, Python 3.12.14, Intel i5-9300H, approximately 8 GB RAM. CPU naive Bayes, not Laya. Optional external telemetry disabled. One full pass with paired shuffled arm order. The desktop was not an isolated performance lab; treat latency as local measurements, not production guarantees or statistical significance evidence.

## All source rows are accounted for

| Dataset / evaluation | Rows | Direct accuracy | SDK assessment accuracy | Prepared accuracy | Prediction changes |
|---|---:|---:|---:|---:|---:|
| banking77-official-test | 3,080 | 78.60% | 78.60% | 78.60% | 0 |
| banking77-training-oof | 10,003 | 78.10% | 78.10% | 78.10% | 0 |
| bitext-all-oof | 26,872 | 98.31% | 98.31% | 98.31% | 0 |

Total: 39,955 source rows and 119,865 measured arm observations. BANKING77 contributes all 13,083 rows; Bitext contributes all 26,872 rows. This does not pool training-fold predictions with the official BANKING77 test score. The official 3,080 test cases use a model fitted on all 10,003 original training rows. The additional training-row score uses five out-of-fold models fitted without each evaluated fold. Official test examples are never used for fitting.

All Bitext rows receive one held-out prediction using our five-fold split. It has no publisher-supplied test split here, so this is not a standard leaderboard score. Only the instruction text reaches the model. Response text, coarse category, flags and expected intent are excluded from prediction input.

## Measured latency

| Dataset | Path | n | p50 ms | p95 ms | Paired median added ms |
|---|---|---:|---:|---:|---:|
| banking77-official-test | direct | 3,080 | 0.522 | 1.159 | 0.000 |
| banking77-official-test | framework_assess | 3,080 | 0.606 | 1.260 | 0.075 |
| banking77-official-test | framework_prepared | 3,080 | 14.092 | 16.543 | 13.527 |
| banking77-training-oof | direct | 10,003 | 0.538 | 1.262 | 0.000 |
| banking77-training-oof | framework_assess | 10,003 | 0.626 | 1.379 | 0.081 |
| banking77-training-oof | framework_prepared | 10,003 | 14.252 | 18.104 | 13.672 |
| bitext-all-oof | direct | 26,872 | 0.235 | 0.476 | 0.000 |
| bitext-all-oof | framework_assess | 26,872 | 0.332 | 0.633 | 0.090 |
| bitext-all-oof | framework_prepared | 26,872 | 14.505 | 19.662 | 14.238 |

The direct path returns a typed Assessment from the same classifier. The SDK-only path additionally validates and hashes the assessment through DecisionFirewall.assess. The prepared path calls prepare and assess_prepared: requester checks, empty evidence resolution, bounded unchanged input, signed preparation and assessment records, and freshness checks. There are no evidence-based shortcuts in this classification task. Every arm makes one fresh classifier call per row. No predictions are cached or copied between arms. No accuracy-enhancing prompt/context/model change is involved.

These timings exclude runtime initialization and model fitting, which are recorded separately. The full action lifecycle (policy, authorization, dispatch, reconciliation) is not timed here. Do not describe the prepared column as the cost of all firewall features. One runtime per dataset accumulates its audit; first/last-1000 timing diagnostics are retained in summary.json.

## Data quality and limits

Exact normalized duplicates stay in the same out-of-fold partition. BANKING77's official test retains its 25 normalized overlaps with training for split comparability; the earlier report also supplied the non-overlap baseline score. Out-of-fold comparisons report zero such training overlap. This does not remove semantic paraphrases or shared generation templates. Bitext is generated language data, so high scores can reflect template similarity and are not independent production-effectiveness evidence.

All errors remain in denominators; see per-arm invalid-output counts and case-level observations. No post-result tuning, accuracy threshold, promotion or selective row omission was applied. The protocol and data hashes were frozen before these runs. Dataset row counts are not counts of independent business transactions.

## τ-bench and AgentDojo status

Not run. The user chose an existing local endpoint, but its URL/model have not been supplied; the usual Ollama, LM Studio and local OpenAI-compatible ports did not respond. Laya cannot substitute for the required conversational agent/user simulator. We inspected pinned upstream source and added a local endpoint/tool-roundtrip preflight. A governed tool-boundary adapter also remains to be implemented and validated. No connection failure or source inspection is reported as a task-success/security benchmark score.

τ-bench pin: b7ea9074c1cba482b30687fecdb5c8425fd6f619 (tau2 1.0.1). AgentDojo pin: 089ed468cf3ed0322acc66b0211f26d9d90dbf60 (package 0.1.35, versioned suites). See benchmarks/agent_suites/README.md for concrete prerequisites and the preflight command. Compare identical agents with no controls, application controls and equivalent firewall controls; preserve task grading and report benign utility as well as adversarial success. Hidden task solutions cannot enter the policy.

## Recommendation from these results

For a standalone intent classifier, use the direct path unless typed validation or audit records are independently needed. The framework has not earned an accuracy claim here. Its execution-governance value must be judged on tasks involving actual proposed actions, trusted evidence and constraints. Existing synthetic control-parity results remain relevant, but do not replace the pending agent suites.

## Reproduction and attribution

Run python -m benchmarks.paired_public.runner --output .runtime-paired-public/measured with a new output directory, then python scripts/report-paired-public.py. Raw CSVs are hash-checked in an ignored cache. Runtime databases, original message texts and signing keys are excluded from this report. Manifests, per-row CSV/JSONL, summary.json and comparison.csv accompany it.

BANKING77: PolyAI and Casanueva et al., Efficient Intent Detection with Dual Sentence Encoders (2020), CC-BY-4.0; https://github.com/PolyAI-LDN/task-specific-datasets . Bitext: Bitext Innovations (2024), CDLA-Sharing-1.0; https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset . Dataset-derived observations retain upstream rights. New code is Apache-2.0.
