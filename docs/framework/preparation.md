# Preparation before model assessment

Preparation validates structured intent, checks requester authority, resolves trusted evidence,
and optionally runs explicitly selected existing mandatory rules. It can avoid unnecessary inference.
It never reserves resources, creates execution permits, dispatches effects, or rejects a live customer
request. A blocked preparation is an observation about this input and evidence snapshot.

```python
from decision_firewall import DecisionFirewall, Proposal
from decision_firewall.domains.access.pack import access_domain, access_preparation

fw = DecisionFirewall(".runtime-prepared", [access_domain(".runtime-prepared")])
proposal = Proposal(
    domain="access", message="Grant access for this shift",
    action={"employee": "alice", "resource": "engineering-docs", "hours": 4},
)
prepared = fw.prepare(proposal, access_preparation(structured=True))
assessment = fw.assess_prepared(prepared.id)  # explicit structured path, no model
request_id = fw.submit(prepared.proposal, assessment)
evaluation = fw.evaluate(request_id)  # fresh evidence and full policy, still required
```

Run `python examples/preparation.py` for an isolated, model-free example.

## Routes and contracts

| Route | Next action |
|---|---|
| READY_FOR_MODEL | Call `assess_prepared(id, prepared_model)` |
| READY_FOR_DETERMINISTIC_EVALUATION | Call `assess_prepared(id)` using the recorded host assessment |
| REQUIRE_INPUT_OR_EVIDENCE | Obtain missing input/evidence and prepare a new record |
| BLOCKED_BY_MANDATORY_CHECK | Explain the restriction; changes require new preparation |
| ERROR | Investigate failure; no favorable assessment is substituted |

`PreparationSpec` is trusted host configuration, never a customer or model field. Default preparation
resolves evidence and routes complete inputs to the model. A deterministic assessment is explicit host
opt-in for workflows that do not need language interpretation. The reference access example supports
this; the refund example retains model intake comparison, avoiding an automatic bypass of disagreement
between the request text and its structured reason.

`mandatory_rules` selects names from the registered `RuleSet`; no separate policy implementation is
introduced. Choose only mandatory checks independent of model output and resource usage. Preparation
provides an unavailable assessment, no review and an empty usage snapshot. For example, directory
restrictions and payment destination binding are suitable; available-balance reservations and model
classification checks belong to final evaluation. Ordinary callable domain policies can use minimal
preparation without named prechecks. Rule errors prevent readiness. Checks are evaluated again in final
authorization, along with all other prerequisites.

`refund_preparation()` selects the existing payment binding and eligibility checks. It requests missing
duplicate/usage evidence before model inference. It does not predict amounts or manufacture ledger facts.

## Model context and budgets

`PreparedInput` separates the complete current request from explicitly allowlisted evidence fields and
optional context. Nothing enters model context from the evidence resolver by default. Field values are
data, not instructions; preparation is not a prompt-injection sanitizer.

```python
from decision_firewall import ContextItem, PreparationSpec, RenderedPreparedModel

spec = PreparationSpec(
    evidence_keys=["employee"],
    max_input_characters=4000,
    optional_context=[ContextItem(name="policy-summary", version="1", content="Example guidance")],
)
prepared = fw.prepare(proposal, spec)
# Explicit adapter for existing models with assess(message), including Laya:
# assessment = fw.assess_prepared(prepared.id, RenderedPreparedModel(your_model))
```

The character budget rejects oversized material input or evidence context. Optional items are omitted
whole, with their names recorded; the request is never truncated. Model adapters retain their own token
limits. `assess(message)` remains unchanged, while custom adapters can implement
`assess_prepared(PreparedInput)` directly. Model exceptions propagate.

Optional context is intended for host-owned guidance. Do not insert historical decisions by copying
arbitrary dataset rows into `ContextItem`: that bypasses split/time checks. The existing `ContextualModel`
and `LexicalHistoryRetriever` remain the supported historical evaluation path with explicit reference
pools and leakage checks. Preparation does not automatically retrieve history or replace that path.

## Persistence and observability

New records live in the additive `preparations` table and linked signed audit events. Existing domain
fingerprints and signed payload formats are unchanged. `inspect_preparation(id)` retrieves the recorded
snapshot after restart. Assessment reloads the stored record, checks its requester, expiry, domain
fingerprint and fresh evidence before calling the model. Caller mutations of returned nested objects
cannot change that stored assessment input.

Assessments record preparation ID, spec/input hashes, evidence versions and selected/omitted items.
Telemetry emits preparation route/counts and assessment hashes, allowing linkage to subsequent submit
events without exporting input bodies. The optional OTLP adapter allows `preparation_id`. Observer
failures remain diagnostic; required local audit failures prevent preparation/assessment completion.
Local audit does contain full snapshots and needs deployment-specific retention/access controls.

The normal submit/evaluate API remains usable without preparation. Preparation is an optional cost and
input-quality feature, not a new security boundary. Final authorization and dispatch revalidate facts.

## CLI

```console
firewall framework --home .runtime-prepared --domain access prepare proposal.json --reference-checks --structured-access
firewall framework --home .runtime-prepared --domain access inspect-preparation PREPARATION_ID
firewall framework --home .runtime-prepared --domain access assess-prepared PREPARATION_ID
```

For inference supply `--model-plugin installed_module:create_prepared_model`, an explicitly trusted
factory. No model plugin is downloaded or inferred automatically. Save the assessment and use the
ordinary submit/evaluate commands to proceed. The SDK handles custom preparation specifications.
