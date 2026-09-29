"""Full-source paired classification measurements. No optional model or agent dependencies."""

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import random
import statistics
import time
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.public_intent.runner import LexicalModel, fetch, tokens
from decision_firewall import Assessment, DecisionFirewall, Proposal, RenderedPreparedModel, Signal
from decision_firewall.core import Decision, DomainPack, Evidence, Record

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
ARMS = ("direct", "framework_assess", "framework_prepared")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return " ".join(tokens(text))


def fold(text, seed):
    return int(sha(f"{seed}\n{normalized(text)}".encode()), 16) % 5


class UnusedExecutor:
    name, version = "classification-only-no-effects", "1"
    supported_constraints = frozenset()

    def execute(self, *args):
        raise AssertionError("Classification benchmark must not execute")

    def reconcile(self, *args):
        raise AssertionError("Classification benchmark must not reconcile")


def domain():
    return DomainPack(
        name="intent",
        version="1",
        policy_version="no-authorization-v1",
        action_schema=Record,
        resolve=lambda p: Evidence(),
        evaluate=lambda c: Decision(disposition="REQUIRE_REVIEW", reasons=["classification_only"]),
        executor=UnusedExecutor(),
    )


class Model:
    def __init__(self, rows):
        self.classifier = LexicalModel(rows)

    def assess(self, message):
        return Assessment(
            provider="lexical",
            model="multinomial-naive-bayes",
            revision="1",
            signals={"intent": Signal(kind="choice", value=self.classifier.predict(message))},
        )


def load_data(cache, protocol):
    original = json.loads((ROOT / "benchmarks/public_intent/protocol.json").read_text())
    files = fetch(cache / "banking77", original)
    banking = {
        split: list(csv.DictReader(io.StringIO(files[f"banking_data/{split}.csv"].decode())))
        for split in ("train", "test")
    }
    config = protocol["bitext"]
    path = cache / "bitext" / config["filename"]
    if not path.exists():
        url = f"https://huggingface.co/datasets/{config['dataset']}/resolve/{config['revision']}/{config['filename']}"
        data = urllib.request.urlopen(url, timeout=60).read()
        if sha(data) != config["sha256"]:
            raise ValueError("Bitext hash mismatch")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = path.read_bytes()
    if sha(data) != config["sha256"]:
        raise ValueError("Bitext cache hash mismatch")
    bitext = [
        {"text": r["instruction"], "category": r["intent"]}
        for r in csv.DictReader(io.StringIO(data.decode("utf-8")))
    ]
    if (len(banking["train"]), len(banking["test"]), len(bitext)) != (10003, 3080, 26872):
        raise ValueError("Unexpected source row counts")
    return banking, bitext


def percentile(values, q):
    return sorted(values)[math.ceil(q * len(values)) - 1]


def summarize(rows, labels):
    result = {}
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        f1 = []
        for label in labels:
            tp = sum(r["expected"] == label and r["predicted"] == label for r in selected)
            fp = sum(r["expected"] != label and r["predicted"] == label for r in selected)
            fn = sum(r["expected"] == label and r["predicted"] != label for r in selected)
            f1.append(2 * tp / max(1, 2 * tp + fp + fn))
        durations = [r["duration_ms"] for r in selected]
        result[arm] = {
            "n": len(selected),
            "correct": sum(r["predicted"] == r["expected"] for r in selected),
            "accuracy": sum(r["predicted"] == r["expected"] for r in selected) / len(selected),
            "macro_f1": statistics.mean(f1),
            "macro_f1_denominator": len(labels),
            "invalid_outputs": sum(r["predicted"] not in labels for r in selected),
            "missing_labels": sum(not r["expected"] for r in selected),
            "p50_ms": statistics.median(durations),
            "p95_ms": percentile(durations, 0.95),
            "sum_operation_seconds": sum(durations) / 1000,
            "exact_normalized_training_overlap": sum(r["training_overlap"] for r in selected),
            "p50_first_1000_ms": statistics.median(r["duration_ms"] for r in selected[:1000]),
            "p50_last_1000_ms": statistics.median(r["duration_ms"] for r in selected[-1000:]),
        }
    direct = {r["index"]: r for r in rows if r["arm"] == "direct"}
    for arm in ARMS[1:]:
        selected = [r for r in rows if r["arm"] == arm]
        deltas = [r["duration_ms"] - direct[r["index"]]["duration_ms"] for r in selected]
        result[arm]["prediction_disagreements_with_direct"] = sum(
            r["predicted"] != direct[r["index"]]["predicted"] for r in selected
        )
        result[arm]["paired_delta_p50_ms"] = statistics.median(deltas)
        result[arm]["paired_delta_p95_ms"] = percentile(deltas, 0.95)
    return result


def measure(output, name, train, test, oof, seed):
    folder = output / name
    folder.mkdir()
    start = time.perf_counter()
    fw = DecisionFirewall(folder / "runtime", [domain()])
    setup_ms = (time.perf_counter() - start) * 1000
    training_ms = 0.0
    rng = random.Random(seed)
    rows = []
    labels = sorted({r["category"] for r in train})
    splits = [fold(r["text"], seed) for r in train] if oof else []
    processed = 0
    with (folder / "observations.jsonl").open("x", encoding="utf-8") as log:
        for heldout in range(5) if oof else [None]:
            fitting = [r for i, r in enumerate(train) if splits[i] != heldout] if oof else train
            indices = (
                [i for i in range(len(test)) if splits[i] == heldout]
                if oof
                else list(range(len(test)))
            )
            rng.shuffle(indices)
            start = time.perf_counter()
            model = Model(fitting)
            training_ms += (time.perf_counter() - start) * 1000
            training_text = {normalized(r["text"]) for r in fitting}
            for index in indices:
                case = test[index]
                proposal = Proposal(domain="intent", action={}, message=case["text"])
                arms = list(ARMS)
                rng.shuffle(arms)
                for arm in arms:
                    prediction, error = None, None
                    start = time.perf_counter()
                    try:
                        if arm == "direct":
                            assessment = model.assess(case["text"])
                        elif arm == "framework_assess":
                            assessment = fw.assess(model, case["text"])
                        else:
                            prepared = fw.prepare(proposal)
                            assessment = fw.assess_prepared(
                                prepared.id, RenderedPreparedModel(model)
                            )
                        prediction = assessment.signals["intent"].value
                    except Exception as exc:  # noqa: BLE001 -- retain benchmark failures in denominator
                        error = type(exc).__name__
                    duration = (time.perf_counter() - start) * 1000
                    row = {
                        "index": index,
                        "fold": heldout,
                        "arm": arm,
                        "input_hash": sha(case["text"].encode()),
                        "expected": case["category"],
                        "predicted": prediction,
                        "error": error,
                        "duration_ms": duration,
                        "training_overlap": normalized(case["text"]) in training_text,
                    }
                    rows.append(row)
                    log.write(json.dumps(row) + "\n")
                processed += 1
                if processed % 500 == 0:
                    log.flush()
                    print(f"{name}: {processed}/{len(test)} rows, all three arms", flush=True)
    summary = {
        "dataset": name,
        "source_rows_scored": processed,
        "oof": oof,
        "labels": len(labels),
        "fold_counts": dict(Counter(splits)),
        "runtime_setup_ms": setup_ms,
        "training_ms": training_ms,
        "arms": summarize(rows, labels),
    }
    with fw.store.transaction() as db:
        summary["audit_events"] = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        summary["permits"] = db.execute("SELECT COUNT(*) FROM permits").fetchone()[0]
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (folder / "observations.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def run(output, cache):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((HERE / "protocol.json").read_text())
    banking, bitext = load_data(cache, protocol)
    manifest = {
        "started": datetime.now(UTC).isoformat(),
        "protocol": protocol,
        "protocol_hash": sha((HERE / "protocol.json").read_bytes()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "code_hashes": {
            str(p.relative_to(ROOT)): sha(p.read_bytes())
            for folder in (HERE, ROOT / "src", ROOT / "benchmarks/public_intent")
            for p in folder.rglob("*.py")
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    results = [
        measure(
            output,
            "banking77-official-test",
            banking["train"],
            banking["test"],
            False,
            protocol["seed"],
        ),
        measure(
            output,
            "banking77-training-oof",
            banking["train"],
            banking["train"],
            True,
            protocol["seed"],
        ),
        measure(output, "bitext-all-oof", bitext, bitext, True, protocol["seed"]),
    ]
    (output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path(".runtime-public-data"))
    args = parser.parse_args()
    run(args.output, args.cache)
