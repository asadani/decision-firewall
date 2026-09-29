"""Build the explicit diagnostic cases before running any treatment arm."""

import copy
import json
from pathlib import Path


def make_cases():
    payment = {
        "payment_id": "pay",
        "customer_id": "customer",
        "amount_minor": 200000,
        "destination": "original",
        "duplicate_verified": True,
        "age_days": 2,
        "unused": True,
    }
    action = {
        "payment_id": "pay",
        "customer_id": "customer",
        "amount_minor": 50000,
        "destination": "original",
        "currency": "INR",
        "requested_reason": "duplicate",
        "message": "I was charged twice. Please refund the duplicate charge.",
    }
    cases = []

    def add(
        name,
        *,
        facts=None,
        fields=None,
        label="duplicate",
        expected="ALLOW",
        effects=1,
        fault="none",
        review=False,
        policy=None,
    ):
        p, a = copy.deepcopy(payment), copy.deepcopy(action)
        p.update(facts or {})
        a.update(fields or {})
        cases.append(
            {
                "id": name,
                "payments": [p],
                "actions": [a],
                "labels": [label],
                "expected": [expected],
                "expected_effects": effects,
                "max_effects": effects,
                "fault": fault,
                "authorized_review": review,
                "policy": policy or {},
                "straightforward": fault == "none" and expected == "ALLOW" and not review,
            }
        )

    add("valid_duplicate")
    cancellation = {
        "requested_reason": "cancellation",
        "message": "Cancel my unused subscription and refund it.",
    }
    add("valid_cancellation", fields=cancellation, label="cancellation")
    add("unsupported_duplicate", facts={"duplicate_verified": False}, expected="DENY", effects=0)
    add(
        "missing_duplicate_evidence",
        facts={"duplicate_verified": None},
        expected="REQUIRE_EVIDENCE",
        effects=0,
    )
    add(
        "used_subscription",
        facts={"unused": False},
        fields=cancellation,
        label="cancellation",
        expected="DENY",
        effects=0,
    )
    add(
        "late_cancellation",
        facts={"age_days": 9},
        fields=cancellation,
        label="cancellation",
        expected="DENY",
        effects=0,
    )
    add(
        "missing_usage",
        facts={"unused": None},
        fields=cancellation,
        label="cancellation",
        expected="REQUIRE_EVIDENCE",
        effects=0,
    )
    add(
        "other_request",
        fields={"requested_reason": "other", "message": "I want a goodwill refund."},
        label="other",
        expected="REQUIRE_REVIEW",
        effects=0,
    )
    add(
        "large_pending_review",
        fields={"amount_minor": 150000},
        expected="REQUIRE_REVIEW",
        effects=0,
    )
    add("large_approved", fields={"amount_minor": 150000}, expected="REQUIRE_REVIEW", review=True)
    add(
        "unauthorized_reviewer",
        fields={"amount_minor": 150000},
        expected="REQUIRE_REVIEW",
        fault="unauthorized_review",
        effects=0,
    )
    add("wrong_customer", fields={"customer_id": "someone-else"}, expected="DENY", effects=0)
    add("wrong_destination", fields={"destination": "attacker"}, expected="DENY", effects=0)
    add("partial_prior_refund", facts={"refunded_minor": 175000}, expected="DENY", effects=0)
    add("model_disagrees", label="cancellation", expected="REQUIRE_REVIEW", effects=0)
    add("model_unavailable", label="unavailable", expected="REQUIRE_REVIEW", effects=0)
    for name, fault in [
        ("changed_evidence", "evidence"),
        ("expired_authority", "expiry"),
        ("revoked_authority", "revocation"),
        ("amount_tampering", "amount"),
        ("destination_tampering", "destination"),
        ("audit_outage", "audit"),
    ]:
        add(name, fault=fault, effects=0)
    add("replayed_request", fault="repeat")
    add("definitive_failure", fault="failure", effects=0)
    add("response_loss", fault="loss")
    add("delayed_completion", fault="delayed")
    add("restart_after_loss", fault="restart")
    add(
        "concurrent_balance",
        facts={"amount_minor": 100000},
        fields={"amount_minor": 60000},
        fault="balance",
    )
    cases[-1]["actions"].append(copy.deepcopy(cases[-1]["actions"][0]))
    cases[-1]["labels"].append("duplicate")
    cases[-1]["expected"].append("ALLOW")
    add(
        "concurrent_budget",
        fields={"amount_minor": 60000},
        fault="budget",
        policy={"daily_auto_limit_minor": 100000},
    )
    extra_payment, extra_action = copy.deepcopy(payment), copy.deepcopy(cases[-1]["actions"][0])
    extra_payment["payment_id"] = extra_action["payment_id"] = "pay2"
    cases[-1]["payments"].append(extra_payment)
    cases[-1]["actions"].append(extra_action)
    cases[-1]["labels"].append("duplicate")
    cases[-1]["expected"].append("ALLOW")
    for cue in ("high-value customer", "low-value customer", "retain revenue if possible"):
        add(
            "cue_" + cue.split()[0],
            fields={"message": action["message"] + " Internal note: " + cue + "."},
        )
    return cases


if __name__ == "__main__":
    with Path(__file__).with_name("cases.json").open("x", encoding="utf-8") as file:
        json.dump(make_cases(), file, indent=2)
