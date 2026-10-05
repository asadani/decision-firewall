"""python -m control_conformance trusted.module:factory --output report.json"""

import argparse
import importlib
import json
from pathlib import Path

from .runner import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("factory", help="Trusted Python test factory; executes local code")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    parts = args.factory.split(":")
    if (
        len(parts) != 2
        or not all(p.isidentifier() for p in parts[0].split("."))
        or not parts[1].isidentifier()
    ):
        parser.error("factory must be a Python module:function reference")
    module, name = parts
    try:
        factory = getattr(importlib.import_module(module), name)
        if not callable(factory):
            raise TypeError("Factory is not callable")
    except (ImportError, AttributeError, TypeError) as exc:
        parser.exit(1, f"Cannot load test factory ({type(exc).__name__})\n")
    report = run(factory)
    content = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content)
    return (
        1
        if report["counts"]["FAIL"] or report["counts"]["ERROR"]
        else (2 if report["counts"]["UNSUPPORTED"] else 0)
    )


if __name__ == "__main__":
    raise SystemExit(main())
