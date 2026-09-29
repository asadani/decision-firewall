"""v0.1 refund storage compatibility. Shared audit lives in core.audit."""

from pathlib import Path

from .core.audit import Store as AuditStore
from .core.audit import canonical, connect, digest, verify_receipt  # noqa: F401
from .domains.refunds.simulator import PaymentSimulator  # noqa: F401


class Store(AuditStore):
    def __init__(self, home: Path):
        super().__init__(
            home,
            schema="""
            CREATE TABLE IF NOT EXISTS requests (
              id TEXT PRIMARY KEY, revision INTEGER NOT NULL, requester TEXT NOT NULL,
              proposal TEXT NOT NULL, assessment TEXT NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evaluations (
              id TEXT PRIMARY KEY, request_id TEXT NOT NULL, context TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews (
              id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, revision INTEGER NOT NULL,
              reviewer TEXT NOT NULL, identity_version INTEGER NOT NULL, evidence_version INTEGER,
              policy_hash TEXT NOT NULL, expires REAL NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS authorizations (
              id TEXT PRIMARY KEY, request_id TEXT NOT NULL, token TEXT NOT NULL, status TEXT NOT NULL,
              amount INTEGER NOT NULL, payment_id TEXT NOT NULL, day TEXT NOT NULL, automatic INTEGER NOT NULL,
              attempt_id TEXT, result TEXT);
        """,
        )
