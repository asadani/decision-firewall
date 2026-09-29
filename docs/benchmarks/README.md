# Benchmark reports

- [Full-data paired comparisons](paired-public/summary.md): direct classifier, SDK assessment and preparation/recording over every BANKING77 and Bitext source row; official test and out-of-fold scores remain separate. [HTML](paired-public/report.html).

- [Preparation and public intent benchmark](preparation-and-public/summary.md): measured avoided calls and cost, plus BANKING77 full-test and 1K baseline scores. [Dataset and standard-suite selection](public-datasets.md).

- [Reuse, audit and observability](reuse-observability/summary.md): modular application versus framework across two domains and policy changes; telemetry on/off latency, OTLP coverage, restart linkage and failure behavior. [Standalone HTML](reuse-observability/report.html).

- [With and without the framework](framework-value/summary.md): current paired comparison of direct model routing, competent application controls and Decision Firewall; controlled fixtures and local Laya, with frozen protocol and case-level observations. [Standalone HTML](framework-value/report.html).
- `fixture-summary.md`, `baseline-summary.md`, `laya-summary.md` and their JSON/HTML files: preserved historical v0.1 provider comparisons. Every provider used the firewall. **“Baseline” means the keyword language classifier, not execution without the framework.**
- `diagnostic-before-intake-binding.json`: preserved earlier development diagnostic, not an ungoverned control arm.

Repeated synthetic scenarios and paraphrases are not independent production samples. Do not combine different releases, datasets or benchmark definitions into an improvement percentage.
