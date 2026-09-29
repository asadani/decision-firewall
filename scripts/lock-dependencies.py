"""Record installed, tested dependencies without embedding local paths or credentials."""

from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def closure(names, excluded=()):
    found = {}
    pending = list(names)
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found or name in excluded:
            continue
        dist = distribution(name)
        found[name] = dist.version
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                pending.append(req.name)
    return found


def write(name, values, note):
    (ROOT / name).write_text(
        "# " + note + "\n" + "\n".join(f"{k}=={v}" for k, v in sorted(values.items())) + "\n",
        encoding="utf-8",
    )


def main():
    core = closure(["pydantic", "typer", "cryptography", "rfc8785"])
    inspector = closure(
        [
            "fastapi",
            "jinja2",
            "uvicorn",
            "python-multipart",
            "itsdangerous",
            "psutil",
        ]
    )
    dev = {**closure(["pytest", "httpx", "ruff", "mypy", "build"]), **inspector}
    telemetry = closure(["opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http"])
    write(
        "requirements-telemetry.lock",
        {k: v for k, v in telemetry.items() if k not in core},
        "Optional OTLP/HTTP export; install alongside core",
    )
    model = closure(["laya"], excluded=("torch",))
    write("requirements-core.lock", core, "Python 3.12 tested core; no model dependency")
    write(
        "requirements-inspector.lock",
        {k: v for k, v in inspector.items() if k not in core},
        "Optional refund inspector and evaluation tools; install alongside core",
    )
    write(
        "requirements-dev.lock",
        {k: v for k, v in dev.items() if k not in core},
        "Install alongside requirements-core.lock",
    )
    write(
        "requirements-model.lock",
        {k: v for k, v in model.items() if k not in core},
        "Install core first, then torch==2.6.0 from the CPU or cu124 wheel index, then this lock",
    )


if __name__ == "__main__":
    main()
