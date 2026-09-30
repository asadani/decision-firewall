"""Embedded governance runtime. Plugins own domain semantics, never lifecycle state."""

import json
import time
from pathlib import Path
from uuid import uuid4

from .audit import Store, digest
from .contracts import (
    Assessment,
    Context,
    Decision,
    Evidence,
    ExecutionResult,
    Proposal,
    Review,
    RuntimeIdentity,
)
from .observation import component, observed, set_correlation
from .outcomes import audit_outcome
from .plugins import DecisionModel, DomainPack
from .policy import evaluate_context
from .preparation import PreparationResult, PreparationSpec, PreparedModel

SCHEMA = """
CREATE TABLE IF NOT EXISTS preparations (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
 id TEXT PRIMARY KEY, revision INTEGER NOT NULL, requester TEXT NOT NULL,
 proposal TEXT NOT NULL, assessment TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checks (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL, domain_hash TEXT NOT NULL,
 manifest TEXT NOT NULL, context TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
 id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, revision INTEGER NOT NULL,
 reviewer TEXT NOT NULL, generation INTEGER NOT NULL, evidence_hash TEXT NOT NULL,
 domain_hash TEXT NOT NULL, expires REAL NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS permits (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL, token TEXT NOT NULL,
 status TEXT NOT NULL, attempt TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS rule_reports (evaluation_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reservations (
 permit_id TEXT NOT NULL, domain TEXT NOT NULL, resource TEXT NOT NULL,
 units INTEGER NOT NULL, retain INTEGER NOT NULL,
 PRIMARY KEY(permit_id,resource));
"""
ALLOWED = {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
UNRESOLVED = {"RESERVED", "UNKNOWN"}


class FirewallError(ValueError):
    pass


class DecisionFirewall:
    """Register trusted domain packs; submit untrusted model output separately from intent.

    This local SQLite runtime serializes dispatch. A process with filesystem/code access
    is trusted. Do not expose its operator methods as unauthenticated network endpoints.
    """

    def __init__(
        self,
        home: str | Path,
        domains: list[DomainPack],
        *,
        identity: RuntimeIdentity | None = None,
        clock=time.time,
        observer=None,
    ):
        self.domains = {domain.name: domain for domain in domains}
        if len(self.domains) != len(domains):
            raise ValueError("Duplicate domain registration")
        self.identity = identity or RuntimeIdentity()
        self.clock = clock
        self.observer = observer
        self.store = Store(Path(home), schema=SCHEMA, filename="governance.db")

    def _event(self, db, rid, kind, data, timestamp):
        if rid:
            set_correlation(rid)
        self.store.event(db, rid, kind, data, timestamp)
        attributes = {"decision_id": rid or "operator"}
        for key in ("evaluation_id", "attempt_id", "authorization_id"):
            if key in data:
                attributes[key] = data[key]
        component("audit." + kind, **attributes)

    def _domain(self, name):
        if name not in self.domains:
            raise FirewallError(f"Domain is not registered: {name}")
        return self.domains[name]

    def _actor(self, db, name, role):
        row = db.execute("SELECT * FROM identities WHERE name=?", (name,)).fetchone()
        if not row or not row["active"] or row["role"] != role:
            raise FirewallError(f"Active {role} authority required")
        return dict(row)

    @observed("governance.configure_identity")
    def configure_identity(self, name: str, role: str, *, active: bool = True):
        """Trusted host administration; every change invalidates old authority generations."""
        if role not in {"requester", "reviewer", "executor", "auditor"}:
            raise ValueError("Unknown role")
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO identities VALUES (?,?,?,1) ON CONFLICT(name) DO UPDATE "
                "SET role=excluded.role,active=excluded.active,version=identities.version+1",
                (name, role, active),
            )
            self._event(
                db,
                None,
                "identity_changed",
                {"name": name, "role": role, "active": active},
                self.clock(),
            )

    @observed("governance.assess")
    def assess(self, model: DecisionModel, message: str) -> Assessment:
        # Model exceptions propagate. Callers may explicitly submit an unavailable assessment.
        assessment = Assessment.model_validate(model.assess(message).model_dump(mode="json"))
        component("assessment.completed", assessment_id=digest(assessment.model_dump()))
        return assessment

    @observed("governance.prepare")
    def prepare(self, proposal: Proposal, spec: PreparationSpec | None = None) -> PreparationResult:
        from .preparation import prepare

        return prepare(self, proposal, spec or PreparationSpec())

    @observed("governance.inspect_preparation")
    def inspect_preparation(self, preparation_id: str) -> PreparationResult:
        from .preparation import load

        return load(self, preparation_id)

    @observed("governance.assess_prepared")
    def assess_prepared(
        self, preparation_id: str, model: PreparedModel | None = None
    ) -> Assessment:
        from .preparation import assess_prepared

        return assess_prepared(self, preparation_id, model)

    @observed("governance.submit")
    def submit(self, proposal: Proposal, assessment: Assessment) -> str:
        proposal = self._domain(proposal.domain).validate(proposal)
        assessment = Assessment.model_validate(assessment.model_dump(mode="json"))
        # Canonical validation rejects non-JSON/NaN nested values before persistence.
        digest({"proposal": proposal.model_dump(), "assessment": assessment.model_dump()})
        rid = "decision_" + uuid4().hex
        with self.store.transaction() as db:
            self._actor(db, self.identity.requester, "requester")
            set_correlation(rid)
            component("assessment.link", assessment_id=digest(assessment.model_dump()))
            db.execute(
                "INSERT INTO decisions VALUES (?,1,?,?,?,'OPEN')",
                (
                    rid,
                    self.identity.requester,
                    proposal.model_dump_json(),
                    assessment.model_dump_json(),
                ),
            )
            self._event(
                db,
                rid,
                "proposal_submitted",
                {
                    "revision": 1,
                    "actor": self.identity.requester,
                    "proposal": proposal.model_dump(),
                    "assessment": assessment.model_dump(),
                },
                self.clock(),
            )
        return rid

    def _request(self, db, rid):
        row = db.execute("SELECT * FROM decisions WHERE id=?", (rid,)).fetchone()
        if not row:
            raise FirewallError("Request not found")
        set_correlation(row["id"])
        return dict(row)

    def _pending(self, db, rid):
        if db.execute(
            "SELECT 1 FROM permits WHERE request_id=? AND status IN "
            "('RESERVED','UNKNOWN','SUCCEEDED')",
            (rid,),
        ).fetchone():
            raise FirewallError("Inspect or reconcile the existing execution first")

    @observed("governance.revise")
    def revise(self, rid: str, proposal: Proposal, assessment: Assessment) -> int:
        proposal = self._domain(proposal.domain).validate(proposal)
        digest({"proposal": proposal.model_dump(), "assessment": assessment.model_dump()})
        with self.store.transaction() as db:
            self._actor(db, self.identity.requester, "requester")
            row = self._request(db, rid)
            self._pending(db, rid)
            if row["requester"] != self.identity.requester:
                raise FirewallError("Only the original requester may revise")
            if json.loads(row["proposal"])["domain"] != proposal.domain:
                raise FirewallError("A different domain requires a new request")
            revision = row["revision"] + 1
            db.execute(
                "UPDATE decisions SET revision=?,proposal=?,assessment=?,status='OPEN' WHERE id=?",
                (revision, proposal.model_dump_json(), assessment.model_dump_json(), rid),
            )
            db.execute(
                "UPDATE permits SET status='REVOKED' WHERE request_id=? AND status='ISSUED'", (rid,)
            )
            self._event(
                db,
                rid,
                "proposal_revised",
                {
                    "revision": revision,
                    "proposal": proposal.model_dump(),
                    "assessment": assessment.model_dump(),
                },
                self.clock(),
            )
            return revision

    def _context(self, db, row, exclude=None):
        proposal = Proposal.model_validate_json(row["proposal"])
        domain = self._domain(proposal.domain)
        started = time.perf_counter()
        status = "error"
        try:
            evidence = Evidence.model_validate(domain.resolve(proposal).model_dump(mode="json"))
            status = "ok"
        finally:
            component(
                "evidence.resolve",
                status=status,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        usage = {
            r["resource"]: r["used"]
            for r in db.execute(
                "SELECT r.resource,SUM(r.units) AS used FROM reservations r JOIN permits p "
                "ON p.id=r.permit_id WHERE r.domain=? AND (? IS NULL OR p.id!=?) AND "
                "(p.status IN ('RESERVED','UNKNOWN') OR (p.status='SUCCEEDED' AND r.retain=1)) "
                "GROUP BY r.resource",
                (domain.name, exclude, exclude),
            )
        }
        approval = db.execute(
            "SELECT a.*,i.active AS reviewer_active,i.role AS reviewer_role,"
            "i.version AS reviewer_version FROM approvals a LEFT JOIN identities i ON i.name=a.reviewer "
            "WHERE a.request_id=? AND a.revision=? ORDER BY a.id DESC LIMIT 1",
            (row["id"], row["revision"]),
        ).fetchone()
        recorded_review = Review.model_validate_json(approval["body"]) if approval else None
        review_event = db.execute(
            "SELECT body FROM events WHERE request_id=? AND json_extract(body,'$.kind')='review_recorded' "
            "ORDER BY seq DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        provenance = json.loads(review_event["body"])["data"] if review_event else {}
        valid = (
            approval
            and recorded_review is not None
            and (
                recorded_review.decision != "approve"
                or (
                    provenance.get("approval_id") == approval["id"]
                    and bool(provenance.get("evaluation_id"))
                )
            )
            and approval["reviewer_active"] == 1
            and approval["reviewer_role"] == "reviewer"
            and approval["reviewer_version"] == approval["generation"]
            and approval["expires"] > self.clock()
            and approval["evidence_hash"] == digest(evidence.model_dump())
            and approval["domain_hash"] == domain.fingerprint
        )
        # A later review supersedes earlier ones even if its actor becomes invalid.
        # Rejection is a durable veto for this revision, not expiring permission.
        rejected = approval and Review.model_validate_json(approval["body"]).decision == "reject"
        context = Context(
            proposal=proposal,
            assessment=Assessment.model_validate_json(row["assessment"]),
            evidence=evidence,
            usage=usage,
            now=self.clock(),
            review=Review.model_validate_json(approval["body"]) if valid or rejected else None,
        )
        return domain, context, approval["id"] if valid else None

    @staticmethod
    def _decide(domain, context):
        return evaluate_context(domain, context)

    @observed("governance.evaluate")
    def evaluate(self, rid: str) -> dict:
        with self.store.transaction() as db:
            row = self._request(db, rid)
            self._pending(db, rid)
            domain = self._domain(json.loads(row["proposal"])["domain"])
            context = None
            approval_id = None
            rule_results: list = []
            try:
                self._actor(db, row["requester"], "requester")
                domain, context, approval_id = self._context(db, row)
                result = evaluate_context(domain, context, rule_results)
            except Exception as exc:  # noqa: BLE001 -- plugin boundaries fail closed
                result = Decision(disposition=None, errors=[type(exc).__name__ + ": " + str(exc)])
            eid = "evaluation_" + uuid4().hex
            snapshot = context.model_dump(mode="json") if context else None
            db.execute(
                "INSERT INTO checks VALUES (?,?,?,?,?,?)",
                (
                    eid,
                    rid,
                    domain.fingerprint,
                    json.dumps(domain.manifest()),
                    json.dumps(snapshot),
                    result.model_dump_json(),
                ),
            )
            db.execute(
                "UPDATE permits SET status='REVOKED' WHERE request_id=? AND status='ISSUED'", (rid,)
            )
            status = "EVALUATION_ERROR" if result.errors else result.disposition
            db.execute(
                "UPDATE decisions SET status=? WHERE id=?", (status or "EVALUATION_ERROR", rid)
            )
            self._event(
                db,
                rid,
                "policy_evaluated",
                {
                    "id": eid,
                    "domain": domain.manifest(),
                    "context": snapshot,
                    "result": result.model_dump(),
                },
                self.clock(),
            )
            db.execute(
                "INSERT INTO rule_reports VALUES (?,?)",
                (eid, json.dumps([r.model_dump(mode="json") for r in rule_results])),
            )
            if rule_results:
                self._event(
                    db,
                    rid,
                    "rule_report",
                    {
                        "evaluation_id": eid,
                        "rules": [r.model_dump(mode="json") for r in rule_results],
                    },
                    self.clock(),
                )
            token = None
            if result.disposition in ALLOWED and not result.errors and context:
                executor = self._actor(db, self.identity.executor, "executor")
                requester = self._actor(db, row["requester"], "requester")
                payload = {
                    "schema_version": 1,
                    "id": "permit_" + uuid4().hex,
                    "request_id": rid,
                    "revision": row["revision"],
                    "proposal_hash": digest(context.proposal.model_dump()),
                    "assessment_hash": digest(context.assessment.model_dump()),
                    "evidence_hash": digest(context.evidence.model_dump()),
                    "domain_hash": domain.fingerprint,
                    "approval_id": approval_id,
                    "requester_generation": requester["version"],
                    "executor": executor["name"],
                    "executor_generation": executor["version"],
                    "expires": self.clock() + domain.authorization_seconds,
                    "decision_hash": digest(result.model_dump()),
                }
                token = self.store.sign(payload)
                db.execute(
                    "INSERT INTO permits VALUES (?,?,?,'ISSUED',NULL,NULL)",
                    (payload["id"], rid, json.dumps(token)),
                )
                self._event(db, rid, "authorization_issued", payload, self.clock())
            return {
                "evaluation_id": eid,
                "result": result.model_dump(mode="json"),
                "authorization": token,
            }

    @observed("governance.review")
    def review(
        self, rid: str, decision: Review, *, revision: int, evaluation_id: str | None = None
    ) -> dict:
        with self.store.transaction() as db:
            actor = self._actor(db, self.identity.reviewer, "reviewer")
            row = self._request(db, rid)
            if row["revision"] != revision or row["status"] not in {
                "REQUIRE_REVIEW",
                "REQUIRE_EVIDENCE",
            }:
                raise FirewallError("Stale revision or request is not awaiting review")
            domain, context, _ = self._context(db, row)
            if decision.decision == "approve":
                seen = db.execute(
                    "SELECT * FROM checks WHERE request_id=? ORDER BY rowid DESC LIMIT 1", (rid,)
                ).fetchone()
                if not evaluation_id or not seen or seen["id"] != evaluation_id:
                    raise FirewallError("Approval requires the latest inspected evaluation_id")
                snapshot = json.loads(seen["context"])
                if (
                    snapshot is None
                    or seen["domain_hash"] != domain.fingerprint
                    or digest(snapshot["proposal"]) != digest(context.proposal.model_dump())
                    or digest(snapshot["assessment"]) != digest(context.assessment.model_dump())
                    or digest(snapshot["evidence"]) != digest(context.evidence.model_dump())
                ):
                    raise FirewallError("Reviewed snapshot changed; evaluate and inspect again")
            approval_cursor = db.execute(
                "INSERT INTO approvals (request_id,revision,reviewer,generation,evidence_hash,"
                "domain_hash,expires,body) VALUES (?,?,?,?,?,?,?,?)",
                (
                    rid,
                    revision,
                    actor["name"],
                    actor["version"],
                    digest(context.evidence.model_dump()),
                    domain.fingerprint,
                    self.clock() + 3600,
                    decision.model_dump_json(),
                ),
            )
            db.execute("UPDATE decisions SET status='OPEN' WHERE id=?", (rid,))
            self._event(
                db,
                rid,
                "review_recorded",
                {
                    "actor": actor["name"],
                    "revision": revision,
                    **decision.model_dump(),
                    "evaluation_id": evaluation_id,
                    "approval_id": approval_cursor.lastrowid,
                    "evidence_hash": digest(context.evidence.model_dump()),
                },
                self.clock(),
            )
        return self.evaluate(rid)

    @observed("governance.revoke")
    def revoke(self, permit_id: str):
        with self.store.transaction() as db:
            self._actor(db, self.identity.reviewer, "reviewer")
            row = db.execute("SELECT * FROM permits WHERE id=?", (permit_id,)).fetchone()
            if not row or row["status"] != "ISSUED":
                raise FirewallError("Only an unclaimed authorization can be revoked")
            db.execute("UPDATE permits SET status='REVOKED' WHERE id=?", (permit_id,))
            self._event(
                db, row["request_id"], "authorization_revoked", {"id": permit_id}, self.clock()
            )

    def _revalidate(self, db, payload, exclude=None):
        actor = self._actor(db, self.identity.executor, "executor")
        row = self._request(db, payload["request_id"])
        requester = self._actor(db, row["requester"], "requester")
        domain, context, approval = self._context(db, row, exclude)
        bindings = {
            "revision": row["revision"],
            "proposal_hash": digest(context.proposal.model_dump()),
            "assessment_hash": digest(context.assessment.model_dump()),
            "evidence_hash": digest(context.evidence.model_dump()),
            "domain_hash": domain.fingerprint,
            "approval_id": approval,
            "requester_generation": requester["version"],
            "executor": actor["name"],
            "executor_generation": actor["version"],
        }
        if (
            any(payload.get(k) != v for k, v in bindings.items())
            or payload["expires"] <= self.clock()
        ):
            raise FirewallError("Authorization expired or bindings changed")
        result = self._decide(domain, context)
        if (
            result.errors
            or result.disposition not in ALLOWED
            or digest(result.model_dump()) != payload["decision_hash"]
        ):
            raise FirewallError("Execution-time policy or resource limits prevent dispatch")
        return domain, context, result

    @observed("governance.execute")
    def execute(self, token: dict, *, crash_after_reserve: bool = False) -> dict:
        try:
            payload = self.store.check(token)
        except Exception as exc:
            raise FirewallError("Invalid authorization signature") from exc
        with self.store.transaction() as db:
            permit = db.execute("SELECT * FROM permits WHERE id=?", (payload.get("id"),)).fetchone()
            if not permit or permit["status"] != "ISSUED" or json.loads(permit["token"]) != token:
                raise FirewallError("Authorization missing, consumed or revoked")
            domain, context, result = self._revalidate(db, payload)
            attempt = "attempt_" + uuid4().hex
            db.execute(
                "UPDATE permits SET status='RESERVED',attempt=? WHERE id=?",
                (attempt, payload["id"]),
            )
            for claim in result.claims:
                db.execute(
                    "INSERT INTO reservations VALUES (?,?,?,?,?)",
                    (payload["id"], domain.name, claim.key, claim.units, claim.retain_on_success),
                )
            self._event(
                db,
                permit["request_id"],
                "execution_reserved",
                {
                    "permit_id": payload["id"],
                    "attempt": attempt,
                    "claims": [c.model_dump() for c in result.claims],
                },
                self.clock(),
            )
        if crash_after_reserve:
            raise RuntimeError("Simulated crash after durable reservation")
        with self.store.transaction() as db:
            permit = db.execute("SELECT * FROM permits WHERE id=?", (payload["id"],)).fetchone()
            if permit["status"] != "RESERVED":
                raise FirewallError("Execution already reconciled")
            # Recheck under dispatch lock: authority/evidence may change after reservation.
            try:
                domain, context, _ = self._revalidate(db, payload, exclude=payload["id"])
            except Exception as exc:  # noqa: BLE001 -- plugin boundaries fail closed
                outcome = ExecutionResult(status="FAILED", detail={"before_dispatch": str(exc)})
            else:
                try:
                    outcome = ExecutionResult.model_validate(
                        domain.executor.execute(
                            attempt, context.proposal, context.evidence
                        ).model_dump(mode="json")
                    )
                except Exception as exc:  # noqa: BLE001 -- plugin boundaries fail closed
                    # An arbitrary adapter exception does not prove no effect occurred.
                    outcome = ExecutionResult(
                        status="UNKNOWN", detail={"error": type(exc).__name__}
                    )
            return self._finish(db, permit, outcome)

    def _finish(self, db, permit, outcome):
        outcome = audit_outcome(outcome)
        result = {
            "authorization_id": permit["id"],
            "attempt_id": permit["attempt"],
            **outcome.model_dump(mode="json"),
        }
        db.execute(
            "UPDATE permits SET status=?,result=? WHERE id=?",
            (outcome.status, json.dumps(result), permit["id"]),
        )
        status = {"SUCCEEDED": "COMPLETED", "UNKNOWN": "AWAITING_RECONCILIATION", "FAILED": "OPEN"}
        db.execute(
            "UPDATE decisions SET status=? WHERE id=?",
            (status[outcome.status], permit["request_id"]),
        )
        self._event(db, permit["request_id"], "execution_outcome", result, self.clock())
        return result

    @observed("governance.reconcile")
    def reconcile(self, permit_id: str) -> dict:
        with self.store.transaction() as db:
            self._actor(db, self.identity.executor, "executor")
            permit = db.execute("SELECT * FROM permits WHERE id=?", (permit_id,)).fetchone()
            if not permit or permit["status"] not in UNRESOLVED:
                raise FirewallError("No uncertain execution to reconcile")
            row = self._request(db, permit["request_id"])
            domain = self._domain(json.loads(row["proposal"])["domain"])
            payload = json.loads(permit["token"])["payload"]
            # A new adapter must not report authoritative absence for the old adapter's key.
            if domain.fingerprint != payload["domain_hash"]:
                raise FirewallError(
                    "Restore the original domain/adapter version for reconciliation"
                )
            try:
                result = ExecutionResult.model_validate(
                    domain.executor.reconcile(permit["attempt"]).model_dump(mode="json")
                )
            except Exception as exc:  # noqa: BLE001 -- plugin boundaries fail closed
                result = ExecutionResult(status="UNKNOWN", detail={"error": type(exc).__name__})
            return self._finish(db, permit, result)

    @observed("governance.replay")
    def replay(self, evaluation_id: str, *, domain: DomainPack | None = None) -> dict:
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM checks WHERE id=?", (evaluation_id,)).fetchone()
            if not row or json.loads(row["context"]) is None:
                raise FirewallError("No complete evaluation snapshot to replay")
            context = Context.model_validate_json(row["context"])
            domain = domain or self._domain(context.proposal.domain)
            if domain.fingerprint != row["domain_hash"]:
                raise FirewallError("Replay requires the recorded domain and policy implementation")
            result = self._decide(domain, context).model_dump(mode="json")
            return {"matches": result == json.loads(row["result"]), "result": result}

    @observed("governance.outcome")
    def outcome(self, rid: str, description: str, *, kind: str = "outcome"):
        if kind not in {"outcome", "appeal", "correction"} or not 3 <= len(description) <= 4000:
            raise ValueError("Invalid outcome event")
        with self.store.transaction() as db:
            self._actor(db, self.identity.auditor, "auditor")
            self._request(db, rid)
            self._event(
                db,
                rid,
                kind,
                {"description": description, "actor": self.identity.auditor},
                self.clock(),
            )

    def detail(self, rid: str) -> dict:
        with self.store.transaction() as db:
            row = self._request(db, rid)
            for key in ("proposal", "assessment"):
                row[key] = json.loads(row[key])
            row["events"] = [
                json.loads(e[0])
                for e in db.execute(
                    "SELECT body FROM events WHERE request_id=? ORDER BY seq", (rid,)
                )
            ]
            row["executions"] = [
                dict(p)
                for p in db.execute(
                    "SELECT id,status,attempt,result FROM permits WHERE request_id=? ORDER BY rowid",
                    (rid,),
                )
            ]
            row["policy_reports"] = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT rr.body FROM rule_reports rr JOIN checks c ON c.id=rr.evaluation_id WHERE c.request_id=? ORDER BY c.rowid",
                    (rid,),
                )
            ]
            return row

    def receipt(self) -> dict:
        return self.store.receipt()
