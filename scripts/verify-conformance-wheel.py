"""Verify the independent distribution and application pilot in an empty environment."""

import os
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    wheels = sorted((ROOT / "conformance/dist").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Build the single conformance wheel first")
    with tempfile.TemporaryDirectory(prefix="conformance-wheel-") as directory:
        home = Path(directory)
        venv.EnvBuilder(with_pip=True).create(home)
        python = home / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheels[0])],
            check=True,
        )
        code = """
import importlib.util
assert importlib.util.find_spec('decision_firewall') is None
assert importlib.util.find_spec('pydantic') is None
from control_conformance import run
from benchmarks.control_conformance.adapters import application
report = run(application)
assert report['passed'], report
print('Standalone wheel: 3/3, including fresh-process recovery; no framework installed.')
"""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        subprocess.run([str(python), "-c", code], cwd=ROOT, env=env, check=True, timeout=90)


if __name__ == "__main__":
    main()
