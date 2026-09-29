# Full-source before/after classification study

```console
python -m benchmarks.paired_public.runner --output .runtime-paired-public/new-run
```

The pinned protocol is declared before execution. Three independently invoked paths use the identical
fitted classifier and identical text: direct, SDK assessment, and preparation plus signed recording.
This isolates the effect of wrapping the classifier. It does not change its prompt, add examples, fit
a different model, invoke a policy, issue authorizations or dispatch effects. Classifier output labels
are not refund eligibility or business-action decisions.

Coverage is all 13,083 BANKING77 source rows and all 26,872 Bitext source rows, each evaluated in three
arms. BANKING77's 3,080 official test cases retain their standard split; its 10,003 training rows are
additionally evaluated out of fold and reported separately. Bitext uses five deterministic held-out
folds because this source has no official train/test split. Identical normalized texts stay together.
Synthetic template relatives and semantic paraphrases can still cross folds; scores are not estimates
of effectiveness on independently collected production data. Responses, categories, flags and expected
intents are never sent to the classifier for a held-out prediction.

An existing core environment suffices. Cache hashes are checked; no remote Python scripts are executed.
The downloader may fetch the public CSVs. All errors are retained in denominators. Runtime initialization
is separate from inference/preparation timing. One shared runtime per dataset grows its audit log; first
and last 1,000-row timing summaries help expose growth effects. There is one pass, with seeded shuffled
arm order per row. Optional telemetry export is off. Setup and fitting costs are reported separately.

Runtime folders contain signing keys and raw input bodies and must remain ignored. Only sanitized
summary.json, manifest.json, observations.jsonl and observations.csv are selected for publication.
The generated large per-row CSV/JSONL exports remain local and are excluded from Git and source
distributions. Aggregate comparisons, coverage verification, manifests and reports are versionable;
the runner regenerates all per-row artifacts.

BANKING77 observations retain CC-BY-4.0 attribution to PolyAI / Casanueva et al. (2020). Bitext source
and data-derived observations retain CDLA-Sharing-1.0 rights and attribution to Bitext Innovations (2024).
Their original sources are https://github.com/PolyAI-LDN/task-specific-datasets and
https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset .
New benchmark code is Apache-2.0; dataset rights are not replaced by the repository license.
