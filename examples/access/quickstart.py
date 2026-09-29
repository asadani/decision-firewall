"""Run with Python after installing decision-firewall. All effects are simulated."""

from pathlib import Path

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.core import Review, verify_receipt
from decision_firewall.domains.access.pack import access_domain

home = Path(".runtime-access-example")
fw = DecisionFirewall(home, [access_domain(home)])
request = fw.submit(
    Proposal(
        domain="access",
        message="Access for tomorrow's on-call shift",
        action={"employee": "alice", "resource": "engineering-docs", "hours": 24},
    ),
    Assessment(provider="fixture", model="example", revision="1"),
)
assert fw.evaluate(request)["result"]["disposition"] == "REQUIRE_REVIEW"
evaluation = fw.review(
    request, Review(decision="approve", reason="Confirmed on-call assignment"), revision=1
)
print(fw.execute(evaluation["authorization"]))
assert fw.replay(evaluation["evaluation_id"])["matches"]
assert verify_receipt(fw.receipt(), fw.store.public)
