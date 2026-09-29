"""Read pinned upstream metadata without installing or executing upstream code."""

import hashlib
import json
import urllib.request
from pathlib import Path

SOURCES = {
    "tau2": ("sierra-research/tau2-bench", "b7ea9074c1cba482b30687fecdb5c8425fd6f619"),
    "agentdojo": ("ethz-spylab/agentdojo", "089ed468cf3ed0322acc66b0211f26d9d90dbf60"),
}


def inspect(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, (repo, revision) in SOURCES.items():
        url = f"https://api.github.com/repos/{repo}/git/trees/{revision}?recursive=1"
        tree = json.load(urllib.request.urlopen(url, timeout=30))
        (output / f"{name}-tree.json").write_text(json.dumps(tree), encoding="utf-8")
        selected = [
            x
            for x in tree["tree"]
            if x["type"] == "blob"
            and (
                x["path"] in {"pyproject.toml", "README.md", "LICENSE"}
                or any(
                    part in x["path"]
                    for part in (
                        "tasks.json",
                        "split_tasks",
                        "agent_developer",
                        "llm_utils.py",
                        "cli.py",
                        "openai_llm.py",
                        "scripts/benchmark.py",
                        "task_suite/load_suites.py",
                        "docs/agents",
                        "retail/policy",
                    )
                )
            )
        ]
        print(
            name,
            json.dumps([{"path": x["path"], "size": x.get("size")} for x in selected], indent=2),
        )
        manifest = {"repository": repo, "revision": revision, "files": {}}
        for item in selected:
            if item.get("size", 0) > 5000000:
                continue
            path = (output / name / item["path"]).resolve()
            if not path.is_relative_to(output.resolve() / name):
                raise ValueError("Unexpected source path")
            data = path.read_bytes() if path.exists() else None
            if (
                data is not None
                and hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != item["sha"]
            ):
                data = None
            if data is None:
                data = urllib.request.urlopen(
                    f"https://raw.githubusercontent.com/{repo}/{revision}/{item['path']}",
                    timeout=30,
                ).read()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            manifest["files"][item["path"]] = hashlib.sha256(data).hexdigest()
        (output / f"{name}-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    inspect(Path(".runtime-agent-sources"))
