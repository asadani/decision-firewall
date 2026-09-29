"""Deployment rules and a durable local registry/executor; no deployment APIs."""

import json
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import Field

from ...core.audit import connect, digest
from ...core.contracts import (
    Claim,
    Decision,
    Disposition,
    Evidence,
    ExecutionResult,
    Proposal,
    Record,
)
from ...core.plugins import DomainPack
from ...core.rules import Rule, RuleResult, RuleSet


class DeploymentAction(Record):
    service: str = Field(min_length=1)
    artifact: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    environment: Literal["staging", "production"]


class Artifact(Record):
    service: str = Field(min_length=1)
    approved: bool = Field(strict=True)
    environments: list[Literal["staging", "production"]]


class Environment(Record):
    enabled: bool = Field(strict=True)


def restrictions(action: DeploymentAction, facts: dict) -> list[str]:
    artifact, environment = facts["artifact"], facts["environment"]
    reasons = []
    if not artifact["approved"]:
        reasons.append("artifact_not_approved")
    if artifact["service"] != action.service:
        reasons.append("artifact_service_mismatch")
    if action.environment not in artifact["environments"]:
        reasons.append("artifact_environment_prohibited")
    if not environment["enabled"]:
        reasons.append("environment_frozen")
    return reasons


class DeploymentSimulator:
    """Trusted local administration and simulated effects in one atomic ledger."""

    name = "simulated-deployments"
    version = "1"
    supported_constraints = frozenset({"exact_action", "single_use", "registry_snapshot"})

    def __init__(self, home: str | Path, *, mode: str = "success"):
        if mode not in {"success", "fail", "delayed", "response_loss"}:
            raise ValueError("Unknown deployment simulation mode")
        self.path = Path(home) / "deployments.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        with closing(connect(self.path)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS registry (
                    kind TEXT, name TEXT, body TEXT NOT NULL, version INTEGER NOT NULL,
                    PRIMARY KEY (kind, name));
                CREATE TABLE IF NOT EXISTS deployments (
                    id TEXT PRIMARY KEY, hash TEXT NOT NULL, action TEXT NOT NULL,
                    environment TEXT NOT NULL, status TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS active_deployment
                    ON deployments(environment) WHERE status='UNKNOWN';
            """)

    def register(self, kind: Literal["artifact", "environment"], name: str, record: dict):
        """Trusted administration only. Every update advances the evidence version."""
        if kind not in {"artifact", "environment"}:
            raise ValueError("Unknown registry kind")
        schema = Artifact if kind == "artifact" else Environment
        body = schema.model_validate(record).model_dump(mode="json")
        with closing(connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO registry VALUES (?,?,?,1) ON CONFLICT(kind,name) DO UPDATE "
                "SET body=excluded.body, version=registry.version+1",
                (kind, name, json.dumps(body)),
            )

    def _resolve(self, db, action: DeploymentAction) -> Evidence:
        facts, versions, missing = {}, {}, []
        for kind, name in (("artifact", action.artifact), ("environment", action.environment)):
            row = db.execute(
                "SELECT body,version FROM registry WHERE kind=? AND name=?", (kind, name)
            ).fetchone()
            if row is None:
                missing.append(kind)
            else:
                facts[kind] = json.loads(row["body"])
                versions[kind] = str(row["version"])
        return Evidence(facts=facts, versions=versions, missing=missing)

    def resolve(self, proposal: Proposal) -> Evidence:
        with closing(connect(self.path)) as db, db:
            db.execute("BEGIN")
            return self._resolve(db, DeploymentAction.model_validate(proposal.action))

    def execute(self, key: str, proposal: Proposal, evidence: Evidence) -> ExecutionResult:
        action = DeploymentAction.model_validate(proposal.action)
        body = proposal.model_dump(mode="json")
        with closing(connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM deployments WHERE id=?", (key,)).fetchone()
            if old:
                if old["hash"] != digest(body):
                    raise ValueError("Idempotency key reused for a different deployment")
                return ExecutionResult(status=old["status"])
            current = self._resolve(db, action)
            busy = db.execute(
                "SELECT 1 FROM deployments WHERE environment=? AND status='UNKNOWN'",
                (action.environment,),
            ).fetchone()
            prohibited = current != evidence or bool(current.missing)
            if not prohibited:
                prohibited = bool(restrictions(action, current.facts)) or bool(busy)
            status = (
                "FAILED"
                if prohibited or self.mode == "fail"
                else "UNKNOWN"
                if self.mode == "delayed"
                else "SUCCEEDED"
            )
            db.execute(
                "INSERT INTO deployments VALUES (?,?,?,?,?)",
                (key, digest(body), json.dumps(body), action.environment, status),
            )
        if self.mode == "response_loss" and status == "SUCCEEDED":
            raise TimeoutError("Response lost after durable simulated deployment")
        return ExecutionResult.model_validate({"status": status})

    def reconcile(self, key: str) -> ExecutionResult:
        with closing(connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM deployments WHERE id=?", (key,)).fetchone()
            # Synchronous local dispatch: no remote queue can accept this key later.
            return ExecutionResult(status=row[0] if row else "FAILED")

    def settle(self, key: str):
        """Complete an already accepted simulated job, without dispatching again."""
        with closing(connect(self.path)) as db, db:
            db.execute(
                "UPDATE deployments SET status='SUCCEEDED' WHERE id=? AND status='UNKNOWN'",
                (key,),
            )


def deployment_domain(home: str | Path, *, mode: str = "success") -> DomainPack:
    simulator = DeploymentSimulator(home, mode=mode)

    def mandatory(context, config):
        if context.evidence.missing:
            return RuleResult(status="evidence", reasons=context.evidence.missing)
        reasons = restrictions(
            DeploymentAction.model_validate(context.proposal.action), context.evidence.facts
        )
        return RuleResult(status="deny", reasons=reasons) if reasons else RuleResult()

    def production(context, config):
        if context.proposal.action["environment"] == "production":
            return RuleResult(status="review", reasons=["production_requires_review"])
        return RuleResult()

    rules = RuleSet(
        [
            Rule(
                "registry_restrictions",
                "1",
                "Approved artifact and enabled environment",
                mandatory,
                Record(),
            ),
            Rule(
                "production_review",
                "1",
                "Production needs authorized review",
                production,
                Record(),
                kind="review",
            ),
        ],
        finalize=lambda context: Decision(
            disposition=Disposition.ALLOW_WITH_CONSTRAINTS,
            reasons=["deployment_eligible"],
            constraints=["exact_action", "single_use", "registry_snapshot"],
            claims=[
                Claim(
                    key=f"environment:{context.proposal.action['environment']}", units=1, capacity=1
                )
            ],
        ),
    )
    return DomainPack(
        name="deployments",
        version="1",
        policy_version="deployment-demo-v1",
        action_schema=DeploymentAction,
        resolve=simulator.resolve,
        evaluate=rules,
        executor=simulator,
        authorization_seconds=120,
        policy_config={"simulated": True},
    )
