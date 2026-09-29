"""Independent competent application baseline. No framework gate/runtime calls.

Shares only the simulated payment service with the other treatments. This is
benchmark reference code, not a production application or a replacement library.
"""

import json
import sqlite3
from contextlib import contextmanager
from uuid import uuid4


def decide(action, label, payment, policy, approved=False, reserved=0, budget=0):
    if payment is None:
        return "REQUIRE_EVIDENCE"
    if (
        action["customer_id"] != payment["customer_id"]
        or action["destination"] != payment["destination"]
        or action["currency"] != payment["currency"]
        or action["amount_minor"] > payment["amount_minor"] - payment["refunded_minor"] - reserved
    ):
        return "DENY"
    if label == "unavailable":
        return "REQUIRE_REVIEW"
    reason = action["requested_reason"]
    if reason == "duplicate":
        if payment["duplicate_verified"] is None:
            return "REQUIRE_EVIDENCE"
        if not payment["duplicate_verified"]:
            return "DENY"
    elif reason == "cancellation":
        if payment["unused"] is None or payment["age_days"] is None:
            return "REQUIRE_EVIDENCE"
        if not payment["unused"] or payment["age_days"] > policy["cancellation_days"]:
            return "DENY"
    if not approved and (
        reason == "other"
        or label != reason
        or action["amount_minor"] > policy["auto_amount_minor"]
        or budget + action["amount_minor"] > policy["daily_auto_limit_minor"]
    ):
        return "REQUIRE_REVIEW"
    return "ALLOW"


class Application:
    def __init__(self, home, payments, policy, clock):
        self.path, self.payments, self.policy, self.clock = (
            home / "application.db",
            payments,
            policy,
            clock,
        )
        self.audit_unavailable = False
        with self.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, action TEXT, label TEXT, evidence TEXT, approved INTEGER,
                disposition TEXT, expires REAL, state TEXT);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, job TEXT, event TEXT);
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def audit(self, db, job, event):
        if self.audit_unavailable:
            raise OSError("Injected required local audit outage")
        db.execute("INSERT INTO audit(job,event) VALUES (?,?)", (job, event))

    def usage(self, db, payment_id, exclude=None):
        reserved = budget = 0
        for row in db.execute(
            "SELECT * FROM jobs WHERE state IN ('RESERVED','UNKNOWN','SUCCEEDED')"
        ):
            if row["id"] == exclude:
                continue
            action = json.loads(row["action"])
            if action["payment_id"] == payment_id and row["state"] != "SUCCEEDED":
                reserved += action["amount_minor"]
            # The benchmark clock never crosses a UTC day. This app targets this daily window.
            if not row["approved"]:
                budget += action["amount_minor"]
        return reserved, budget

    def prepare(self, action, label):
        with self.transaction() as db:
            payment = self.payments.get(action["payment_id"])
            reserved, budget = self.usage(db, action["payment_id"])
            result = decide(action, label, payment, self.policy, reserved=reserved, budget=budget)
            job = "job_" + uuid4().hex
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                (
                    job,
                    json.dumps(action),
                    label,
                    json.dumps(payment),
                    False,
                    result,
                    self.clock() + self.policy["authorization_seconds"],
                    "READY",
                ),
            )
            self.audit(db, job, "prepared:" + result)
        return {"id": job, "disposition": result}

    def approve(self, handle, authorized):
        if not authorized:
            raise ValueError("Unauthorized reviewer")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (handle["id"],)).fetchone()
            action = json.loads(row["action"])
            payment = self.payments.get(action["payment_id"])
            reserved, budget = self.usage(db, action["payment_id"])
            result = decide(action, row["label"], payment, self.policy, True, reserved, budget)
            db.execute(
                "UPDATE jobs SET approved=1,disposition=?,evidence=? WHERE id=?",
                (result, json.dumps(payment), handle["id"]),
            )
            self.audit(db, handle["id"], "reviewed:" + result)
        handle["disposition"] = result

    def revoke(self, handle):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET state='REVOKED' WHERE id=?", (handle["id"],))
            self.audit(db, handle["id"], "revoked")

    def dispatch(self, handle, mode="success", override=None):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (handle["id"],)).fetchone()
            if row["state"] == "SUCCEEDED":
                return "SUCCEEDED"
            if (
                row["state"] != "READY"
                or row["disposition"] != "ALLOW"
                or row["expires"] <= self.clock()
            ):
                raise ValueError("No current application authority")
            action = json.loads(row["action"])
            if override is not None and override != action:
                raise ValueError("Stored action binding mismatch")
            payment = self.payments.get(action["payment_id"])
            if payment != json.loads(row["evidence"]):
                raise ValueError("Evidence changed")
            reserved, budget = self.usage(db, action["payment_id"])
            if (
                decide(
                    action,
                    row["label"],
                    payment,
                    self.policy,
                    bool(row["approved"]),
                    reserved,
                    budget,
                )
                != "ALLOW"
            ):
                raise ValueError("Dispatch-time policy prevents execution")
            db.execute("UPDATE jobs SET state='RESERVED' WHERE id=?", (handle["id"],))
            self.audit(db, handle["id"], "reserved")
        # Reservation is durable before contacting the separate payment service.
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (handle["id"],)).fetchone()
            current = self.payments.get(action["payment_id"])
            if row["state"] != "RESERVED" or row["expires"] <= self.clock() or current != payment:
                raise ValueError("Authority changed before dispatch")
            reserved, budget = self.usage(db, action["payment_id"], exclude=handle["id"])
            if (
                decide(
                    action,
                    row["label"],
                    current,
                    self.policy,
                    bool(row["approved"]),
                    reserved,
                    budget,
                )
                != "ALLOW"
            ):
                raise ValueError("Resources changed before dispatch")
            payload = {
                k: action[k] for k in ("payment_id", "amount_minor", "currency", "destination")
            }
            try:
                result = self.payments.execute(
                    handle["id"], payload, mode, expected_version=payment["version"]
                )
                result = "UNKNOWN" if result == "PENDING" else result
            except TimeoutError:
                result = "UNKNOWN"
            except ValueError:
                result = "FAILED"
            db.execute("UPDATE jobs SET state=? WHERE id=?", (result, handle["id"]))
            self.audit(db, handle["id"], "outcome:" + result)
        return result

    def reconcile(self, handle):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (handle["id"],)).fetchone()
            if row["state"] not in {"RESERVED", "UNKNOWN"}:
                return row["state"]
            result = self.payments.lookup(handle["id"])
            result = "UNKNOWN" if result == "PENDING" else result or "FAILED"
            db.execute("UPDATE jobs SET state=? WHERE id=?", (result, handle["id"]))
            self.audit(db, handle["id"], "reconciled:" + result)
            return result
