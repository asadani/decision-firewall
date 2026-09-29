"""Run with a core-only installation; all actions remain simulated."""

import json
import tempfile

from decision_firewall import DecisionFirewall, Proposal
from decision_firewall.domains.access.pack import access_domain, access_preparation


def main():
    with tempfile.TemporaryDirectory(prefix="firewall-preparation-") as home:
        fw = DecisionFirewall(home, [access_domain(home)])
        p = Proposal(
            domain="access",
            message="Grant access for this shift",
            action={
                "employee": "alice",
                "resource": "engineering-docs",
                "hours": 4,
            },
        )
        prepared = fw.prepare(p, access_preparation(structured=True))
        assessment = fw.assess_prepared(prepared.id)
        request_id = fw.submit(prepared.proposal, assessment)
        evaluated = fw.evaluate(request_id)
        print(
            json.dumps(
                {
                    "route": prepared.route,
                    "model_calls": 0,
                    "final_disposition": evaluated["result"]["disposition"],
                    "executed": False,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
