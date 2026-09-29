"""Model-free, explicit test execution and offline investigation commands."""

import base64
import importlib
import json
from pathlib import Path
from typing import Annotated

import typer

from .core.conformance import run_conformance
from .core.investigation import investigate as reconstruct


def conformance(factory: str, save: Path | None = None):
    """Run trusted module:factory(home, scenario) in fresh temporary directories.

    Only simulated factories should be supplied: importing a plugin runs trusted code.
    Exit 1 means failures; exit 2 means unsupported checks; exit 0 means all passed.
    """
    module, separator, name = factory.partition(":")
    if not separator:
        raise typer.BadParameter("Use trusted.module:factory")
    report = run_conformance(getattr(importlib.import_module(module), name))
    body = json.dumps(report, indent=2)
    if save:
        save.write_text(body, encoding="utf-8")
    typer.echo(body)
    if report["counts"]["FAIL"]:
        raise typer.Exit(1)
    if report["counts"]["UNSUPPORTED"]:
        raise typer.Exit(2)


def investigate(
    receipt: Path,
    public_key: Path,
    request_id: str,
    save: Path | None = None,
    action_field: Annotated[
        list[str] | None,
        typer.Option(help="Explicit action-value export allowlist; repeat per field"),
    ] = None,
):
    """Reconstruct a request from a receipt and separately trusted base64 public key."""
    try:
        report = reconstruct(
            json.loads(receipt.read_text(encoding="utf-8")),
            base64.b64decode(public_key.read_text(encoding="ascii").strip(), validate=True),
            request_id,
            action_fields=tuple(action_field or []),
        )
    except Exception as exc:
        typer.echo(json.dumps({"error": "Investigation failed", "error_type": type(exc).__name__}))
        raise typer.Exit(1) from exc
    body = json.dumps(report, indent=2)
    if save:
        save.write_text(body, encoding="utf-8")
    typer.echo(body)
    if report["gaps"]:
        raise typer.Exit(2)
