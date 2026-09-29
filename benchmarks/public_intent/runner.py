"""Pinned public intent baseline, stdlib only; raw texts stay in the ignored cache."""

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import random
import re
import statistics
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent


def sha(value):
    return hashlib.sha256(value).hexdigest()


def tokens(text):
    return re.findall(r"\w+", text.casefold())


class LexicalModel:
    def __init__(self, rows):
        self.documents = Counter(row["category"] for row in rows)
        self.words = defaultdict(Counter)
        for row in rows:
            self.words[row["category"]].update(tokens(row["text"]))
        self.vocabulary = set().union(*(set(counts) for counts in self.words.values()))
        self.denominators = {
            label: sum(words.values()) + len(self.vocabulary) for label, words in self.words.items()
        }
        self.total = len(rows)

    def predict(self, text):
        counts = Counter(t for t in tokens(text) if t in self.vocabulary)
        scores = {
            label: math.log(count / self.total)
            + sum(
                n * math.log((self.words[label][word] + 1) / self.denominators[label])
                for word, n in counts.items()
            )
            for label, count in sorted(self.documents.items())
        }
        return max(scores, key=scores.get)


def fetch(cache, protocol):
    cache.mkdir(parents=True, exist_ok=True)
    root = f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{protocol['revision']}/"
    contents = {}
    for name, checksum in protocol["files"].items():
        path = cache / Path(name).name
        data = (
            path.read_bytes()
            if path.exists()
            else urllib.request.urlopen(root + name, timeout=30).read()
        )
        if sha(data) != checksum:
            raise ValueError(f"Pinned dataset hash mismatch: {name}")
        if not path.exists():
            path.write_bytes(data)
        contents[name] = data
    return contents


def run(output, cache, limit=None):
    protocol = json.loads((HERE / "protocol.json").read_text())
    if limit is not None and not 1 <= limit <= protocol["test_rows"]:
        raise ValueError("BANKING77 has only 3080 official test rows; use at most 3080")
    data = fetch(cache, protocol)
    train = list(csv.DictReader(io.StringIO(data["banking_data/train.csv"].decode("utf-8"))))
    test = list(csv.DictReader(io.StringIO(data["banking_data/test.csv"].decode("utf-8"))))
    if len(train) != protocol["train_rows"] or len(test) != protocol["test_rows"]:
        raise ValueError("Unexpected dataset split sizes")
    output.mkdir(parents=True, exist_ok=False)
    indices = list(range(len(test)))
    random.Random(protocol["seed"]).shuffle(indices)
    indices = indices[:limit]
    manifest = {
        "started": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "protocol": protocol,
        "protocol_hash": sha((HERE / "protocol.json").read_bytes()),
        "runner_hash": sha(Path(__file__).read_bytes()),
        "test_indices": indices,
        "model": "multinomial-naive-bayes-v1",
        "device": "cpu",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    start = time.perf_counter()
    model = LexicalModel(train)
    training_ms = (time.perf_counter() - start) * 1000
    train_content = {" ".join(tokens(row["text"])) for row in train}
    rows = []
    for index in indices:
        case = test[index]
        start = time.perf_counter()
        predicted = model.predict(case["text"])
        duration = (time.perf_counter() - start) * 1000
        rows.append(
            {
                "test_index": index,
                "input_hash": sha(case["text"].encode()),
                "expected": case["category"],
                "predicted": predicted,
                "correct": case["category"] == predicted,
                "duration_ms": duration,
                "train_overlap": " ".join(tokens(case["text"])) in train_content,
            }
        )
    labels = sorted(model.documents)
    f1 = []
    for label in labels:
        tp = sum(r["expected"] == label and r["predicted"] == label for r in rows)
        fp = sum(r["expected"] != label and r["predicted"] == label for r in rows)
        fn = sum(r["expected"] == label and r["predicted"] != label for r in rows)
        f1.append(2 * tp / max(1, 2 * tp + fp + fn))
    durations = sorted(r["duration_ms"] for r in rows)
    clean = [r for r in rows if not r["train_overlap"]]
    summary = {
        "dataset": "BANKING77",
        "official_test": limit is None,
        "n": len(rows),
        "train_n": len(train),
        "labels": len(labels),
        "accuracy": sum(r["correct"] for r in rows) / len(rows),
        "macro_f1": statistics.mean(f1),
        "macro_f1_denominator": len(labels),
        "labels_absent_in_subset": len(set(labels) - {r["expected"] for r in rows}),
        "invalid_outputs": 0,
        "missing_labels": 0,
        "train_overlap": len(rows) - len(clean),
        "nonoverlap_n": len(clean),
        "nonoverlap_accuracy": sum(r["correct"] for r in clean) / len(clean) if clean else None,
        "training_ms": training_ms,
        "p50_ms": statistics.median(durations),
        "p95_ms": durations[math.ceil(0.95 * len(durations)) - 1],
        "execution_safety": "not measured; this dataset has no execution ground truth",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "observations.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with (output / "observations.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path(".runtime-public-data/banking77"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run(args.output, args.cache, args.limit)
