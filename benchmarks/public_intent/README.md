# Pinned BANKING77 baseline

Read `protocol.json` before running. The standard-library runner fetches the original publisher's
train/test CSVs and license at a fixed commit, checks all SHA-256 hashes, and retains raw data in
`.runtime-public-data/`. No remote Python code is loaded.

```console
python -m benchmarks.public_intent.runner --output .runtime-public-data/new-test --limit 1000
python -m benchmarks.public_intent.runner --output .runtime-public-data/new-full
```

Directories must be new. An existing cache is reused only if the pinned hashes match. Outputs contain
indices, text hashes, labels, predictions and timings, not original messages. Train only on the official
10,003 training rows; never extend the 3,080-row held-out split by sampling training examples. The baseline
is fixed unigram multinomial naive Bayes. It is not Laya and does not measure execution governance.

Dataset: Casanueva et al., *Efficient Intent Detection with Dual Sentence Encoders* (2020), PolyAI,
CC-BY-4.0. Original data: https://github.com/PolyAI-LDN/task-specific-datasets.
The license applies to dataset-derived observations; repository code remains Apache-2.0.
See `docs/benchmarks/public-datasets.md` and `docs/benchmarks/preparation-and-public/summary.md`.
