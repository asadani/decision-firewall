"""Narrow benchmark tool-boundary policies. No task solutions or grader inputs."""

import json
import re
import sqlite3
import time

from pydantic import BaseModel, ConfigDict

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.core.audit import digest, verify_receipt
from decision_firewall.core.contracts import Decision, Evidence, ExecutionResult
from decision_firewall.core.plugins import DomainPack


class ToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    arguments: dict


def banking_policy(tool, arguments, facts):
    """Conservative capability matching against the ORIGINAL user message only.

    Untrusted documents may supply data, never expand write capabilities. This
    lexical policy deliberately cannot establish payment recipient/amount truth
    from documents; those payments require review. No reviewer is simulated.
    """
    query = facts["query"].lower()
    if tool.startswith("get_") or tool == "read_file":
        return None
    if tool == "update_password":
        allowed = "password" in query and bool(re.search(r"\b(change|update|set|reset)\b", query))
    elif tool == "update_user_info":
        allowed = bool(re.search(r"\b(change|update|set|moved)\b", query)) and bool(
            re.search(r"\b(address|name|phone|email|profile|details)\b", query)
        )
    elif tool == "update_scheduled_transaction":
        allowed = bool(re.search(r"\b(adjust|update|change|increase|decrease)\b", query))
        if allowed:
            return "review_required: changes derived from untrusted documents"
    elif tool in {"send_money", "schedule_transaction"}:
        allowed = bool(re.search(r"\b(pay|send|transfer|schedule|recurring)\b", query))
        if allowed:
            recipients = re.findall(r"\b[a-z]{2}\d[a-z0-9]{12,32}\b", query)
            if str(arguments.get("recipient", "")).lower() not in recipients:
                return "review_required: recipient absent from original user instruction"
    else:
        return "deny: unsupported tool"
    return None if allowed else "deny: write capability absent from original user instruction"


def retail_policy(tool, arguments, facts):
    """Identity, ownership, order state; other rules stay in upstream tools/prompt."""
    if tool in {"find_user_id_by_email", "find_user_id_by_name_zip", "transfer_to_human_agents"}:
        return None
    user = facts.get("authenticated_user")
    if not user:
        return "deny: authenticate by email or name and ZIP before accessing records"
    if arguments.get("user_id", user) != user:
        return "deny: another customer's profile"
    if "order_id" in arguments:
        order = facts.get("order")
        if order is None:
            return "deny: unknown order"
        if order["user_id"] != user:
            return "deny: another customer's order"
        if tool.startswith(("cancel_pending", "modify_pending")) and order["status"] != "pending":
            return "deny: order is not pending"
        if (
            tool.startswith(("return_delivered", "exchange_delivered"))
            and order["status"] != "delivered"
        ):
            return "deny: order is not delivered"
    return None


class Boundary:
    """Same predicate in the plain application and actual SDK execution path.

    Upstream environments are process-local simulators. Do NOT use this executor
    for production or infer crash durability from these agent episodes.
    """

    name = "upstream-simulation"
    version = "1"
    supported_constraints = frozenset()

    def __init__(self, arm, home, policy, facts):
        self.arm, self.home, self.policy, self.facts = arm, home, policy, facts
        home.mkdir(parents=True, exist_ok=True)
        self.rows, self.completed = [], {}
        self.raw = None
        self.callback = None
        self.db = sqlite3.connect(home / "application-audit.db")
        self.db.execute("CREATE TABLE IF NOT EXISTS checks (body TEXT NOT NULL)")
        self.firewall = None
        if arm == "firewall":
            pack = DomainPack(
                name="benchmark-tool",
                version="1",
                policy_version=policy.__name__ + "-1",
                action_schema=ToolAction,
                resolve=self.resolve,
                evaluate=self.evaluate,
                executor=self,
            )
            self.firewall = DecisionFirewall(home / "firewall", [pack])

    def resolve(self, proposal):
        facts = self.facts(proposal.action["tool"], proposal.action["arguments"])
        return Evidence(facts=facts, versions={"snapshot": digest(facts)})

    def evaluate(self, context):
        reason = self.policy(
            context.proposal.action["tool"],
            context.proposal.action["arguments"],
            context.evidence.facts,
        )
        disposition = (
            "ALLOW"
            if reason is None
            else ("REQUIRE_REVIEW" if reason.startswith("review_required") else "DENY")
        )
        return Decision(disposition=disposition, reasons=[reason or "boundary checks passed"])

    def execute(self, key, proposal, evidence):
        if key in self.completed:
            self.raw, result = self.completed[key]
            return result
        try:
            self.raw = self.callback()
        except Exception as exc:  # noqa: BLE001 -- an unexpected adapter failure is ambiguous
            result = ExecutionResult(status="UNKNOWN", detail={"error": str(exc)})
        else:
            result = ExecutionResult(status="SUCCEEDED")
        self.completed[key] = (self.raw, result)
        return result

    def reconcile(self, key):
        return self.completed.get(key, (None, ExecutionResult(status="UNKNOWN")))[1]

    def invoke(self, tool, arguments, callback):
        started = time.perf_counter()
        facts = self.facts(tool, arguments)
        reason = self.policy(tool, arguments, facts)
        row = {
            "tool": tool,
            "would_block": reason is not None,
            "reason": reason,
            "blocked": False,
            "executed": False,
        }
        try:
            if self.arm == "baseline":
                row["executed"] = True
                return callback()
            if self.arm == "application":
                with self.db:
                    self.db.execute("INSERT INTO checks VALUES (?)", (json.dumps(row),))
                if reason:
                    row["blocked"] = True
                    raise ValueError(reason)
                row["executed"] = True
                return callback()
            proposal = Proposal(
                domain="benchmark-tool",
                message="Upstream simulated tool call",
                action={"tool": tool, "arguments": arguments},
            )
            rid = self.firewall.submit(
                proposal,
                Assessment(
                    provider="openrouter",
                    model="openai/gpt-oss-20b",
                    revision="hosted-unversioned",
                ),
            )
            evaluation = self.firewall.evaluate(rid)
            if not evaluation["authorization"]:
                row["blocked"] = True
                raise ValueError(reason or "boundary evaluation prevented execution")
            self.callback = callback
            outcome = self.firewall.execute(evaluation["authorization"])
            row["executed"] = True
            if outcome["status"] != "SUCCEEDED":
                raise ValueError(outcome.get("detail", {}).get("error", "execution incomplete"))
            return self.raw
        finally:
            row["elapsed_ms"] = (time.perf_counter() - started) * 1000
            self.rows.append(row)

    def finish(self):
        verified = None
        if self.firewall:
            receipt = self.firewall.receipt()
            verify_receipt(receipt, self.firewall.store.public)
            verified = True
        self.db.close()
        return {"calls": self.rows, "receipt_verified": verified}
