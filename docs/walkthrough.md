# End-to-end walkthrough

Run `firewall demo`, then `firewall serve`. Browse the ledger and open a large duplicate-charge request in the review queue. Enter a reason and approve it for policy check. The resulting authorization still needs a separate execution operation.

## File-based workflow

`examples/refund/payment.json` is trusted synthetic evidence. `proposal.json` is untrusted intent. `assessment.json` is a fixture assessment. Use a new runtime directory for a repeatable demonstration:

```text
firewall seed examples/refund/payment.json --home .runtime-example
firewall submit examples/refund/proposal.json examples/refund/assessment.json --home .runtime-example
firewall evaluate REQUEST_ID --home .runtime-example --save .runtime-example/token.json
firewall execute .runtime-example/token.json --mode response_loss --home .runtime-example
firewall inspect REQUEST_ID --home .runtime-example
firewall reconcile AUTHORIZATION_ID --home .runtime-example
firewall receipt --home .runtime-example --save .runtime-example/receipt.json
firewall verify .runtime-example/receipt.json .runtime-example/receipt.pub
firewall replay EVALUATION_ID --home .runtime-example
```

Replace identifiers with actual command output. The response-loss example commits the refund but reports UNKNOWN. Reconciliation establishes success without a second effect. `--mode delayed` remains unknown until `reconcile --settle` advances the simulated processor. This explicit settlement is a simulator control, not a production reconciliation assumption.

To use Laya, run `firewall assess MESSAGE --provider laya --save .runtime-example/assessment.json`, then submit that assessment with the matching proposal. The evidence is unchanged. `firewall outcome` appends outcome, appeal, or correction records.

SDK callers can revise a proposal before execution, update trusted evidence, revoke authorization, and change the example policy. Material changes invalidate previously bound authority. See tests for executable examples.

