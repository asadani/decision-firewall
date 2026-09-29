"""Local governance runtime. All financial effects target PaymentSimulator only."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ...storage import PaymentSimulator, Store, digest
from .contracts import Assessment, OutcomeEvent, Policy, Proposal, ReviewDecision
from .policy import evaluate_policy


class FirewallError(ValueError):
    pass


class Firewall:
    def __init__(self, home: str | Path = ".runtime", clock=time.time):
        self.store = Store(Path(home))
        self.payments = PaymentSimulator(Path(home))
        self.clock = clock
        with self.store.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES ('policy',?)", (Policy().model_dump_json(),)
            )

    def _actor(self, db, actor, role):
        row = db.execute("SELECT * FROM identities WHERE name=?", (actor,)).fetchone()
        if not row or not row["active"] or row["role"] != role:
            raise FirewallError(f"Active {role} authority required")
        return dict(row)

    def _request(self, db, request_id):
        row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            raise FirewallError("Request not found")
        return dict(row)

    def set_policy(self, policy: Policy):
        """Trusted local operator API, not exposed through model input or the browser."""
        with self.store.transaction() as db:
            db.execute(
                "UPDATE settings SET value=? WHERE name='policy'", (policy.model_dump_json(),)
            )
            self.store.event(db, None, "policy_changed", policy.model_dump(), self.clock())

    def set_identity_active(self, actor: str, active: bool):
        """Trusted local operator API; revocation increments authority generation."""
        with self.store.transaction() as db:
            if (
                db.execute(
                    "UPDATE identities SET active=?,version=version+1 WHERE name=?", (active, actor)
                ).rowcount
                != 1
            ):
                raise FirewallError("Unknown identity")
            self.store.event(
                db, None, "identity_changed", {"actor": actor, "active": active}, self.clock()
            )

    def submit(self, proposal: Proposal, assessment: Assessment, actor="requester") -> str:
        rid = "req_" + uuid4().hex[:12]
        with self.store.transaction() as db:
            self._actor(db, actor, "requester")
            db.execute(
                "INSERT INTO requests VALUES (?,1,?,?,?,'OPEN')",
                (rid, actor, proposal.model_dump_json(), assessment.model_dump_json()),
            )
            self.store.event(
                db,
                rid,
                "proposal_submitted",
                {
                    "revision": 1,
                    "actor": actor,
                    "proposal": proposal.model_dump(),
                    "assessment": assessment.model_dump(),
                },
                self.clock(),
            )
        return rid

    def revise(self, rid: str, proposal: Proposal, assessment: Assessment, actor="requester"):
        with self.store.transaction() as db:
            self._actor(db, actor, "requester")
            request = self._request(db, rid)
            if request["requester"] != actor:
                raise FirewallError("Only the original requester may revise")
            if db.execute(
                "SELECT 1 FROM authorizations WHERE request_id=? AND status IN ('RESERVED','UNKNOWN','SUCCEEDED')",
                (rid,),
            ).fetchone():
                raise FirewallError("Resolve existing execution before creating a new request")
            revision = request["revision"] + 1
            db.execute(
                "UPDATE requests SET revision=?,proposal=?,assessment=?,status='OPEN' WHERE id=?",
                (revision, proposal.model_dump_json(), assessment.model_dump_json(), rid),
            )
            db.execute(
                "UPDATE authorizations SET status='REVOKED' WHERE request_id=? AND status='ISSUED'",
                (rid,),
            )
            self.store.event(
                db,
                rid,
                "proposal_revised",
                {
                    "revision": revision,
                    "proposal": proposal.model_dump(),
                    "assessment": assessment.model_dump(),
                    "actor": actor,
                },
                self.clock(),
            )

    def _context(self, db, request, exclude=None):
        proposal = json.loads(request["proposal"])
        payment = self.payments.get(proposal["payment_id"])
        policy = json.loads(
            db.execute("SELECT value FROM settings WHERE name='policy'").fetchone()[0]
        )
        day = datetime.fromtimestamp(self.clock(), UTC).date().isoformat()
        reserved = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM authorizations WHERE payment_id=? AND status IN ('RESERVED','UNKNOWN') AND (? IS NULL OR id!=?)",
            (proposal["payment_id"], exclude, exclude),
        ).fetchone()[0]
        used = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM authorizations WHERE day=? AND automatic=1 AND status IN ('RESERVED','UNKNOWN','SUCCEEDED') AND (? IS NULL OR id!=?)",
            (day, exclude, exclude),
        ).fetchone()[0]
        actor = db.execute(
            "SELECT * FROM identities WHERE name=?", (request["requester"],)
        ).fetchone()
        review = db.execute(
            "SELECT r.* FROM reviews r JOIN identities i ON i.name=r.reviewer WHERE r.request_id=? AND r.revision=? AND i.active=1 AND i.role='reviewer' AND i.version=r.identity_version ORDER BY r.id DESC LIMIT 1",
            (request["id"], request["revision"]),
        ).fetchone()
        valid_review = (
            review
            and review["policy_hash"] == digest(policy)
            and review["evidence_version"] == (payment["version"] if payment else None)
            and review["expires"] > self.clock()
        )
        return {
            "proposal": proposal,
            "assessment": json.loads(request["assessment"]),
            "payment": payment,
            "policy": policy,
            "reserved_minor": reserved,
            "daily_used_minor": used,
            "requester_active": bool(actor and actor["active"] and actor["role"] == "requester"),
            "requester_version": actor["version"] if actor else None,
            "review": review["decision"] if valid_review else None,
            "review_id": review["id"] if valid_review else None,
            "day": day,
        }

    def evaluate(self, rid: str) -> dict:
        with self.store.transaction() as db:
            request = self._request(db, rid)
            if db.execute(
                "SELECT 1 FROM authorizations WHERE request_id=? AND status IN ('RESERVED','UNKNOWN','SUCCEEDED')",
                (rid,),
            ).fetchone():
                raise FirewallError("Existing execution must be inspected or reconciled")
            context = self._context(db, request)
            result = evaluate_policy(context).model_dump(mode="json")
            eid = "eval_" + uuid4().hex[:12]
            db.execute(
                "INSERT INTO evaluations VALUES (?,?,?,?)",
                (eid, rid, json.dumps(context), json.dumps(result)),
            )
            db.execute(
                "UPDATE authorizations SET status='REVOKED' WHERE request_id=? AND status='ISSUED'",
                (rid,),
            )
            self.store.event(
                db,
                rid,
                "policy_evaluated",
                {"evaluation_id": eid, "context": context, "result": result},
                self.clock(),
            )
            status = "EVALUATION_ERROR" if result["errors"] else result["disposition"]
            db.execute("UPDATE requests SET status=? WHERE id=?", (status, rid))
            token = None
            if (
                result["disposition"] in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
                and not result["errors"]
            ):
                executor = self._actor(db, "executor", "executor")
                aid = "auth_" + uuid4().hex
                payload = {
                    "schema_version": 1,
                    "id": aid,
                    "request_id": rid,
                    "revision": request["revision"],
                    "proposal_hash": digest(context["proposal"]),
                    "assessment_hash": digest(context["assessment"]),
                    "evidence_version": context["payment"]["version"],
                    "policy_hash": digest(context["policy"]),
                    "review_id": context["review_id"],
                    "executor": "executor",
                    "executor_version": executor["version"],
                    "requester_version": context["requester_version"],
                    "expires": self.clock() + context["policy"]["authorization_seconds"],
                    "constraints": result["constraints"],
                }
                token = self.store.sign(payload)
                p = context["proposal"]
                db.execute(
                    "INSERT INTO authorizations VALUES (?,?,?,'ISSUED',?,?,?,?,NULL,NULL)",
                    (
                        aid,
                        rid,
                        json.dumps(token),
                        p["amount_minor"],
                        p["payment_id"],
                        context["day"],
                        context["review"] != "approve",
                    ),
                )
                self.store.event(db, rid, "authorization_issued", payload, self.clock())
            return {"evaluation_id": eid, "result": result, "authorization": token}

    def review(self, rid: str, decision: ReviewDecision, revision: int, actor="reviewer") -> dict:
        with self.store.transaction() as db:
            reviewer = self._actor(db, actor, "reviewer")
            request = self._request(db, rid)
            if revision != request["revision"]:
                raise FirewallError("Stale revision; reload the request")
            if request["status"] not in {"REQUIRE_REVIEW", "REQUIRE_EVIDENCE"}:
                raise FirewallError("Request is not awaiting review")
            context = self._context(db, request)
            db.execute(
                "INSERT INTO reviews (request_id,revision,reviewer,identity_version,evidence_version,policy_hash,expires,decision,reason) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    revision,
                    actor,
                    reviewer["version"],
                    context["payment"]["version"] if context["payment"] else None,
                    digest(context["policy"]),
                    self.clock() + 3600,
                    decision.decision,
                    decision.reason,
                ),
            )
            # Consume this reviewable state before leaving the transaction (duplicate-submit protection).
            db.execute("UPDATE requests SET status='OPEN' WHERE id=?", (rid,))
            self.store.event(
                db,
                rid,
                "review_recorded",
                {**decision.model_dump(), "actor": actor, "revision": revision},
                self.clock(),
            )
        return self.evaluate(rid)

    def revoke(self, aid: str):
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM authorizations WHERE id=?", (aid,)).fetchone()
            if not row or row["status"] != "ISSUED":
                raise FirewallError("Only an unclaimed authorization can be revoked")
            db.execute("UPDATE authorizations SET status='REVOKED' WHERE id=?", (aid,))
            self.store.event(
                db, row["request_id"], "authorization_revoked", {"id": aid}, self.clock()
            )

    def execute(
        self,
        token: dict,
        actor="executor",
        mode="success",
        action: dict | None = None,
        crash_after_reserve=False,
    ) -> dict:
        if mode not in {"success", "fail", "response_loss", "delayed"}:
            raise FirewallError("Unknown simulator mode")
        try:
            payload = self.store.check(token)
        except Exception as exc:
            raise FirewallError("Invalid authorization signature") from exc
        with self.store.transaction() as db:
            executor = self._actor(db, actor, "executor")
            auth = db.execute(
                "SELECT * FROM authorizations WHERE id=?", (payload["id"],)
            ).fetchone()
            if not auth or auth["status"] != "ISSUED" or json.loads(auth["token"]) != token:
                raise FirewallError("Authorization missing, consumed, or revoked")
            if payload["executor"] != actor or payload["executor_version"] != executor["version"]:
                raise FirewallError("Wrong executor or revoked authority generation")
            if payload["expires"] <= self.clock():
                raise FirewallError("Authorization expired")
            request = self._request(db, payload["request_id"])
            context = self._context(db, request)
            if context["requester_version"] != payload.get("requester_version"):
                raise FirewallError("Requester authority generation changed")
            if (
                request["revision"] != payload["revision"]
                or digest(context["proposal"]) != payload["proposal_hash"]
                or digest(context["assessment"]) != payload["assessment_hash"]
                or digest(context["policy"]) != payload["policy_hash"]
                or not context["payment"]
                or context["payment"]["version"] != payload["evidence_version"]
                or context["review_id"] != payload["review_id"]
            ):
                raise FirewallError("Authorization bindings are stale")
            if set(payload["constraints"]) - {"original_destination", "exact_amount", "single_use"}:
                raise FirewallError("Unsupported constraint")
            result = evaluate_policy(context)
            if result.errors or result.disposition not in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}:
                raise FirewallError(
                    "Execution-time policy prevents dispatch: "
                    + ", ".join(result.reasons + result.errors)
                )
            p = context["proposal"]
            expected = {k: p[k] for k in ("payment_id", "amount_minor", "currency", "destination")}
            if action is not None and action != expected:
                raise FirewallError("Action differs from authorization")
            attempt_id = "attempt_" + uuid4().hex
            db.execute(
                "UPDATE authorizations SET status='RESERVED',attempt_id=?,day=? WHERE id=?",
                (attempt_id, context["day"], payload["id"]),
            )
            self.store.event(
                db,
                request["id"],
                "execution_reserved",
                {"authorization_id": payload["id"], "attempt_id": attempt_id, "action": expected},
                self.clock(),
            )
        if crash_after_reserve:
            raise RuntimeError("Simulated crash after durable reservation")
        # Holding the firewall write lock across dispatch excludes concurrent reconciliation.
        # A process crash releases the lock; the durable downstream ledger resolves uncertainty.
        with self.store.transaction() as db:
            auth = db.execute(
                "SELECT * FROM authorizations WHERE id=?", (payload["id"],)
            ).fetchone()
            if auth["status"] != "RESERVED":
                raise FirewallError("Execution already reconciled")
            # Reservation and dispatch are separate transactions. Revalidate authority
            # and policy again under the dispatch lock, excluding our own reservation.
            try:
                current_executor = self._actor(db, actor, "executor")
                current_request = self._request(db, payload["request_id"])
                current = self._context(db, current_request, exclude=auth["id"])
                bindings_valid = (
                    current_executor["version"] == payload["executor_version"]
                    and self.clock() < payload["expires"]
                    and current_request["revision"] == payload["revision"]
                    and current["requester_version"] == payload["requester_version"]
                    and digest(current["proposal"]) == payload["proposal_hash"]
                    and digest(current["assessment"]) == payload["assessment_hash"]
                    and digest(current["policy"]) == payload["policy_hash"]
                    and current["payment"] is not None
                    and current["payment"]["version"] == payload["evidence_version"]
                    and current["review_id"] == payload["review_id"]
                )
                recheck = evaluate_policy(current)
                if (
                    not bindings_valid
                    or recheck.errors
                    or recheck.disposition not in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
                ):
                    raise FirewallError("Dispatch-time authorization changed")
                db.execute(
                    "UPDATE authorizations SET day=? WHERE id=?", (current["day"], auth["id"])
                )
            except (ValueError, KeyError, TypeError):
                self._finish(db, auth, "FAILED")
                return {
                    "authorization_id": payload["id"],
                    "attempt_id": attempt_id,
                    "status": "FAILED",
                }
            try:
                status = self.payments.execute(
                    attempt_id, expected, mode, expected_version=payload["evidence_version"]
                )
                status = "UNKNOWN" if status == "PENDING" else status
            except TimeoutError:
                status = "UNKNOWN"
            except ValueError:
                status = "FAILED"
            self._finish(db, auth, status)
        return {"authorization_id": payload["id"], "attempt_id": attempt_id, "status": status}

    def _finish(self, db, auth, status):
        result = {"status": status, "attempt_id": auth["attempt_id"]}
        db.execute(
            "UPDATE authorizations SET status=?,result=? WHERE id=?",
            (status, json.dumps(result), auth["id"]),
        )
        db.execute(
            "UPDATE requests SET status=? WHERE id=?",
            (
                "REFUNDED"
                if status == "SUCCEEDED"
                else "AWAITING_RECONCILIATION"
                if status == "UNKNOWN"
                else "OPEN",
                auth["request_id"],
            ),
        )
        self.store.event(
            db,
            auth["request_id"],
            "execution_outcome",
            {"authorization_id": auth["id"], **result},
            self.clock(),
        )

    def reconcile(self, aid: str, actor="executor", settle=False) -> dict:
        with self.store.transaction() as db:
            self._actor(db, actor, "executor")
            auth = db.execute("SELECT * FROM authorizations WHERE id=?", (aid,)).fetchone()
            if not auth or auth["status"] not in {"RESERVED", "UNKNOWN"}:
                raise FirewallError("No uncertain execution to reconcile")
            status = self.payments.lookup(auth["attempt_id"], settle=settle)
            # In this authoritative local simulator, absence with the dispatch lock held is definitive.
            status = "UNKNOWN" if status == "PENDING" else status or "FAILED"
            self._finish(db, auth, status)
            return {"authorization_id": aid, "status": status}

    def outcome(self, rid: str, event: OutcomeEvent, actor="auditor"):
        with self.store.transaction() as db:
            self._actor(db, actor, "auditor")
            self._request(db, rid)
            self.store.event(
                db, rid, event.kind, {**event.model_dump(), "actor": actor}, self.clock()
            )

    def replay(self, evaluation_id: str) -> dict:
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM evaluations WHERE id=?", (evaluation_id,)).fetchone()
            if not row:
                raise FirewallError("Evaluation not found")
            actual = evaluate_policy(json.loads(row["context"])).model_dump(mode="json")
            return {"matches": actual == json.loads(row["result"]), "result": actual}

    def detail(self, rid: str) -> dict:
        with self.store.transaction() as db:
            request = self._request(db, rid)
            for field in ("proposal", "assessment"):
                request[field] = json.loads(request[field])
            request["events"] = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM events WHERE request_id=? ORDER BY seq", (rid,)
                )
            ]
            request["authorizations"] = [
                {k: v for k, v in dict(r).items() if k != "token"}
                for r in db.execute(
                    "SELECT * FROM authorizations WHERE request_id=? ORDER BY rowid DESC", (rid,)
                )
            ]
            request["evaluations"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM evaluations WHERE request_id=? ORDER BY rowid DESC", (rid,)
                )
            ]
            request["evidence"] = self.payments.get(request["proposal"]["payment_id"])
            return request

    def list_requests(self, search="", status="", page=1, page_size=10) -> dict:
        page_size = max(1, min(page_size, 50))
        where = "WHERE (id LIKE ? OR proposal LIKE ?) AND (?='' OR status=?)"
        args = (f"%{search}%", f"%{search}%", status, status)
        with self.store.transaction() as db:
            count = db.execute("SELECT COUNT(*) FROM requests " + where, args).fetchone()[0]
            pages = max(1, (count + page_size - 1) // page_size)
            page = min(max(page, 1), pages)
            rows = db.execute(
                "SELECT * FROM requests " + where + " ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (*args, page_size, (page - 1) * page_size),
            )
            return {
                "items": [{**dict(r), "proposal": json.loads(r["proposal"])} for r in rows],
                "count": count,
                "page": page,
                "pages": pages,
            }
