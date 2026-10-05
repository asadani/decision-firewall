"""Thin test bridges over existing applications, with an independent effect oracle.

The application branch imports no Decision Firewall modules. Fault injection lives
in faults.py, never in the healthy adapter. All effects are local simulations.
"""

import json
import subprocess
import sys
from pathlib import Path

from benchmarks.reuse_observability.application import Application
from benchmarks.reuse_observability.policies import configuration
from benchmarks.reuse_observability.service import Service, fingerprint, transaction
from control_conformance import Observation


class ObservedService(Service):
    """Persist calls before downstream checks so those checks cannot mask dispatch."""

    def __init__(self, home):
        super().__init__(home, "export")
        with transaction(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS calls (seq INTEGER PRIMARY KEY, kind, key)")

    def record(self, kind, key):
        with transaction(self.path) as db:
            db.execute("INSERT INTO calls(kind,key) VALUES (?,?)", (kind, key))

    def execute(self, key, action, evidence):
        self.record("dispatch", key)
        return super().execute(key, action, evidence)

    def reconcile(self, key):
        self.record("lookup", key)
        return super().reconcile(key)

    def observe(self, expected_action):
        with transaction(self.path) as db:
            calls = list(db.execute("SELECT kind,key FROM calls ORDER BY seq"))
            effects = list(
                db.execute("SELECT body FROM effects WHERE status='SUCCEEDED' ORDER BY id")
            )
        return Observation(
            len(effects),
            tuple(r["key"] for r in calls if r["kind"] == "dispatch"),
            tuple(r["key"] for r in calls if r["kind"] == "lookup"),
            fingerprint(expected_action),
            tuple(fingerprint(json.loads(r["body"])) for r in effects),
            fingerprint(self.facts()),
        )


class Bridge:
    def __init__(self, home, scenario, arm, fault=None, *, resume=False):
        self.home, self.scenario, self.arm, self.fault = Path(home), scenario, arm, fault
        self.service = ObservedService(self.home)
        self.service.mode = "response_loss" if scenario == "lost_response" else "success"
        self.action = {"destination": "original", "rows": 1500}
        if not resume:
            self.service.facts_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "active": True,
                        "destination": "original",
                        "available_rows": 5000,
                        "legal_hold": False,
                    }
                ),
                encoding="utf-8",
            )
        engine = Application
        if arm == "framework":
            from benchmarks.reuse_observability.framework import Framework

            engine = Framework
        self.engine = engine(
            self.home, "export", configuration("export"), self.service, lambda: 1000
        )
        if resume:
            self.handle = json.loads((self.home / "handle.json").read_text(encoding="utf-8"))
        if fault:
            from .faults import inject

            inject(self)

    def prepare(self):
        assessment = {
            "provider": "fixture",
            "model": "controlled",
            "revision": "1",
            "signals": {"request_type": {"kind": "choice", "value": "export"}},
        }
        self.handle = self.engine.prepare(self.action, "export", assessment)
        return "REVIEW_REQUIRED" if self.handle["disposition"] == "REQUIRE_REVIEW" else "FAILED"

    def approve(self):
        self.engine.approve(self.handle, True)
        (self.home / "handle.json").write_text(json.dumps(self.handle), encoding="utf-8")
        return (
            "READY"
            if self.handle["disposition"] in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
            else "FAILED"
        )

    def execute(self):
        try:
            return self.engine.dispatch(self.handle)
        except ValueError as exc:
            if self.arm == "application" and str(exc) in {
                "Evidence, resources or policy changed",
                "No current authority",
            }:
                return "BLOCKED"
            # Only the runtime's documented refusal is translated, not arbitrary errors.
            if self.arm == "framework":
                from decision_firewall.core.runtime import FirewallError

                if isinstance(exc, FirewallError) and str(exc) in {
                    "Authorization expired or bindings changed",
                    "Authorization missing, consumed or revoked",
                }:
                    return "BLOCKED"
            raise

    def change_evidence(self):
        facts = self.service.facts()
        facts["version"] += 1
        facts["available_rows"] = 4900  # Material change, still eligible after a new review.
        self.service.facts_path.write_text(json.dumps(facts), encoding="utf-8")

    def recover_after_restart(self):
        # New interpreter, no live engine/observer objects carried into recovery.
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.control_conformance.recover",
                str(self.home.resolve()),
                self.arm,
                self.fault or "none",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=45,
        )
        return json.loads(result.stdout)["status"]

    def observe(self):
        return self.service.observe(self.action)


def application(home, scenario):
    return Bridge(home, scenario, "application")


def framework(home, scenario):
    return Bridge(home, scenario, "framework")
