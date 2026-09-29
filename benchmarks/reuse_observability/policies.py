"""Shared pure domain policies: architecture comparison, not a policy contest."""

from benchmarks.framework_value.application import decide as refund_decide


def export_v1(action, facts, config, approved):
    if not facts["active"] or action["destination"] != facts["destination"]:
        return "DENY", ["requester_or_destination_prohibited"]
    if action["rows"] > facts["available_rows"]:
        return "DENY", ["too_many_rows"]
    if action["rows"] > config["automatic_rows"] and not approved:
        return "REQUIRE_REVIEW", ["export_size_review"]
    return "ALLOW", ["export_eligible"]


def export_v2(action, facts, config, approved):
    if facts["legal_hold"]:
        return "DENY", ["legal_hold_mandatory"]
    return export_v1(action, facts, config, approved)


def configuration(domain, changed=False):
    if domain == "refund":
        return {
            "version": "refund-1",
            "auto_amount_minor": 50000 if changed else 100000,
            "daily_auto_limit_minor": 1000000,
            "cancellation_days": 7,
        }
    return {
        "version": "export-2" if changed else "export-1",
        "automatic_rows": 500 if changed else 1000,
    }


def policy(domain, action, label, evidence, config, approved, usage):
    if evidence is None:
        return "REQUIRE_EVIDENCE", ["material_evidence_missing"], []
    if label == "unavailable":
        return "REQUIRE_REVIEW", ["model_unavailable"], []
    if domain == "refund":
        result = refund_decide(
            action,
            label,
            evidence,
            config,
            approved,
            usage.get("balance", 0),
            usage.get("budget", 0),
        )
        claims = [
            {
                "key": "balance",
                "units": action["amount_minor"],
                "capacity": evidence["amount_minor"] - evidence["refunded_minor"],
                "retain": True,
            }
        ]
        if not approved:
            claims.append(
                {
                    "key": "budget",
                    "units": action["amount_minor"],
                    "capacity": config["daily_auto_limit_minor"],
                    "retain": True,
                }
            )
        return result, ["refund_policy:" + result], claims if result == "ALLOW" else []
    evaluate = export_v2 if config["version"] == "export-2" else export_v1
    result, reasons = evaluate(action, evidence, config, approved)
    if result == "ALLOW" and usage.get("capacity", 0) + action["rows"] > evidence["available_rows"]:
        return "DENY", ["export_capacity_exhausted"], []
    return (
        result,
        reasons,
        (
            [
                {
                    "key": "capacity",
                    "units": action["rows"],
                    "capacity": evidence["available_rows"],
                    "retain": True,
                }
            ]
            if result == "ALLOW"
            else []
        ),
    )
