# OpenRouter compatibility pilot — 28 September 2026

The key authenticated with a non-resetting $5 spending ceiling. No credentials are
included in these artifacts. The client read the ignored local `.env` file.

Successful configuration: `openai/gpt-oss-20b`, provider `darkbloom`, automatic
fallback disabled, temperature 0, low reasoning effort, max_tokens 1024 per call,
`require_parameters=true`, maximum input/output prices $0.03/$0.15 per million
tokens, and `tool_choice=auto`. Calls were sequential, without automatic retries.

Two calls completed the synthetic echo-tool roundtrip. The first returned exactly
one `benchmark_echo` call with `{"text":"ping"}`; the client supplied the literal
tool result `ping`; the model replied exactly `DONE`. The prompt explicitly requested
uppercase DONE and nothing else. No model-generated code or external tool was executed.

## Measured result

- Successful confirmation: 268 input tokens, 49 completion tokens (including reasoning).
- Request latencies: 1.421 seconds and 1.115 seconds, including network/provider time.
- Confirmation cost reported in responses: $0.000009234.
- Total response-reported cost across all successful pilot calls: $0.000018216.
- Key usage counters still reported zero immediately afterward; accounting can lag.
  The nonzero response costs are retained and must count toward the $5 total budget.

## Failed attempts retained

Three requests using required tool selection were rejected with HTTP 404; the diagnostic
reported that no endpoint supported the requested tool_choice value. An automatic-choice
request pinned to AkashML returned HTTP 429. Darkbloom then completed two requests costing
$0.000008982: its tool call was valid, but the final text failed the original exact-DONE
check. That response text was not retained, so its precise formatting is unknown.

The confirmation above clarified the prompt and retained the final reply. This is an
adaptive integration smoke test, not a frozen model-quality evaluation. Eight completion
requests were attempted overall: four rejected requests and four successful responses.
No inference cost was reported for rejected requests; final billing remains authoritative.

Sibling directories retain each result: `openrouter-pilot`, `openrouter-pilot-akash`,
`openrouter-pilot-diagnostic`, `openrouter-pilot-auto`, and `openrouter-pilot-darkbloom-auto`.

## Limits

This establishes basic conversational tool protocol compatibility only. It is not a
tau-bench or AgentDojo run, does not test their simulated user, and provides no governance
effectiveness score or full-suite cost estimate. Their execution-boundary adapters remain
unfinished. Larger runs must retain this fixed model/provider configuration, account for
all agent/user/retry costs, checkpoint progress and stop within the authorized $5 ceiling.
