# Independent agent pilot: public artifact selection

Start with [COMPARISON.md](COMPARISON.md) and [findings.md](findings.md). These files
are unchanged evaluator outputs for the pre-correction snapshot. The framework's
response is separately recorded in the [0.3.1 corrective release](../../verification/0.3.1/README.md).

Included here:

- Aggregate observations in [JSON](results/observations.json) and [CSV](results/observations.csv).
- Per-test scoring JSON under `results/scoring/`, including the interrupted attempt
  and before/after-maintenance phases; failures have not been removed.
- [Investigation scores](results/investigation-scoring/scores.md) and their [JSON](results/investigation-scoring/scores.json).
- Original public task specifications under `protocol/public/` and evaluated-source /
  frozen-protocol hashes under `hashes/`.
- [Public artifact manifest](public-artifacts.json), recording byte hashes of the
  selected copied files. No scores or task definitions were edited for publication.

This is an auditable results selection, **not a complete executable reproduction
bundle**. The full original archive also contains builder/maintainer implementations,
held-out tests, environment-specific scripts, raw agent transcripts and incident
databases. Those are not bundled here. Public task specifications and hashes preserve
provenance but cannot by themselves reproduce the full pilot. Original report references
to those local paths therefore do not imply those files are available in this repository.

One paired task cannot establish general productivity or statistical superiority.
The configured model is recorded as reported by the evaluator; its served identity
was not independently verified. Budget interruption, prompt asymmetry, lack of enforced
filesystem isolation and the investigation ceiling remain disclosed in the comparison.
