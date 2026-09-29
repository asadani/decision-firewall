"""Run from the checkout: python examples/workbench/run.py .runtime-comparisons"""

import json
import sys
from pathlib import Path

from decision_firewall import Assessment, Proposal
from decision_firewall.core import Decision, Disposition, Evidence, Signal
from decision_firewall.domains.access.pack import AccessPolicy, access_domain
from decision_firewall.domains.refunds.contracts import Payment, Policy
from decision_firewall.domains.refunds.pack import refund_domain
from decision_firewall.experiments import (
    EvaluationPolicy,
    ExperimentRunner,
    ExperimentSpec,
    ExperimentVariant,
)
from decision_firewall.history import ExpectedLabels, HistoricalDecision, HistoryStore


def run(root):
    for domain in ("access", "refunds"):
        home = root / domain
        store = HistoryStore(home)
        if domain == "access":
            packs = [
                access_domain(home / "isolated", policy=AccessPolicy(automatic_max_hours=n))
                for n in (8, 2)
            ]
            proposal = Proposal(
                domain=domain,
                message="Read engineering documentation",
                action={"employee": "alice", "resource": "engineering-docs", "hours": 4},
            )
            evidence = Evidence(
                facts={
                    "employee": {"active": True, "resources": ["engineering-docs"], "version": 1}
                },
                versions={"directory": "1"},
            )
            assessment = Assessment(provider="fixture", model="example", revision="1")
        else:
            packs = [
                refund_domain(home / "isolated", policy=Policy(auto_amount_minor=n))
                for n in (100000, 10000)
            ]
            proposal = Proposal(
                domain=domain,
                message="Refund my duplicate charge",
                action={
                    "payment_id": "pay-1",
                    "customer_id": "customer-1",
                    "message": "Refund my duplicate charge",
                    "amount_minor": 50000,
                    "destination": "original-card",
                    "requested_reason": "duplicate",
                },
            )
            evidence = Evidence(
                facts={
                    "payment": Payment(
                        payment_id="pay-1",
                        customer_id="customer-1",
                        amount_minor=50000,
                        destination="original-card",
                        duplicate_verified=True,
                    ).model_dump()
                },
                versions={"payment": "1"},
            )
            assessment = Assessment(
                provider="fixture",
                model="example",
                revision="1",
                signals={"request_type": Signal(kind="choice", value="duplicate")},
            )
        history = HistoricalDecision(
            source="synthetic-example",
            source_id=domain,
            proposal=proposal,
            decision_at=1000,
            available_at=1001,
            evidence=evidence,
            evidence_available_at=999,
            assessment=assessment,
            historical_decision=Decision(disposition=Disposition.ALLOW),
            usage={},
        )
        file = home / "history.jsonl"
        file.write_text(history.model_dump_json() + "\n", encoding="utf-8")
        imported = store.import_file(file)
        rid = imported["record_ids"][0]
        store.annotate(
            rid,
            ExpectedLabels(disposition=Disposition.ALLOW_WITH_CONSTRAINTS),
            reviewer="example-curator",
            reason="Verified the synthetic facts",
            available_at=2000,
        )
        snapshot = store.snapshot(domain + "-development", {"development": [rid]})
        result = ExperimentRunner(
            [
                ExperimentVariant(name, EvaluationPolicy.from_domain(pack))
                for name, pack in zip(("baseline", "more-review"), packs, strict=True)
            ]
        ).run(snapshot, ExperimentSpec(name=domain + "-comparison"), home / "experiment")
        assert result.passed
        assert result.observations[0]["actual"] == "ALLOW_WITH_CONSTRAINTS"
        assert result.observations[1]["actual"] == "REQUIRE_REVIEW"
        print(json.dumps({"domain": domain, "summaries": result.summaries}, indent=2))


if __name__ == "__main__":
    run(Path(sys.argv[1] if len(sys.argv) > 1 else ".runtime-comparisons"))
