"""Application-owned reusable runtime extracted from the previous refund baseline.

No DecisionFirewall lifecycle, policy, signing or observation imports. Domain
business functions and the fake service are shared experimental controls.
"""

import json
import threading
import time
from functools import wraps
from uuid import uuid4

from .policies import policy
from .service import fingerprint, transaction


def operation(name):
    """Application-written hooks: defer optional export until transactions finish."""

    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            outer = not hasattr(self.local, "events")
            if outer:
                self.local.events = []
                self.local.rid = "operation_" + uuid4().hex
            started = time.perf_counter()
            status = "ok"
            try:
                return function(self, *args, **kwargs)
            except Exception:
                status = "error"
                raise
            finally:
                self.note(name, status, duration_ms=(time.perf_counter() - started) * 1000)
                if outer:
                    events = self.local.events
                    del self.local.events
                    if self.observer:
                        for event in events[:256]:
                            try:
                                self.observer(event)
                            except Exception:  # noqa: BLE001 - optional observers cannot alter decisions
                                self.observer_errors += 1

        return wrapped

    return decorate


class Application:
    def __init__(self, home, domain, config, service, clock, observer=None):
        self.path, self.domain, self.config = home / "application.db", domain, config
        self.service, self.clock, self.observer = service, clock, observer
        self.local, self.observer_errors, self.audit_unavailable = threading.local(), 0, False
        with transaction(self.path) as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, domain TEXT, body TEXT, state TEXT);
            CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY, job TEXT, event TEXT, body TEXT);
            """)

    def note(self, name, status="ok", duration_ms=0.0, **attributes):
        if self.observer and hasattr(self.local, "events"):
            self.local.events.append(
                {
                    "name": "application." + name,
                    "correlation_id": self.local.rid,
                    "status": status,
                    "duration_ms": duration_ms,
                    "attributes": attributes,
                }
            )

    def audit(self, db, rid, name, body):
        if self.audit_unavailable:
            raise OSError("Required local audit unavailable")
        db.execute(
            "INSERT INTO audit(job,event,body) VALUES (?,?,?)", (rid, name, json.dumps(body))
        )

    def read(self, db, rid):
        row = db.execute(
            "SELECT * FROM jobs WHERE id=? AND domain=?", (rid, self.domain)
        ).fetchone()
        if not row:
            raise ValueError("Unknown request")
        self.local.rid = rid
        return json.loads(row["body"]), row["state"]

    def usage(self, db, exclude=None):
        usage = {}
        for row in db.execute(
            "SELECT * FROM jobs WHERE domain=? AND state IN ('RESERVED','UNKNOWN','SUCCEEDED')",
            (self.domain,),
        ):
            if row["id"] != exclude:
                for claim in json.loads(row["body"])["claims"]:
                    if row["state"] != "SUCCEEDED" or claim["retain"]:
                        usage[claim["key"]] = usage.get(claim["key"], 0) + claim["units"]
        return usage

    def evaluate(self, db, body, exclude=None):
        started = time.perf_counter()
        facts = self.service.facts()
        self.note("evidence", duration_ms=(time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        result, reasons, claims = policy(
            self.domain,
            body["action"],
            body["label"],
            facts,
            self.config,
            body["approved"],
            self.usage(db, exclude),
        )
        self.note(
            "policy",
            result,
            (time.perf_counter() - started) * 1000,
            evaluation_id=body["evaluation_id"],
            policy_version=self.config["version"],
            reasons=reasons,
        )
        return result, reasons, claims, facts

    @operation("prepare")
    def prepare(self, action, label, assessment):
        rid = "job_" + uuid4().hex
        self.local.rid = rid
        self.note("assessment", assessment_id=fingerprint(assessment))
        body = {
            "action": action,
            "label": label,
            "assessment": assessment,
            "approved": False,
            "config": self.config,
            "expires": self.clock() + 300,
            "evaluation_id": uuid4().hex,
        }
        with transaction(self.path) as db:
            result, reasons, claims, facts = self.evaluate(db, body)
            body.update(result=result, reasons=reasons, claims=claims, facts=facts)
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,'READY')", (rid, self.domain, json.dumps(body))
            )
            self.audit(db, rid, "prepared", body)
            if result == "ALLOW":
                self.note("authorization", authorization_id=rid)
        return {"id": rid, "disposition": result}

    @operation("review")
    def approve(self, handle, authorized):
        with transaction(self.path) as db:
            body, state = self.read(db, handle["id"])
            if not authorized or state != "READY":
                raise ValueError("No review authority")
            body.update(approved=True, reviewer="reviewer", evaluation_id=uuid4().hex)
            result, reasons, claims, facts = self.evaluate(db, body)
            body.update(result=result, reasons=reasons, claims=claims, facts=facts)
            db.execute("UPDATE jobs SET body=? WHERE id=?", (json.dumps(body), handle["id"]))
            self.audit(db, handle["id"], "reviewed", body)
            if result == "ALLOW":
                self.note("authorization", authorization_id=handle["id"])
        handle["disposition"] = result

    def revoke(self, handle):
        with transaction(self.path) as db:
            db.execute("UPDATE jobs SET state='REVOKED' WHERE id=?", (handle["id"],))
            self.audit(db, handle["id"], "revoked", {})

    def valid(self, db, body, rid, exclude=None):
        if body["expires"] <= self.clock() or body["config"] != self.config:
            raise ValueError("Expired or changed authority")
        result, _, claims, facts = self.evaluate(db, body, exclude)
        if facts != body["facts"] or result != "ALLOW" or claims != body["claims"]:
            raise ValueError("Evidence, resources or policy changed")

    @operation("dispatch")
    def dispatch(self, handle):
        rid = handle["id"]
        with transaction(self.path) as db:
            body, state = self.read(db, rid)
            if state == "SUCCEEDED":
                return state
            if state != "READY" or body["result"] != "ALLOW":
                raise ValueError("No current authority")
            self.valid(db, body, rid)
            db.execute("UPDATE jobs SET state='RESERVED' WHERE id=?", (rid,))
            self.audit(db, rid, "reserved", {"attempt_id": rid})
        with transaction(self.path) as db:
            body, state = self.read(db, rid)
            try:
                if state != "RESERVED":
                    raise ValueError("Already reconciled")
                self.valid(db, body, rid, rid)
            except ValueError:
                status = "FAILED"
            else:
                try:
                    status = self.service.execute(rid, body["action"], body["facts"])
                except TimeoutError:
                    status = "UNKNOWN"
                except ValueError:
                    status = "FAILED"
            db.execute("UPDATE jobs SET state=? WHERE id=?", (status, rid))
            self.audit(db, rid, "outcome", {"status": status, "attempt_id": rid})
            self.note("outcome", status, attempt_id=rid, authorization_id=rid)
        return status

    @operation("reconciliation")
    def reconcile(self, handle):
        rid = handle["id"]
        with transaction(self.path) as db:
            _, state = self.read(db, rid)
            if state not in {"UNKNOWN", "RESERVED"}:
                return state
            status = self.service.reconcile(rid)
            db.execute("UPDATE jobs SET state=? WHERE id=?", (status, rid))
            self.audit(db, rid, "reconciled", {"status": status, "attempt_id": rid})
            self.note("outcome", status, attempt_id=rid)
            return status
