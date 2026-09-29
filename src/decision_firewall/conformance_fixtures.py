"""Reference simulated fixtures; business assumptions stay outside core checks."""

from contextlib import closing
from pathlib import Path

from .core.audit import connect
from .core.conformance import ConformanceFixture
from .core.contracts import Assessment, Proposal
from .domains.access.pack import access_domain
from .domains.deployments.pack import DeploymentSimulator, deployment_domain


def _mode(scenario):
    return {
        "failure": "fail",
        "response_loss": "response_loss",
        "delayed": "delayed",
        "resource_contention": "delayed",
    }.get(scenario, "success")


def _count(path, table):
    with closing(connect(path)) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table} WHERE status='SUCCEEDED'").fetchone()[0]


def access(home: Path, scenario: str) -> ConformanceFixture:
    directory: dict = {"alice": {"active": True, "resources": ["docs"], "version": 1}}
    pack = access_domain(home, directory=directory, mode=_mode(scenario))

    def deny():
        directory["alice"]["active"] = False
        directory["alice"]["version"] += 1

    return ConformanceFixture(
        domain=pack,
        proposal=Proposal(
            domain="access",
            message="Test access",
            action={
                "employee": "alice",
                "resource": "docs",
                "hours": 24 if scenario in {"review", "review_cannot_override"} else 4,
            },
        ),
        assessment=Assessment(provider="fixture", model="conformance", revision="1"),
        effects=lambda: _count(Path(home) / "access-effects.db", "effects"),
        restart=lambda: access_domain(home, directory=directory),
        deny=deny,
        stale=deny,
        missing=directory.clear,
        settle=pack.executor.settle,
    )


def deployments(home: Path, scenario: str) -> ConformanceFixture:
    ledger = DeploymentSimulator(home)
    artifact = "sha256:" + "a" * 64
    environment = "production" if scenario in {"review", "review_cannot_override"} else "staging"
    ledger.register(
        "artifact",
        artifact,
        {
            "service": "orders",
            "approved": True,
            "environments": ["production", "staging"],
        },
    )
    ledger.register("environment", environment, {"enabled": True})

    def deny():
        ledger.register("environment", environment, {"enabled": False})

    def missing():
        with closing(connect(ledger.path)) as db, db:
            db.execute("DELETE FROM registry WHERE kind='artifact'")

    return ConformanceFixture(
        domain=deployment_domain(home, mode=_mode(scenario)),
        proposal=Proposal(
            domain="deployments",
            message="Test deployment",
            action={
                "service": "orders",
                "artifact": artifact,
                "environment": environment,
            },
        ),
        assessment=Assessment(provider="fixture", model="conformance", revision="1"),
        effects=lambda: _count(ledger.path, "deployments"),
        restart=lambda: deployment_domain(home),
        deny=deny,
        stale=deny,
        missing=missing,
        settle=ledger.settle,
        resource_contention=True,
    )
