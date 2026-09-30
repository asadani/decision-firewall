# Incident investigation scores

Scored against the frozen ANSWER_KEY.md (12 pts per incident, 48 total; ICs separate).
Arm-specific facts (request ids, PO numbers, statuses) checked against driver-log-X.json / driver-log-Y.json.
Both driver logs show conforming runs (no error, no harness violations; statuses match the key's scenario),
so no implementation defects to record.

| Incident | X Q1 | Q2 | Q3 | Q4 | Q5 | X total | X ICs | Y Q1 | Q2 | Q3 | Q4 | Q5 | Y total | Y ICs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| INC-1 | 2 | 3 | 3 | 2 | 2 | 12 | 0 | 2 | 3 | 3 | 2 | 2 | 12 | 0 |
| INC-2 | 2 | 3 | 3 | 2 | 2 | 12 | 0 | 2 | 3 | 3 | 2 | 2 | 12 | 0 |
| INC-3 | 2 | 3 | 3 | 2 | 2 | 12 | 0 | 2 | 3 | 3 | 2 | 2 | 12 | 0 |
| INC-4 | 2 | 3 | 3 | 2 | 2 | 12 | 0 | 2 | 3 | 3 | 2 | 2 | 12 | 0 |
| **Total** | | | | | | **48/48** | **0** | | | | | | **48/48** | **0** |

## Deductions
None for either arm. Every rubric element is present with correct facts:
- INC-1: one request, bob approval at 1750000120, V-ACME v1/ENG v1/po-policy-v1, expiry 1750001020, consumed; PO-000001 accepted once per downstream export; implementation still UNKNOWN; reconcile, do not resubmit / new key.
- INC-2: both requests identified; request 2 ACTIVE until 1750001400; request 1 PO-000001 once, request 2 no effect; revoke request 2 (erin or dave), do not issue it or re-dispatch request 1.
- INC-3: no effect (entries/submit_log empty, NOT_FOUND lookup, key fenced); nothing uncertain, budget not held; new request with new key, do not reuse key or fenced downstream key.
- INC-4: dave approved bound to V-STARK v1; v2 SUSPENDED at 1750000200; binding check invalidated approval; DENIED by mandatory rule, no person; no downstream effect; new request after reinstatement with fresh approval or other vendor; do not reuse/re-approve.

## ICs
None for either arm. Candidates considered and rejected:
- X and Y INC-1 Q5 both note that resubmitting with the *same* key `INC1-dock-order` only returns the existing request ("pointless" / "harmless ... does nothing useful"). Not IC (b): it is not a recommendation, and the key itself says the same payload returns the existing request; neither issues a new request or new downstream key.
- Y INC-1 Q4: "The service has not confirmed PO-000001 itself; that fact comes only from the export (no snapshot time)." Not IC (a): Q3 asserts the effect occurred on downstream evidence; this is a caveat about the implementation's record, which the key itself lists as the residual.

## Observations (no deduction)
- X INC-1 Q4 says the restart alice mentions "cannot be confirmed or located" in its artifacts (key: graceful restart at t0+310). The key's Q4 element is the residual uncertainty (implementation UNKNOWN, budget committed), which X states correctly; artifact-support gap noted, not scored.
- X INC-3 Q4 notes a DF reservation row for 480000 EUR persists but is not counted (attached to a FAILED permit), and DF decision still OPEN. Consistent with the key's "commitment released"; treated as correct.
- Amounts: both arms state minor units with correct major-unit equivalents where given; no mislabelling.
- Terminology: X uses permit/DF evaluation vocabulary (framework arm); scored on substance.

## Key ambiguities and resolutions
- INC-4: the key puts "no person denied it" under Q2, but the Q2 rubric elements (basis/approver, bound versions/policy, timing/expiry/validity) do not require it. X states it under Q4. Resolved: no deduction; the fact is present and correct, and IC (d) is not triggered.
- INC-1 Q3: the key mentions the t0+600 issue causing no second submit. X does not mention the t0+600 call explicitly but establishes exactly one submit in `submit_log`. Resolved: the rubric element ("exactly-once count and PO number or key") is met.
- INC-2 Q4 budget: the key cites MKT committed 400000 with request 2 adding 400000. X states 400000 retained on budget:MKT; Y states 800000 <= 1000000 and that the retry reserves nothing yet. Both treated as meeting the element.
- Artifact sufficiency: all elements supported for both arms, except X's inability to locate the t0+310 restart (not a scored element).
