"""Materialize all requirements before any execution; do not overwrite frozen cases."""

import json
from pathlib import Path

from .policies import configuration


def cases():
    result = []
    for domain in ("refund", "data_export"):
        for changed in (False, True):
            for name in (
                "allow",
                "threshold_change",
                "review_approved",
                "review_unauthorized",
                "destination_denied",
                "missing_evidence",
                "model_unavailable",
                "legal_hold",
                "expired",
                "revoked",
                "changed_evidence",
                "response_loss_restart",
                "repeat",
                "audit_failure",
                "concurrent_capacity",
            ):
                action = (
                    {
                        "customer_id": "customer",
                        "payment_id": "payment",
                        "destination": "original",
                        "currency": "INR",
                        "amount_minor": 25000,
                        "requested_reason": "duplicate",
                    }
                    if domain == "refund"
                    else {"requester": "employee", "destination": "sandbox", "rows": 250}
                )
                facts = (
                    {
                        "customer_id": "customer",
                        "destination": "original",
                        "currency": "INR",
                        "amount_minor": 200000,
                        "refunded_minor": 0,
                        "duplicate_verified": True,
                        "unused": True,
                        "age_days": 2,
                        "version": 1,
                    }
                    if domain == "refund"
                    else {
                        "active": True,
                        "destination": "sandbox",
                        "available_rows": 10000,
                        "legal_hold": False,
                        "version": 1,
                    }
                )
                field = "amount_minor" if domain == "refund" else "rows"
                count, expected, initial = 1, 1, "ALLOW"
                if name == "threshold_change":
                    action[field] = 75000 if domain == "refund" else 750
                    if changed:
                        expected, initial = 0, "REQUIRE_REVIEW"
                if name in {"review_approved", "review_unauthorized"}:
                    action[field] = 150000 if domain == "refund" else 1500
                    initial = "REQUIRE_REVIEW"
                    if name == "review_unauthorized":
                        expected = 0
                if name == "destination_denied":
                    action["destination"], expected, initial = "forbidden", 0, "DENY"
                if name == "missing_evidence":
                    facts, expected, initial = None, 0, "REQUIRE_EVIDENCE"
                if name == "model_unavailable":
                    expected, initial = 0, "REQUIRE_REVIEW"
                if name == "legal_hold" and domain == "data_export":
                    facts["legal_hold"] = True
                    if changed:
                        expected, initial = 0, "DENY"
                if name in {"expired", "revoked", "changed_evidence", "audit_failure"}:
                    expected = 0
                if name == "concurrent_capacity":
                    count = 2
                    action[field] = 40000 if domain == "refund" else 400
                    facts["amount_minor" if domain == "refund" else "available_rows"] = (
                        60000 if domain == "refund" else 600
                    )
                result.append(
                    {
                        "id": f"{domain}-{'changed' if changed else 'base'}-{name}",
                        "name": name,
                        "domain": domain,
                        "changed": changed,
                        "config": configuration(domain, changed),
                        "action": action,
                        "facts": facts,
                        "count": count,
                        "expected_effects": expected,
                        "initial": initial,
                        "label": "unavailable"
                        if name == "model_unavailable"
                        else "duplicate"
                        if domain == "refund"
                        else "export",
                    }
                )
    return result


if __name__ == "__main__":
    with Path(__file__).with_name("cases.json").open("x", encoding="utf-8") as stream:
        json.dump(cases(), stream, indent=2)
