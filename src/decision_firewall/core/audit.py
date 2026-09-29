"""Domain-neutral transactional storage, canonical signing and linked audit verification."""

import base64
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(value: dict) -> bytes:
    return rfc8785.dumps(value)


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=FULL")
    return db


class Store:
    def __init__(self, home: Path, schema: str = "", filename: str = "firewall.db"):
        self.home = home
        home.mkdir(parents=True, exist_ok=True)
        self.path = home / filename
        keyfile = home / "signing.key"
        if not keyfile.exists():
            private = Ed25519PrivateKey.generate().private_bytes_raw()
            try:
                with keyfile.open("xb") as stream:
                    stream.write(private)
                keyfile.chmod(0o600)
            except FileExistsError:
                pass
        self.key = Ed25519PrivateKey.from_private_bytes(keyfile.read_bytes())
        self.public = self.key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        with self.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS identities (
              name TEXT PRIMARY KEY, role TEXT NOT NULL, active INTEGER NOT NULL, version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY, request_id TEXT, body TEXT NOT NULL,
              hash TEXT NOT NULL, signature TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            db.executescript(schema)
            for name, role in [
                ("requester", "requester"),
                ("reviewer", "reviewer"),
                ("executor", "executor"),
                ("auditor", "auditor"),
            ]:
                db.execute("INSERT OR IGNORE INTO identities VALUES (?,?,1,1)", (name, role))

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

    def sign(self, payload: dict) -> dict:
        return {
            "payload": payload,
            "signature": base64.b64encode(self.key.sign(canonical(payload))).decode(),
        }

    def check(self, token: dict) -> dict:
        self.key.public_key().verify(
            base64.b64decode(token["signature"]), canonical(token["payload"])
        )
        return token["payload"]

    def event(self, db, request_id, kind, data, timestamp):
        previous = db.execute("SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        body = {
            "schema_version": 1,
            "seq": previous["seq"] + 1 if previous else 1,
            "previous": previous["hash"] if previous else "0" * 64,
            "request_id": request_id,
            "kind": kind,
            "timestamp": timestamp,
            "data": data,
        }
        signed = self.sign(body)
        db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            (body["seq"], request_id, json.dumps(body), digest(body), signed["signature"]),
        )

    def receipt(self) -> dict:
        with self.transaction() as db:
            events = [dict(x) for x in db.execute("SELECT * FROM events ORDER BY seq")]
        checkpoint = {"count": len(events), "head": events[-1]["hash"] if events else "0" * 64}
        return {
            "public_key": base64.b64encode(self.public).decode(),
            "events": events,
            "checkpoint": self.sign(checkpoint),
        }


def verify_receipt(receipt: dict, trusted_public_key: bytes) -> bool:
    """Caller supplies its trusted key: an embedded key is not a trust anchor."""
    key = Ed25519PublicKey.from_public_bytes(trusted_public_key)
    previous = "0" * 64
    for i, event in enumerate(receipt["events"], 1):
        body = json.loads(event["body"])
        if event.get("seq") != body["seq"] or event.get("request_id") != body["request_id"]:
            raise ValueError("Audit envelope does not match signed body")
        if body["seq"] != i or body["previous"] != previous or digest(body) != event["hash"]:
            raise ValueError("Broken audit chain")
        key.verify(base64.b64decode(event["signature"]), canonical(body))
        previous = event["hash"]
    checkpoint = receipt["checkpoint"]
    key.verify(base64.b64decode(checkpoint["signature"]), canonical(checkpoint["payload"]))
    if checkpoint["payload"] != {"count": len(receipt["events"]), "head": previous}:
        raise ValueError("Checkpoint mismatch")
    return True
