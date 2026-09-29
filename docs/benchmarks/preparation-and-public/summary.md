# Preparation and public benchmark measurements

Measured September 28, 2026 on Windows, Python 3.12.14, Intel i5-9300H, approximately 8 GB RAM. CPU only. No paid APIs, external telemetry services or model downloads.

## Before-model preparation

| Arm | Cases | Expected outcomes matched | Model calls | Operation p50 ms |
|---|---:|---:|---:|---:|
| without_preparation | 200 | 200 | 200 | 15.10 |
| with_preparation | 200 | 200 | 50 | 18.67 |

The declared mix has 50 model-needed, 50 structured deterministic, 50 missing-evidence and 50 mandatory-restriction cases. Preparation avoids 150 of 200 model calls (75%) by construction of that workload. This is not an estimated production avoidance rate. Both arms use the same final governance gate; this is not a comparison against a well-engineered application baseline. Stopped preparations are compared to expected prerequisite outcomes, not described as final decisions. No effects were dispatched.

The fixture adds no inference delay. Preparation adds evidence reads, signed records and freshness checks, so its observed median is higher. Real-model savings depend on the actual share of avoidable calls and their cost. Do not subtract these mixture medians to predict production savings or infer better model accuracy.

## BANKING77 intent benchmark

| Evaluation | Train rows | Test rows | Accuracy | Macro-F1 | Normalized train overlaps |
|---|---:|---:|---:|---:|---:|
| banking77-1k | 10003 | 1000 | 78.20% | 76.58% | 5 |
| banking77-full | 10003 | 3080 | 78.60% | 77.65% | 25 |

Both runs use the same fixed unigram multinomial naive Bayes implementation with Laplace alpha=1 and empirical class priors. It trains only on the official training split. The 1K subset is sampled without replacement with seed 20260928. All 77 labels are represented; invalid outputs and missing labels are zero. These are baseline model scores, not Laya scores or improvements attributable to the firewall.

Full-test non-overlap accuracy is 78.49% on 3055 examples. Normalization casefolds text and tokenizes word characters. This detects exact normalized overlap, not semantic paraphrase leakage. Full-test inference p50/p95 is 0.330/0.831 ms; training took 57.42 ms. Macroscopic accuracy is not a measure of authorization or refund eligibility.

BANKING77 has 10,003 training rows but only 3,080 test rows. The runner refuses a 10K test request; copying training examples into evaluation would inflate the evidence. The original test split remains intact and the overlap-filtered score is supplemental. No prompt variants or hyperparameters were selected after inspecting these results. Future fixes informed by this test set should explicitly mark it development-informed.

## Scope and provenance

The preparation protocol was declared before its run. The BANKING77 source revision and file hashes were pinned before training/evaluation. Manifests and case-level JSON/CSV observations accompany this report. Runtime databases, private signing keys, permits and raw source texts are not published. The implementation remains a local sandbox; no production effectiveness or developer productivity claim is made.

BANKING77 attribution: Iñigo Casanueva, Tadas Temčinas, Daniela Gerz, Matthew Henderson and Ivan Vulić, Efficient Intent Detection with Dual Sentence Encoders, NLP for ConvAI / ACL 2020; PolyAI, CC-BY-4.0. Dataset-derived observation files retain those rights; new framework and benchmark code is Apache-2.0. Original source: https://github.com/PolyAI-LDN/task-specific-datasets .

## Reproduce

Run the commands in benchmarks/preparation/README.md and benchmarks/public_intent/README.md from the repository. Run python scripts/report-preparation-public.py after the documented measured run paths exist. See docs/benchmarks/public-datasets.md for Bitext, τ-bench and AgentDojo options. Those additional suites were researched, not executed.
