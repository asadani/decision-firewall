"""Read-only reconstruction from a verified audit receipt, without live plugins."""

import json

from .audit import digest, verify_receipt


def investigate(
    receipt: dict,
    trusted_public_key: bytes,
    request_id: str,
    *,
    action_fields: tuple[str, ...] = (),
) -> dict:
    """Return metadata and reasons, never bearer permits or raw request/evidence bodies.

    Verification raises on any damaged chain. The caller supplies the trust anchor.
    This is a historical snapshot, not verification of external execution truth.
    """
    verify_receipt(receipt, trusted_public_key)
    events = [json.loads(e["body"]) for e in receipt["events"]]
    events = [e for e in events if e["request_id"] == request_id]
    if not events or events[0]["kind"] != "proposal_submitted":
        raise ValueError("Request has no signed submission record")
    proposals, evaluations, reviews, timeline = [], [], [], []
    permits: dict[str, dict] = {}
    gaps = []
    status = "OPEN"
    latest_evaluation = None
    for event in events:
        kind, data = event["kind"], event["data"]
        timeline.append({"seq": event["seq"], "timestamp": event["timestamp"], "kind": kind})
        if kind in {"proposal_submitted", "proposal_revised"}:
            proposal = data["proposal"]
            proposals.append(
                {
                    "revision": data["revision"],
                    "domain": proposal["domain"],
                    "proposal_hash": digest(proposal),
                    "action_hash": digest(proposal["action"]),
                    "action_fields": sorted(proposal["action"]),
                    "selected_action_values": {
                        key: proposal["action"][key]
                        for key in action_fields
                        if key in proposal["action"]
                    },
                    "requester": data.get("actor"),
                }
            )
            for permit in permits.values():
                if permit["status"] == "ISSUED":
                    permit["status"] = "SUPERSEDED"
            status = "OPEN"
        elif kind == "policy_evaluated":
            context, result, manifest = data["context"], data["result"], data["domain"]
            latest_evaluation = data["id"]
            evaluations.append(
                {
                    "id": latest_evaluation,
                    "policy_version": manifest["policy_version"],
                    "domain_hash": digest(manifest),
                    "disposition": result["disposition"],
                    "reasons": result["reasons"],
                    "errors": result["errors"],
                    "constraints": result["constraints"],
                    "evidence_versions": context["evidence"]["versions"] if context else None,
                    "evidence_hash": digest(context["evidence"]) if context else None,
                    "missing_evidence": context["evidence"]["missing"] if context else None,
                    "rules": [],
                }
            )
            if context is None:
                gaps.append(f"{latest_evaluation}: evaluation snapshot unavailable")
            status = "EVALUATION_ERROR" if result["errors"] else result["disposition"]
            for permit in permits.values():
                if permit["status"] == "ISSUED":
                    permit["status"] = "SUPERSEDED"
        elif kind == "rule_report":
            matching = next((e for e in evaluations if e["id"] == data["evaluation_id"]), None)
            if matching is None:
                gaps.append("Rule report has no matching evaluation")
            else:
                matching["rules"] = [
                    {k: r[k] for k in ("name", "version", "status", "reasons")}
                    for r in data["rules"]
                ]
        elif kind == "review_recorded":
            reviews.append({k: data[k] for k in ("actor", "revision", "decision", "reason")})
            status = "OPEN"
        elif kind == "authorization_issued":
            permits[data["id"]] = {
                **{
                    k: data[k]
                    for k in (
                        "id",
                        "revision",
                        "executor",
                        "expires",
                        "proposal_hash",
                        "evidence_hash",
                        "domain_hash",
                        "approval_id",
                    )
                },
                "evaluation_id": latest_evaluation,
                "status": "ISSUED",
                "attempt_id": None,
                "outcomes": [],
            }
        elif kind == "authorization_revoked":
            if data["id"] in permits:
                permits[data["id"]]["status"] = "REVOKED"
            else:
                gaps.append("Revocation has no matching authorization")
        elif kind in {"execution_reserved", "execution_outcome"}:
            pid = data.get("permit_id", data.get("authorization_id"))
            execution_permit = permits.get(pid)
            if execution_permit is None:
                gaps.append("Execution has no matching authorization")
                continue
            if kind == "execution_reserved":
                execution_permit.update(status="RESERVED", attempt_id=data["attempt"])
                status = "AWAITING_RECONCILIATION"
            else:
                if execution_permit["attempt_id"] != data["attempt_id"]:
                    gaps.append("Execution attempt binding mismatch")
                execution_permit["status"] = data["status"]
                execution_permit["outcomes"].append({"seq": event["seq"], "status": data["status"]})
                status = {
                    "SUCCEEDED": "COMPLETED",
                    "FAILED": "OPEN",
                    "UNKNOWN": "AWAITING_RECONCILIATION",
                }[data["status"]]
    unresolved = [p["id"] for p in permits.values() if p["status"] in {"RESERVED", "UNKNOWN"}]
    return {
        "schema_version": 1,
        "request_id": request_id,
        "audit_verified": True,
        "checkpoint": receipt["checkpoint"]["payload"],
        "trust_scope": "Supplied key and recorded events; no live external verification",
        "request_status_from_events": status,
        "proposals": proposals,
        "evaluations": evaluations,
        "reviews": reviews,
        "authorizations": list(permits.values()),
        "timeline": timeline,
        "gaps": gaps,
        "unresolved_authorizations": unresolved,
        "next_step": "Reconcile original authorization IDs; do not dispatch with new keys"
        if unresolved
        else "No unresolved execution recorded in this snapshot",
        "content_note": "Messages, action values, evidence bodies and executor detail omitted; "
        "policy/review reasons may contain application-provided sensitive text",
    }
