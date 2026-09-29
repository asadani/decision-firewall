# Product and demonstration policy

This page specifies the refund reference application. The reusable framework's goals and validation approach are described in [Engineering value and measurement plan](framework/engineering-value.md).

Decision Firewall helps an engineer or reviewer reconstruct why a refund was permitted, ensure the exact authorized effect executes at most once, and investigate outcomes. A refund request is distinct from an execution attempt: rejection of a malformed authorization does not reject the customer's claim.

## Example policy v1

Amounts are integer paise. Currency is INR. These rules are fictional demonstration policy, not legal entitlement.

| Situation | Result |
|---|---|
| Verified duplicate charge | Eligible against the duplicate payment |
| Duplicate status unknown | Require evidence |
| Duplicate claim contradicted by ledger | Deny |
| Unused subscription cancelled within 7 days, inclusive | Eligible |
| Used subscription or cancellation after 7 days | Deny |
| Missing age/usage evidence | Require evidence |
| Other request | Reviewer establishes manual eligibility |
| Eligible amount ≤ INR 1,000 | Automatic, subject to daily limit |
| Larger amount or automatic daily usage above INR 10,000 | Require review |
| Wrong customer, currency, destination, or excessive amount | Hard denial |

Automated daily usage is measured in UTC and includes reserved, unknown, and successful automatic executions. Approved manual refunds do not consume the automatic allowance, but still consume the payment's refundable balance. Failed attempts release reservations. Unknown attempts retain them. The limit is configurable; eligibility is not changed by budget exhaustion.

Laya classifies language. It does not verify duplicate billing, identity, age, usage, or the remaining balance. The local ledger is the trusted source. Seeded evidence is deliberately explicit; a production resolver must authenticate the source and freshness.

Reviewer approval expires after one hour and binds to proposal revision, evidence version, policy hash, and reviewer authority generation. Authorization expires after five minutes. A reviewer cannot waive a hard denial. Updating evidence or policy requires re-evaluation. Customer value and revenue-retention cues are excluded from policy inputs that grant permission.

## Accepted v0.1 scope

SDK/CLI, local review inspector, signed audit chain, deterministic policy, durable simulated payment processing, fixture/baseline/Laya assessment, scenario benchmarks, and adversarial tests. Public deployment, real payments, fine-tuning, automatic calibration, production identity, and claims of legal compliance are out of scope.


## Intake binding

The customer/application supplies a declared `requested_reason` separately from the assessment. Missing reasons default to `other` and require review. The adapter cannot populate or change this field. Eligibility checks follow this declared reason and verified ledger facts; model/intake disagreement adds review. The field is a customer claim, not verified evidence. A malicious claim still cannot satisfy ledger requirements. This separation was added after a local benchmark found two model-driven review bypasses.
