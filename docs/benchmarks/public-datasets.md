# Public datasets and recognized benchmark options

Update: [full-data paired measurements](paired-public/summary.md) now cover all BANKING77 and Bitext rows. The original single-baseline measurements below remain historical. Agent suites still require a supplied local model endpoint and tool-boundary integration; see the new report for the current status.

Sources checked September 28, 2026. Dataset accessibility is not the same as execution ground truth.
Use original publishers and pinned revisions; a larger CSV does not automatically give stronger safety evidence.

| Dataset / suite | Scale and license shown by publisher | Useful measurement | What it cannot establish here |
|---|---|---|---|
| [BANKING77](https://huggingface.co/datasets/PolyAI/banking77) | 10,003 train + 3,080 test; 77 intents; CC-BY-4.0 | Banking request classification, including duplicate charges and refund requests | Refund eligibility, ledger truth, authorization safety |
| [Bitext customer support](https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset) | 26,872 rows; CDLA-Sharing-1.0 | Customer-support language coverage and robustness across linguistic variations | Independent real transaction outcomes; examples are generated training material |
| [τ-bench / current tau2-bench repository](https://github.com/sierra-research/tau2-bench) | Versioned interactive tasks; MIT repository | Tool-using agent task completion under domain policies | A simple classifier score is not an official agent benchmark result |
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) | Dynamic prompt-injection task/attack suites; MIT repository | Utility and attack success when agents read untrusted tool data | Ordinary refund classification and transaction correctness alone |

The [original BANKING77 repository](https://github.com/PolyAI-LDN/task-specific-datasets) supplies plain
CSV files; the pinned downloader avoids executing Hugging Face dataset scripts or installing datasets,
PyArrow, model dependencies or Kaggle authentication. The upstream license and file hashes are checked.
Raw files remain in an ignored cache. This repository's Apache license does not replace dataset rights.
Attribution: Iñigo Casanueva, Tadas Temčinas, Daniela Gerz, Matthew Henderson and Ivan Vulić,
*Efficient Intent Detection with Dual Sentence Encoders*, NLP for ConvAI / ACL 2020.

## Implemented first benchmark

`benchmarks/public_intent` runs a fixed multinomial naive Bayes baseline trained on the original training
split and evaluated on either a seeded 1,000-test-example subset or the complete 3,080-example test split.
No hyperparameter tuning, pretrained model, automatic threshold or policy promotion is involved.
It reports accuracy, macro-F1, denominators, invalid/missing outputs, latency and normalized exact text
overlap. The original test split remains intact for comparability; non-overlap accuracy is also reported.
This is our implementation of a baseline on a recognized dataset, not an official leaderboard submission.

```console
python -m benchmarks.public_intent.runner --output .runtime-public-data/test-1k --limit 1000
python -m benchmarks.public_intent.runner --output .runtime-public-data/test-full
```

The test set has only 3,080 rows. We deliberately reject `--limit 10000` rather than duplicate examples
or relabel training rows as held-out tests. A 10K throughput workload can use the training pool, clearly
labeled development data; it would not constitute 10K held-out accuracy observations.

## Recommended next experiments

1. Compare local Laya's original 77-way intent predictions against this baseline using the same pinned
   test split. Select prompt/question variants using a validation split carved from training only.
   Keep the existing three-way refund adapter separate: collapsing 77 labels produces a new task and
   must not be reported as a standard BANKING77 score. Public-data pretraining contamination is unknown.
2. Use the separate preparation study to measure avoided inference, premature blocks, context budgets
   and latency. Public intent labels alone cannot say when evidence is complete or a model call unnecessary.
   Any attached ledger/identity facts are synthetic overlays with separately labeled results.
3. Integrate the firewall at the actual tool-dispatch boundary of a pinned τ-bench release, first in
   retail. Compare the same agent model with application controls and framework controls. Preserve the
   original task definitions, user simulator and grading before claiming a standard score. The current
   upstream has evolved to τ³-bench; pin the release and domain because grading changes affect comparisons.
4. Add AgentDojo as a distinct adversarial suite once that tool adapter exists. Report benign utility
   alongside attack success. A framework cannot prevent bypasses through ungoverned tools.

No external model API was used, no hosted service was provisioned, and neither τ-bench nor AgentDojo was
run in this release. They need an agent/tool integration beyond a local typed decision classifier.
Bitext was initially inspected only; it has now been downloaded into an ignored cache for the paired
out-of-fold study. Raw texts are not redistributed in the report. A publisher-hosted source was preferred
over an unverified Kaggle mirror. [Original measurements](preparation-and-public/summary.md).
