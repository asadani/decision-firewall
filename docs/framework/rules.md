# Named rules and compatibility

Ordinary `DomainPack.evaluate(context) -> Decision` remains supported. The optional `decision_firewall.rules` exports `Rule`, `RuleResult`, `RuleSet`, and `PolicyReport`. Implement logic in Python and validate JSON parameters with a Pydantic model; there is no additional policy language.

```python
from decision_firewall.core import Record
from decision_firewall.rules import Rule, RuleResult, RuleSet

def destination_check(context, config):
    valid = context.proposal.action["destination"] == context.evidence.facts["destination"]
    return RuleResult(status="pass" if valid else "deny", reasons=["destination_binding"])

rules = RuleSet([Rule("destination", "1", "Bind action to trusted destination",
                     destination_check, Record())])
```

Every rule has a stable name/version/description/configuration and `kind` (`mandatory` by default, or `review`). Mandatory checks run first, each against a validated context/config copy. Within a rule set, errors block; hard denial dominates evidence requests; missing evidence blocks; unresolved review requirements route to review. Approval satisfies only explicitly designated review rules. A review rule cannot introduce a hard denial/evidence check; move such logic into a mandatory rule. Existing runtime prerequisites (missing evidence, reviewer rejection, unavailable assessment, supported constraints, resource capacities) remain in force.

No individual rule issues authority. Only after checks pass does the optional `finalize(context)` assemble the decision, constraints and resource claims. Duplicate claim keys are rejected, including otherwise identical definitions. Unsupported constraints and exceptions fail closed. Keep all mandatory business checks in mandatory rules, not a review callback or model score.

`firewall policy inspect --domain access` prints ordered rules, descriptions, validated parameters, versions and the complete configuration fingerprint. Evaluation reports include actual rule statuses/reasons. Runtime stores per-rule results in an additive `rule_reports` table and separate signed audit events; the Decision/authorization payload schema is unchanged. Rule timing is observational and excluded from policy fingerprints. Timing does not affect replay decision comparisons.

Add `--context-file context.json` to inspect actual rule reasons against a pinned `Context` JSON record, including explicit proposal, assessment, evidence, usage and time (`now`). This uses the same offline gate and cannot issue an authorization or execute an action.

The default generic access pack uses `access-demo-v2`. The generic refund pack uses the configured legacy version plus `-rules-v2`. Both retain old `pack_v1.py` factories for old recorded policies:

```python
from decision_firewall.domains.access.pack_v1 import access_domain
from decision_firewall.domains.refunds.pack_v1 import refund_domain
```

Use the factory/config matching the stored fingerprint to replay or finish work under that old policy. Changing the default pack intentionally changes the fingerprint; it does not silently reinterpret old authorizations. Receipts still verify with their existing public keys. The v0.1 top-level refund facade remains unchanged. No old signed rows are rewritten. Compatibility tests include a receipt and policy snapshot generated before the v0.3 migration.
