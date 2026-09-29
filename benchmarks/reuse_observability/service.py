"""Common durable fake action service. No governance or authorization logic."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@contextmanager
def transaction(path):
    db = sqlite3.connect(path, timeout=30)
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


class Service:
    def __init__(self, home, domain):
        self.path = home / "effects.db"
        self.facts_path = home / f"{domain}-facts.json"
        self.mode = "success"
        with transaction(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS effects (id TEXT PRIMARY KEY, body TEXT, status TEXT)"
            )

    def facts(self):
        return json.loads(self.facts_path.read_text(encoding="utf-8"))

    def execute(self, key, action, evidence):
        with transaction(self.path) as db:
            old = db.execute("SELECT * FROM effects WHERE id=?", (key,)).fetchone()
            if old:
                if json.loads(old["body"]) != action:
                    raise ValueError("Idempotency payload mismatch")
                return old["status"]
            if self.facts() != evidence:
                raise ValueError("Service evidence version changed")
            db.execute("INSERT INTO effects VALUES (?,?,?)", (key, json.dumps(action), "SUCCEEDED"))
        if self.mode == "response_loss":
            raise TimeoutError("Response loss after commit")
        return "SUCCEEDED"

    def reconcile(self, key):
        with transaction(self.path) as db:
            row = db.execute("SELECT status FROM effects WHERE id=?", (key,)).fetchone()
            return row[0] if row else "FAILED"

    def count(self):
        with transaction(self.path) as db:
            return db.execute("SELECT COUNT(*) FROM effects WHERE status='SUCCEEDED'").fetchone()[0]
