# Framework-value comparison

This benchmark compares three execution architectures, including a competent independently implemented application baseline. Read `protocol.json` before interpreting any numbers. All effects are simulated. No simulator safeguard is disabled. These are synthetic diagnostic cases, not a production trial or an independent held-out evaluation.

The protocol and cases were written and hashed before any treatment execution. Frozen SHA-256:

- protocol: `4ffa7b27fb68a499d6290a9809fa18e9ec5a4e51015cadcf19d9bd2f2ec1ced6`
- cases: `d59e97865e3e06a322ce941e7dea67b257d3b5c881d41409d1257e0ceeff9010`

The actual implementations and complete source hashes are captured in each run manifest. Do not regenerate or edit cases to fit observed results.

## Clarifications recorded before the first execution

- `model_disagrees` and `model_unavailable` deliberately inject the specified model fault in both provider conditions, including the Laya condition. Raw Laya outputs remain in `assessments.json`; the applied label and injection flag are separate. These two cases are not observations of Laya model errors.
- Laya supplies request classification only. The direct arm uses the explicitly declared classification-to-execution mapping. This is not a test of an unconstrained model independently deciding a refund amount or legal eligibility.
- All arms consume the same effective request-type signal and original request. Confidence does not authorize actions in any arm. Model inference is done once and excluded from arm timing.
- `audit_outage` is injected after initial preparation, immediately before dispatch. Expected initial policy disposition remains ALLOW; required audit failure must prevent the subsequent effect.
- Application budget accounting targets the single UTC day used by the frozen cases. Multi-day rollover, distributed workers, hostile plugins and full host compromise are outside this experiment. Plain audit storage is present in the application baseline; cryptographic receipt verification is separately reported as a capability.
- The restart case reconstructs recovery in a fresh Python subprocess after response loss and durable state persistence. It does not emulate an OS/power failure at an arbitrary instruction. All arms receive the same logical-request recovery input; only the governed arms have a durable attempt identity. Direct execution retries with a new key, as predeclared.
- Repeated trials measure runtime variation. They do not multiply the number of independent policy cases. Report both trial counts and unique case families.
- Measurement failures must be fixed and documented without treating them as product benefits. Development smoke runs use `--repetitions 1`, are labeled diagnostic, and are retained locally. Full measured runs use the frozen five repetitions.

## Reproduce

From the repository root, with the core installed:

```sh
python -m benchmarks.framework_value.runner --output .runtime-value/fixture --provider controlled_fixture
```

With the pinned optional Laya runtime and checkpoint available:

```sh
python -m benchmarks.framework_value.runner --output .runtime-value/laya --provider local_laya
```

Every output directory must be new. The runner emits pinned protocol/cases, a pre-execution manifest, model assessments, incremental JSONL observations, final JSON and CSV. Runtime databases and bearer permits remain under the ignored output directory. Public summaries must exclude them.

`application.py` uses its own Python business checks, SQLite schema/transactions and recovery logic. It does not call the framework policy gate, RuleSet, authorization or runtime APIs. It shares the same PaymentSimulator as the other arms. `Governed` in `runner.py` is the small integration layer over the actual v0.3 SDK; the runner does not patch its gate or execution behavior. All treatment arms receive identical synthetic fault schedules.

After both full runs, create a new standalone comparison directory:

```sh
python scripts/report-framework-value.py .runtime-value/fixture .runtime-value/laya --destination docs/benchmarks/framework-value
```

The publisher creates Markdown, standalone HTML, comparison CSV and copies of synthetic observations and assessment snapshots. It does not copy runtime databases, signing keys or bearer permits. A published directory is never overwritten.

Keep raw trial observations available when publishing aggregate results. An equal safety result against the application baseline is meaningful: it indicates that competent application engineering can supply these controls, and any framework case rests on reuse, audit capabilities and maintenance tradeoffs rather than unique safety magic.
