"""Generic commands. The old top-level refund commands remain compatible."""

import base64
import importlib
import json
from pathlib import Path

import typer

from .core import Assessment, DecisionFirewall, DomainPack, Proposal, Review, verify_receipt

app = typer.Typer(no_args_is_help=True, help="Reusable decision governance SDK operations.")


def output(value):
    typer.echo(json.dumps(value, indent=2))


@app.callback()
def setup(
    ctx: typer.Context,
    home: Path = Path(".runtime-framework"),
    domain: str = "access",
    plugin: str | None = None,
):
    """PLUGIN is an explicitly trusted installed module:factory, called with home."""
    if plugin:
        module, separator, name = plugin.partition(":")
        if not separator:
            raise typer.BadParameter("Use installed.module:factory")
        pack = getattr(importlib.import_module(module), name)(home)
        if not isinstance(pack, DomainPack):
            raise typer.BadParameter("Factory must return a DomainPack")
    elif domain == "access":
        from .domains.access.pack import access_domain

        pack = access_domain(home)
    elif domain == "refunds":
        from .domains.refunds.pack import refund_domain

        pack = refund_domain(home)
    else:
        raise typer.BadParameter("Choose access, refunds, or an explicit --plugin")
    ctx.obj = DecisionFirewall(home, [pack])


@app.command()
def domains(ctx: typer.Context):
    """Show registered domain manifests and extension contracts."""
    output([domain.manifest() for domain in ctx.obj.domains.values()])


@app.command()
def submit(ctx: typer.Context, proposal: Path, assessment: Path):
    output(
        {
            "request_id": ctx.obj.submit(
                Proposal.model_validate_json(proposal.read_text(encoding="utf-8")),
                Assessment.model_validate_json(assessment.read_text(encoding="utf-8")),
            )
        }
    )


@app.command()
def prepare(
    ctx: typer.Context,
    proposal: Path,
    reference_checks: bool = False,
    structured_access: bool = False,
):
    """Prepare a request without calling a model or granting authority."""
    from .core.preparation import PreparationSpec

    value = Proposal.model_validate_json(proposal.read_text(encoding="utf-8"))
    spec = PreparationSpec()
    if structured_access and value.domain != "access":
        raise typer.BadParameter("Structured bypass is supported only for the access example")
    if value.domain == "access" and (reference_checks or structured_access):
        from .domains.access.pack import access_preparation

        spec = access_preparation(structured=structured_access)
    elif value.domain == "refunds" and reference_checks:
        from .domains.refunds.pack import refund_preparation

        spec = refund_preparation()
    output(ctx.obj.prepare(value, spec).model_dump(mode="json"))


@app.command("inspect-preparation")
def inspect_preparation(ctx: typer.Context, preparation_id: str):
    output(ctx.obj.inspect_preparation(preparation_id).model_dump(mode="json"))


@app.command("assess-prepared")
def assess_prepared(ctx: typer.Context, preparation_id: str, model_plugin: str | None = None):
    """Trusted module:factory returns a PreparedModel; omit for deterministic routing."""
    model = None
    if model_plugin:
        module, separator, name = model_plugin.partition(":")
        if not separator:
            raise typer.BadParameter("Use installed.module:factory")
        model = getattr(importlib.import_module(module), name)()
    output(ctx.obj.assess_prepared(preparation_id, model).model_dump(mode="json"))


@app.command()
def evaluate(ctx: typer.Context, request_id: str, save: Path | None = None):
    result = ctx.obj.evaluate(request_id)
    if save and result["authorization"]:
        save.write_text(json.dumps(result["authorization"], indent=2), encoding="utf-8")
    output(result)


@app.command()
def review(
    ctx: typer.Context,
    request_id: str,
    decision: str,
    reason: str,
    revision: int,
    evaluation_id: str | None = None,
):
    output(
        ctx.obj.review(
            request_id,
            Review.model_validate({"decision": decision, "reason": reason}),
            revision=revision,
            evaluation_id=evaluation_id,
        )
    )


@app.command()
def execute(ctx: typer.Context, authorization: Path):
    output(ctx.obj.execute(json.loads(authorization.read_text(encoding="utf-8"))))


@app.command()
def reconcile(ctx: typer.Context, authorization_id: str):
    output(ctx.obj.reconcile(authorization_id))


@app.command()
def inspect(ctx: typer.Context, request_id: str):
    output(ctx.obj.detail(request_id))


@app.command()
def replay(ctx: typer.Context, evaluation_id: str):
    output(ctx.obj.replay(evaluation_id))


@app.command()
def receipt(ctx: typer.Context, save: Path):
    fw = ctx.obj
    body = fw.receipt()
    assert verify_receipt(body, fw.store.public)
    save.write_text(json.dumps(body, indent=2), encoding="utf-8")
    save.with_suffix(".pub").write_text(
        base64.b64encode(fw.store.public).decode(), encoding="ascii"
    )
    output({"receipt": str(save), "verified": True})


@app.command()
def demo(ctx: typer.Context):
    """Execute one fully simulated request through the generic runtime."""
    from uuid import uuid4

    from .core import Signal

    fw = ctx.obj
    name = next(iter(fw.domains))
    if name == "access":
        proposal = Proposal(
            domain=name,
            action={"employee": "alice", "resource": "engineering-docs", "hours": 4},
            message="Read engineering documentation",
        )
        assessment = Assessment(
            provider="fixture",
            model="example",
            revision="1",
            signals={"intent": Signal(kind="choice", value="access")},
        )
    elif name == "refunds":
        from .adapters.models import RefundModelAdapter
        from .domains.refunds.contracts import Payment
        from .domains.refunds.providers import FixtureProvider
        from .domains.refunds.simulator import PaymentSimulator

        payment_id = "demo-" + uuid4().hex
        PaymentSimulator(fw.store.home).seed(
            Payment(
                payment_id=payment_id,
                customer_id="customer",
                amount_minor=99900,
                destination="original-card",
                duplicate_verified=True,
            )
        )
        proposal = Proposal(
            domain=name,
            message="Refund the duplicate charge",
            action={
                "payment_id": payment_id,
                "customer_id": "customer",
                "amount_minor": 99900,
                "destination": "original-card",
                "requested_reason": "duplicate",
                "message": "Refund the duplicate charge",
            },
        )
        assessment = RefundModelAdapter(FixtureProvider()).assess(proposal.message)
    else:
        raise typer.BadParameter("Use submit for your custom domain")
    rid = fw.submit(proposal, assessment)
    evaluated = fw.evaluate(rid)
    outcome = fw.execute(evaluated["authorization"]) if evaluated["authorization"] else None
    output(
        {
            "request_id": rid,
            "domain": name,
            "evaluation": evaluated["result"],
            "outcome": outcome,
            "replay": fw.replay(evaluated["evaluation_id"]),
            "receipt_verified": verify_receipt(fw.receipt(), fw.store.public),
        }
    )
