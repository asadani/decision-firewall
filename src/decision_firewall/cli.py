import base64
import json
import platform
from pathlib import Path

import typer

from .contracts import Assessment, OutcomeEvent, Payment, Proposal, ReviewDecision
from .engine import Firewall
from .framework_cli import app as framework_app
from .providers import BaselineProvider, FixtureProvider, LayaProvider
from .scenarios import scenarios
from .storage import verify_receipt

app = typer.Typer(
    no_args_is_help=True,
    help="Decision governance framework. Use 'framework' for any domain; other commands are the v0.1 refund demo.",
)
app.add_typer(framework_app, name="framework")
from .workbench_cli import datasets_app, experiments_app, history_app, policy_app

app.add_typer(history_app, name="history")
app.add_typer(datasets_app, name="datasets")
app.add_typer(experiments_app, name="experiments")
app.add_typer(policy_app, name="policy")

from .tooling_cli import conformance, investigate

app.command("conformance")(conformance)
app.command("investigate")(investigate)


@app.command("init")
def initialize(directory: Path):
    """Create an editable custom-domain starter in an empty directory."""
    from .scaffolding import scaffold

    scaffold(directory)
    output(
        {"created": str(directory.resolve()), "next": "Read README.md in the generated directory"}
    )


def output(value):
    typer.echo(json.dumps(value, indent=2, ensure_ascii=True))


@app.command()
def doctor():
    import shutil

    try:
        import psutil

        ram_bytes = psutil.virtual_memory().total
    except ImportError:
        ram_bytes = None

    info = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ram_bytes": ram_bytes,
        "nvidia_smi": shutil.which("nvidia-smi"),
    }
    try:
        import torch

        info.update(
            torch=torch.__version__,
            cuda=torch.cuda.is_available(),
            gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        )
    except ImportError:
        info["model_runtime"] = "Not installed; fixture mode available"
    output(info)


@app.command()
def assess(
    message: str, provider: str = "baseline", device: str = "auto", save: Path | None = None
):
    if provider not in {"baseline", "laya", "fixture"}:
        raise typer.BadParameter("Unknown provider")
    model = (
        LayaProvider(device=device)
        if provider == "laya"
        else BaselineProvider()
        if provider == "baseline"
        else FixtureProvider()
    )
    result = model.assess(message).model_dump()
    if save:
        save.write_text(json.dumps(result, indent=2), encoding="utf-8")
    output(result)


@app.command()
def demo(home: Path = Path(".runtime")):
    fw = Firewall(home)
    if fw.list_requests()["count"]:
        output({"message": "Existing demo preserved", "home": str(home)})
        return
    results = []
    for case in scenarios(variations=0)[::2]:
        if case["payment"]:
            fw.payments.seed(Payment.model_validate(case["payment"]))
        p = Proposal.model_validate(case["proposal"])
        rid = fw.submit(
            p, FixtureProvider(case["label"], case["refund_requested"]).assess(p.message)
        )
        result = fw.evaluate(rid)
        if result["authorization"]:
            fw.execute(
                result["authorization"],
                mode="response_loss" if case["family"] == "duplicate_valid" else "success",
            )
        results.append({"id": rid, "family": case["family"], "status": fw.detail(rid)["status"]})
    output(results)


@app.command()
def seed(payment: Path, home: Path = Path(".runtime")):
    Firewall(home).payments.seed(Payment.model_validate_json(payment.read_text(encoding="utf-8")))
    output({"seeded": True})


@app.command()
def submit(proposal: Path, assessment: Path, home: Path = Path(".runtime")):
    rid = Firewall(home).submit(
        Proposal.model_validate_json(proposal.read_text(encoding="utf-8")),
        Assessment.model_validate_json(assessment.read_text(encoding="utf-8")),
    )
    output({"request_id": rid})


@app.command()
def evaluate(request_id: str, home: Path = Path(".runtime"), save: Path | None = None):
    result = Firewall(home).evaluate(request_id)
    if save:
        save.write_text(json.dumps(result["authorization"], indent=2), encoding="utf-8")
    output(result)


@app.command()
def review(
    request_id: str, decision: str, reason: str, revision: int = 1, home: Path = Path(".runtime")
):
    output(
        Firewall(home).review(
            request_id,
            ReviewDecision.model_validate({"decision": decision, "reason": reason}),
            revision,
        )
    )


@app.command()
def execute(token: Path, mode: str = "success", home: Path = Path(".runtime")):
    output(Firewall(home).execute(json.loads(token.read_text(encoding="utf-8")), mode=mode))


@app.command()
def reconcile(authorization_id: str, settle: bool = False, home: Path = Path(".runtime")):
    output(Firewall(home).reconcile(authorization_id, settle=settle))


@app.command()
def inspect(request_id: str, home: Path = Path(".runtime")):
    output(Firewall(home).detail(request_id))


@app.command()
def outcome(
    request_id: str,
    description: str,
    kind: str = "outcome",
    source: str = "local-operator",
    home: Path = Path(".runtime"),
):
    Firewall(home).outcome(
        request_id,
        OutcomeEvent.model_validate({"kind": kind, "description": description, "source": source}),
    )
    output({"recorded": True})


@app.command()
def receipt(save: Path = Path("receipt.json"), home: Path = Path(".runtime")):
    store = Firewall(home).store
    save.write_text(json.dumps(store.receipt(), indent=2), encoding="utf-8")
    save.with_suffix(".pub").write_text(base64.b64encode(store.public).decode(), encoding="ascii")
    output({"receipt": str(save), "public_key": str(save.with_suffix(".pub"))})


@app.command()
def verify(receipt_file: Path, public_key: Path):
    output(
        {
            "verified": verify_receipt(
                json.loads(receipt_file.read_text(encoding="utf-8")),
                base64.b64decode(public_key.read_text()),
            )
        }
    )


@app.command()
def replay(evaluation_id: str, home: Path = Path(".runtime")):
    output(Firewall(home).replay(evaluation_id))


@app.command()
def benchmark(
    output_dir: Path,
    provider: str = "fixture",
    variations: int = 200,
    seed: int = 42,
    device: str = "auto",
    limit: int = 0,
):
    from .evaluation import benchmark as run

    output(run(output_dir, provider, variations, seed, device, limit))


@app.command()
def report(run: Path):
    from .evaluation import write_report

    write_report(run, json.loads((run / "results.json").read_text(encoding="utf-8")))
    output({"report": str(run / "report.html")})


@app.command()
def serve(home: Path = Path(".runtime"), runs: Path = Path("runs"), port: int = 8765):
    import uvicorn

    from .web import create_app

    uvicorn.run(create_app(home, runs), host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
