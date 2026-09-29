"""Paired pre-inference routing experiment using the real SDK and no model downloads."""

import argparse
import hashlib
import json
import platform
import random
import statistics
import time
from pathlib import Path

from decision_firewall import Assessment, DecisionFirewall, Proposal, RenderedPreparedModel
from decision_firewall.domains.access.pack import access_domain, access_preparation

HERE = Path(__file__).parent


class Model:
    def __init__(self):
        self.calls = 0

    def assess(self, message):
        self.calls += 1
        return Assessment(provider="fixture", model="counting", revision="1")


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((HERE / "protocol.json").read_text())
    manifest = {
        "protocol": protocol,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_hashes": {
            str(p.relative_to(HERE.parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in (HERE, HERE.parents[1] / "src")
            for p in folder.rglob("*.py")
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    rng = random.Random(protocol["seed"])
    rows = []
    for i in range(protocol["cases"]):
        family = protocol["families"][i % 4]
        arms = list(protocol["arms"])
        rng.shuffle(arms)
        for arm in arms:
            directory = (
                {}
                if family == "missing_evidence"
                else {
                    "alice": {
                        "active": family != "mandatory_block",
                        "resources": ["engineering-docs"],
                        "version": 1,
                    }
                }
            )
            home = output / "runtime" / str(i) / arm
            fw = DecisionFirewall(home, [access_domain(home, directory=directory)])
            p = Proposal(
                domain="access",
                action={"employee": "alice", "resource": "engineering-docs", "hours": 4},
                message=f"Please grant engineering docs access, case {i}",
            )
            model = Model()
            start = time.perf_counter()
            route, result = "not_prepared", None
            if arm == "with_preparation":
                prepared = fw.prepare(p, access_preparation(structured=family == "structured"))
                route = prepared.route
                if route in {"READY_FOR_MODEL", "READY_FOR_DETERMINISTIC_EVALUATION"}:
                    a = fw.assess_prepared(prepared.id, RenderedPreparedModel(model))
                    result = fw.evaluate(fw.submit(p, a))["result"]["disposition"]
                else:
                    result = {
                        "REQUIRE_INPUT_OR_EVIDENCE": "REQUIRE_EVIDENCE",
                        "BLOCKED_BY_MANDATORY_CHECK": "DENY",
                    }.get(route, "ERROR")
            else:
                result = fw.evaluate(fw.submit(p, fw.assess(model, p.message)))["result"][
                    "disposition"
                ]
            expected = (
                "REQUIRE_EVIDENCE"
                if family == "missing_evidence"
                else "DENY"
                if family == "mandatory_block"
                else "ALLOW_WITH_CONSTRAINTS"
            )
            rows.append(
                {
                    "index": i,
                    "family": family,
                    "arm": arm,
                    "route": route,
                    "result": result,
                    "expected": expected,
                    "model_calls": model.calls,
                    "operation_ms": (time.perf_counter() - start) * 1000,
                    "matches": result == expected,
                }
            )
    summary = {
        arm: {
            "n": len(samples),
            "matches": sum(r["matches"] for r in samples),
            "model_calls": sum(r["model_calls"] for r in samples),
            "p50_ms": statistics.median(r["operation_ms"] for r in samples),
        }
        for arm in protocol["arms"]
        if (samples := [r for r in rows if r["arm"] == arm])
    }
    for name, value in (("observations.json", rows), ("summary.json", summary)):
        (output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all(r["matches"] for r in rows) else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
