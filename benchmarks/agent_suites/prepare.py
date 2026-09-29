"""Download hash-verified pinned source/data without Git partial-clone assumptions."""

import concurrent.futures
import hashlib
import json
import urllib.request
from pathlib import Path

from .inspect_sources import SOURCES


def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, (repo, revision) in SOURCES.items():
        tree_path = output / f"{name}-tree.json"
        if not tree_path.exists():
            with urllib.request.urlopen(
                f"https://api.github.com/repos/{repo}/git/trees/{revision}?recursive=1", timeout=60
            ) as response:
                tree_path.write_bytes(response.read())
        tree = json.loads(tree_path.read_text())
        if tree.get("sha") != revision or tree.get("truncated"):
            raise ValueError("Invalid/incomplete upstream tree")
        selected = [
            x
            for x in tree["tree"]
            if x["type"] == "blob"
            and (
                x["path"].startswith(f"src/{name}/")
                or x["path"].startswith(("data/tau2/domains/retail/", "data/tau2/user_simulator/"))
                or x["path"] in {"pyproject.toml", "README.md", "LICENSE"}
            )
        ]
        root = (output / name).resolve()

        def fetch(item, root=root, repo=repo, revision=revision):
            destination = root / item["path"]
            if not destination.resolve().is_relative_to(root):
                raise ValueError("Invalid source path")
            data = destination.read_bytes() if destination.exists() else b""

            def blob_hash(content):
                return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()

            if blob_hash(data) != item["sha"]:
                with urllib.request.urlopen(
                    f"https://raw.githubusercontent.com/{repo}/{revision}/{item['path']}",
                    timeout=60,
                ) as response:
                    data = response.read()
                if blob_hash(data) != item["sha"]:
                    raise ValueError("Upstream blob mismatch")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            return item["path"], hashlib.sha256(data).hexdigest()

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            files = dict(pool.map(fetch, selected))
        (output / f"{name}-installed-source.json").write_text(
            json.dumps(
                {
                    "repository": repo,
                    "revision": revision,
                    "files": files,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(name, len(files), "verified source/data files", flush=True)


if __name__ == "__main__":
    prepare(Path(".runtime-agent-sources"))
