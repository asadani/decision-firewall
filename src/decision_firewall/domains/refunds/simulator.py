"""Durable refund simulator; no real payment API."""

import json
from contextlib import contextmanager
from pathlib import Path

from ...core.audit import connect
from .contracts import Payment


class PaymentSimulator:
    def __init__(self, home: Path):
        self.path = home / "payments.db"
        with self.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS refunds (id TEXT PRIMARY KEY, payment_id TEXT NOT NULL,
              amount INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    @contextmanager
    def transaction(self):
        db = connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self, payment: Payment):
        if payment.refunded_minor > payment.amount_minor:
            raise ValueError("Refunded amount exceeds payment")
        with self.transaction() as db:
            db.execute(
                "INSERT INTO payments VALUES (?,?)", (payment.payment_id, payment.model_dump_json())
            )

    def get(self, payment_id: str) -> dict | None:
        with self.transaction() as db:
            row = db.execute("SELECT body FROM payments WHERE id=?", (payment_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def update_evidence(self, payment_id: str, **changes):
        if set(changes) - {"duplicate_verified", "age_days", "unused"}:
            raise ValueError("Only evidence fields may be updated")
        with self.transaction() as db:
            body = json.loads(
                db.execute("SELECT body FROM payments WHERE id=?", (payment_id,)).fetchone()[0]
            )
            body.update(changes)
            body["version"] += 1
            payment = Payment.model_validate(body)
            db.execute(
                "UPDATE payments SET body=? WHERE id=?", (payment.model_dump_json(), payment_id)
            )

    def execute(
        self, key: str, payload: dict, mode: str = "success", expected_version: int | None = None
    ) -> str:
        if type(payload.get("amount_minor")) is not int:
            raise ValueError("Refund amounts must be integer minor units")
        if mode not in {"success", "fail", "response_loss", "delayed"}:
            raise ValueError("Unsupported simulator mode")
        with self.transaction() as db:
            existing = db.execute("SELECT * FROM refunds WHERE id=?", (key,)).fetchone()
            if existing:
                if json.loads(existing["payload"]) != payload:
                    raise ValueError("Idempotency payload mismatch")
                return existing["status"]
            row = db.execute(
                "SELECT body FROM payments WHERE id=?", (payload["payment_id"],)
            ).fetchone()
            if not row:
                raise ValueError("Payment missing")
            payment = json.loads(row[0])
            if expected_version is not None and payment["version"] != expected_version:
                raise ValueError("Downstream evidence version changed before commit")
            pending = db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM refunds WHERE payment_id=? AND status='PENDING'",
                (payload["payment_id"],),
            ).fetchone()[0]
            if (
                payload["amount_minor"] <= 0
                or payload["amount_minor"]
                > payment["amount_minor"] - payment["refunded_minor"] - pending
            ):
                raise ValueError("Downstream refundable balance exceeded")
            if (
                payload["destination"] != payment["destination"]
                or payload["currency"] != payment["currency"]
            ):
                raise ValueError("Downstream destination mismatch")
            status = "FAILED" if mode == "fail" else "PENDING" if mode == "delayed" else "SUCCEEDED"
            db.execute(
                "INSERT INTO refunds VALUES (?,?,?,?,?)",
                (key, payload["payment_id"], payload["amount_minor"], status, json.dumps(payload)),
            )
            if status == "SUCCEEDED":
                payment["refunded_minor"] += payload["amount_minor"]
                payment["version"] += 1
                db.execute(
                    "UPDATE payments SET body=? WHERE id=?",
                    (json.dumps(payment), payload["payment_id"]),
                )
        if mode == "response_loss":
            raise TimeoutError("Simulated response loss after committed refund")
        return status

    def lookup(self, key: str, settle: bool = False) -> str | None:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM refunds WHERE id=?", (key,)).fetchone()
            if not row:
                return None
            if settle and row["status"] == "PENDING":
                payment = json.loads(
                    db.execute(
                        "SELECT body FROM payments WHERE id=?", (row["payment_id"],)
                    ).fetchone()[0]
                )
                payment["refunded_minor"] += row["amount"]
                payment["version"] += 1
                db.execute(
                    "UPDATE payments SET body=? WHERE id=?",
                    (json.dumps(payment), row["payment_id"]),
                )
                db.execute("UPDATE refunds SET status='SUCCEEDED' WHERE id=?", (key,))
                return "SUCCEEDED"
            return row["status"]
