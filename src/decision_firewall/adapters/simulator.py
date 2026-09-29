"""Durable generic action recorder. It never calls external systems."""

import json
from pathlib import Path

from ..core.audit import connect, digest
from ..core.contracts import Evidence, ExecutionResult, Proposal


class SimulatedExecutor:
    name = "simulated-actions"
    version = "1"
    supported_constraints = frozenset({"exact_action", "single_use"})

    def __init__(self, path: str | Path, *, mode: str = "success"):
        if mode not in {"success", "fail", "delayed", "response_loss"}:
            raise ValueError("Unknown simulator mode")
        self.path, self.mode = Path(path), mode
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = connect(self.path)
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS effects (id TEXT PRIMARY KEY, hash TEXT NOT NULL, "
                "proposal TEXT NOT NULL, status TEXT NOT NULL)"
            )
            db.commit()
        finally:
            db.close()

    def execute(self, key: str, proposal: Proposal, evidence: Evidence) -> ExecutionResult:
        body = proposal.model_dump(mode="json")
        db = connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM effects WHERE id=?", (key,)).fetchone()
            if old:
                if old["hash"] != digest(body):
                    raise ValueError("Idempotency key reused for a different action")
                return ExecutionResult.model_validate({"status": old["status"]})
            status = (
                "FAILED"
                if self.mode == "fail"
                else "UNKNOWN"
                if self.mode == "delayed"
                else "SUCCEEDED"
            )
            db.execute(
                "INSERT INTO effects VALUES (?,?,?,?)",
                (key, digest(body), json.dumps(body), status),
            )
            db.commit()
        finally:
            db.close()
        if self.mode == "response_loss":
            raise TimeoutError("Response lost after durable simulated effect")
        return ExecutionResult.model_validate({"status": status})

    def reconcile(self, key: str) -> ExecutionResult:
        db = connect(self.path)
        try:
            row = db.execute("SELECT status FROM effects WHERE id=?", (key,)).fetchone()
            return ExecutionResult.model_validate({"status": row[0] if row else "FAILED"})
        finally:
            db.close()

    def settle(self, key: str):
        """Explicit test operation completing a delayed simulated effect."""
        db = connect(self.path)
        try:
            db.execute(
                "UPDATE effects SET status='SUCCEEDED' WHERE id=? AND status='UNKNOWN'", (key,)
            )
            db.commit()
        finally:
            db.close()
