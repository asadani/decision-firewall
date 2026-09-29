"""Sequential resumable pilot. No automatic episode retries or provider changes."""

import argparse
import importlib.metadata
import json
import os
import platform
import random
import time
from dataclasses import asdict
from pathlib import Path

from decision_firewall.core.audit import digest

from .bridge import Bridge, configured_client

ROOT = Path(__file__).resolve().parents[2]


def schedule(protocol):
    rng = random.Random(protocol["seed"])
    cases = [("tau2", t, None) for t in protocol["tau2"]["task_ids"]]
    cases += [
        ("agentdojo", t, i)
        for t in protocol["agentdojo"]["task_ids"]
        for i in protocol["agentdojo"]["injection_ids"]
    ]
    for suite, task, injection in cases:
        arms = list(protocol["arms"])
        rng.shuffle(arms)
        for arm in arms:
            yield suite, task, injection, arm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--budget-db", type=Path, default=Path(".runtime-agent-sources/openrouter-budget.db")
    )
    parser.add_argument("--suite", choices=["tau2", "agentdojo", "all"], default="all")
    args = parser.parse_args()
    os.environ["TAU2_DATA_DIR"] = str((ROOT / ".runtime-agent-sources/tau2/data").resolve())
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    # Avoid upstream optional tracing integrations or accidental ambient clients.
    os.environ["USE_LANGFUSE"] = "False"
    protocol_path = Path(__file__).with_name("protocol.json")
    protocol = json.loads(protocol_path.read_text())
    client = configured_client(args.env_file, args.budget_db, protocol["max_tokens"])
    args.output.mkdir(parents=True, exist_ok=True)
    bridge = Bridge(client, args.output / "private-cache")
    manifest = {
        "protocol": protocol,
        "protocol_hash": digest(protocol),
        "settings": asdict(client.settings),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_hashes": {
            str(p.relative_to(ROOT)): digest(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "benchmarks/agent_suites").glob("*.py"))
        },
        "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        "upstream_sources": {
            name: json.loads(
                (ROOT / f".runtime-agent-sources/{name}-installed-source.json").read_text()
            )
            for name in ("tau2", "agentdojo")
        },
        "framework_source_hashes": {
            str(p.relative_to(ROOT)): digest(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "src/decision_firewall").rglob("*.py"))
        },
    }
    manifest_path = args.output / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise RuntimeError("Manifest changed: use a new output directory, retaining this run")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    from loguru import logger

    logger.remove()
    from . import dojo, tau

    for suite, task, injection, arm in schedule(protocol):
        if args.suite not in {suite, "all"}:
            continue
        episode_id = f"{suite}-{task}-{injection or 'clean'}-{arm}"
        home = args.output / "private-episodes" / episode_id
        result_path = args.output / f"{episode_id}.json"
        if result_path.exists():
            continue  # retain errors too; no selective reruns
        if home.exists():
            raise RuntimeError(f"Interrupted episode {episode_id}; inspect before resuming")
        home.mkdir(parents=True)
        started, before, before_events = time.perf_counter(), len(bridge.calls), len(client.events)
        row = {"suite": suite, "task": task, "injection": injection, "arm": arm}
        print(f"Starting {episode_id}", flush=True)
        try:
            if suite == "tau2":
                result = tau.run(task, arm, home, bridge, protocol[suite]["max_steps"])
            else:
                result = dojo.run(task, injection, arm, home, bridge, protocol[suite]["max_steps"])
            row.update(result, status="completed")
        except Exception as exc:
            row.update(status="error", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            row["elapsed_seconds"] = time.perf_counter() - started
            row["inference"] = bridge.calls[before:]
            row["attempts"] = client.events[before_events:]
            result_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        print(
            f"Finished {episode_id}: success={row['task_success']} attack={row.get('attack_success')} calls={len(row['inference'])}",
            flush=True,
        )


if __name__ == "__main__":
    main()
