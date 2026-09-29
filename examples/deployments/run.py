"""Run a model-free, simulated deployment with response loss and restart recovery."""

import argparse
import json
from pathlib import Path

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.core import Review, verify_receipt
from decision_firewall.domains.deployments.pack import DeploymentSimulator, deployment_domain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path(".runtime-deployment-demo"))
    args = parser.parse_args()
    if args.home.exists():
        parser.error("Choose a new --home directory to preserve earlier runs")
    ledger = DeploymentSimulator(args.home)
    artifact = "sha256:" + "a" * 64
    ledger.register(
        "artifact",
        artifact,
        {
            "service": "orders",
            "approved": True,
            "environments": ["staging", "production"],
        },
    )
    ledger.register("environment", "production", {"enabled": True})
    fw = DecisionFirewall(args.home, [deployment_domain(args.home, mode="response_loss")])
    rid = fw.submit(
        Proposal(
            domain="deployments",
            message="Deploy orders release",
            action={"service": "orders", "artifact": artifact, "environment": "production"},
        ),
        Assessment(provider="fixture", model="structured-deployment", revision="1"),
    )
    evaluation = fw.evaluate(rid)
    approved = fw.review(rid, Review(decision="approve", reason="Release reviewed"), revision=1)
    attempt = fw.execute(approved["authorization"])
    restarted = DecisionFirewall(args.home, [deployment_domain(args.home)])
    outcome = restarted.reconcile(approved["authorization"]["payload"]["id"])
    report = {
        "simulated": True,
        "request_id": rid,
        "initial_disposition": evaluation["result"]["disposition"],
        "dispatch_status": attempt["status"],
        "reconciled_status": outcome["status"],
        "request_status": restarted.detail(rid)["status"],
        "replay_matches": restarted.replay(approved["evaluation_id"])["matches"],
        "receipt_verified": verify_receipt(restarted.receipt(), restarted.store.public),
    }
    assert report["initial_disposition"] == "REQUIRE_REVIEW"
    assert report["dispatch_status"] == "UNKNOWN"
    assert report["reconciled_status"] == "SUCCEEDED"
    assert report["replay_matches"] and report["receipt_verified"]
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
