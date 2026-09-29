# Refund governance evaluation

Provider: fixture

Evaluation families only (development reported separately in results.json).

| Measurement | Result |
|---|---|
| n | 81 |
| classification_accuracy | 1.0 |
| policy_agreement | 1.0 |
| false_allows | 0 |
| false_blocks | 0 |
| review_count | 14 |
| refund_brier | 0.0 |
| probability_n | 81 |
| refund_ece_10_bins | 0.0 |
| invalid_outputs | 0 |
| gate_p50_ms | 9.213399999680405 |
| gate_p95_ms | 13.949199999842676 |
| inference_p50_ms | 0.029800000447721686 |
| inference_p95_ms | 0.045900000259280205 |
| successful_effects | 35 |
| unresolved_executions | 0 |
| over_refunds | 0 |
| duplicate_effects | 0 |
| ordinal_error | None |
| ordinal_note | No ordinal labels in the refund dataset |

## Limitations

- Synthetic English data; not production effectiveness
- Fixture uses oracle labels; it is not a competing learned model
- Seeded variations are paraphrase wrappers, not independent samples
- Review-required cases are not auto-approved in benchmarks
- Concurrency and fault injection are measured by the separate adversarial test suite