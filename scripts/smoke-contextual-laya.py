"""Optional local context smoke, not an accuracy benchmark. Requires the pinned model extra."""

import json
import platform
import sys
import tempfile
from pathlib import Path

from decision_firewall import Assessment, Proposal
from decision_firewall.adapters.laya import LAYA_REVISION, LayaModel
from decision_firewall.context import ContextualModel, LexicalHistoryRetriever
from decision_firewall.history import HistoricalDecision, HistoryStore


def main():
    model = LayaModel(
        {
            "intent": {
                "type": "choice",
                "instructions": "What does the current request ask for?",
                "criteria": {"access": "Temporary document access", "other": "Another request"},
            }
        }
    )
    try:
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(directory)
            records = [
                HistoricalDecision(
                    source="smoke",
                    source_id=str(i),
                    decision_at=i * 100,
                    available_at=i * 100 + 1,
                    proposal=Proposal(
                        domain="access",
                        message=message,
                        action={"employee": "alice", "resource": "docs", "hours": i},
                    ),
                    assessment=Assessment(provider="fixture", model="smoke", revision="1"),
                )
                for i, message in enumerate(
                    ("Read the docs temporarily", "Please read the docs for two hours"), 1
                )
            ]
            ids = store.import_records(records)["record_ids"]
            dataset = store.snapshot(
                "context-smoke", {"development": ids[:1], "evaluation": ids[1:]}
            )
            adapter = ContextualModel(
                model,
                LexicalHistoryRetriever(ids[:1]),
                max_input_units=256,
                measure=model.measure_input,
            )
            assessment = adapter.assess_case(dataset.cases[1], dataset)
            import torch

            result = {
                "purpose": "contextual inference smoke, not accuracy benchmark",
                "python": platform.python_version(),
                "platform": platform.platform(),
                "torch": torch.__version__,
                "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                "revision": LAYA_REVISION,
                "dataset_hash": dataset.hash,
                "assessment": assessment.model_dump(mode="json"),
            }
            assert assessment.metadata["historical_context"]["selected"]
            path = Path(sys.argv[1] if len(sys.argv) > 1 else ".runtime-context-smoke/result.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(
                json.dumps({k: v for k, v in assessment.metadata.items() if k != "raw"}, indent=2)
            )
    finally:
        model.release()


if __name__ == "__main__":
    main()
