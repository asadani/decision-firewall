"""File-based history, immutable datasets and offline experiment commands."""

import importlib
import json
import tempfile
from pathlib import Path

import typer

from .experiments import (
    EvaluationPolicy,
    ExperimentRunner,
    ExperimentSpec,
    ExperimentVariant,
    compare_reports,
)
from .history import DatasetSnapshot, ExpectedLabels, FieldMapper, HistoryStore

history_app = typer.Typer(no_args_is_help=True)
datasets_app = typer.Typer(no_args_is_help=True)
experiments_app = typer.Typer(no_args_is_help=True)
policy_app = typer.Typer(no_args_is_help=True)


def output(value):
    typer.echo(json.dumps(value, indent=2))


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def factory(name):
    module, separator, attr = name.partition(":")
    if not separator:
        raise ValueError("Use installed.module:factory (trusted Python code)")
    return getattr(importlib.import_module(module), attr)


def mapped(mapping):
    if mapping is None:
        return None
    config = load(mapping)
    if "factory" in config:
        return factory(config["factory"])()
    return FieldMapper(**config)


@history_app.command("validate")
def validate_history(
    file: Path, home: Path = Path(".runtime-history"), mapping: Path | None = None
):
    result = HistoryStore(home).import_file(file, mapper=mapped(mapping), dry_run=True)
    output(result)
    if not result["valid"]:
        raise typer.Exit(2)


@history_app.command("import")
def import_history(file: Path, home: Path = Path(".runtime-history"), mapping: Path | None = None):
    result = HistoryStore(home).import_file(file, mapper=mapped(mapping))
    output(result)
    if not result["valid"]:
        raise typer.Exit(2)


@history_app.command("inspect")
def inspect_history(record_id: str, home: Path = Path(".runtime-history")):
    output(HistoryStore(home).inspect(record_id))


@history_app.command("annotate")
def annotate_history(
    record_id: str,
    labels: Path,
    reviewer: str,
    reason: str,
    available_at: float,
    home: Path = Path(".runtime-history"),
):
    output(
        {
            "annotation_id": HistoryStore(home).annotate(
                record_id,
                ExpectedLabels.model_validate(load(labels)),
                reviewer=reviewer,
                reason=reason,
                available_at=available_at,
            )
        }
    )


@datasets_app.command("create")
def create_dataset(
    name: str,
    memberships: Path,
    save: Path,
    home: Path = Path(".runtime-history"),
    group_by: str | None = None,
):
    snapshot = HistoryStore(home).snapshot(name, load(memberships), group_by=group_by)
    snapshot.save(save)
    output({"hash": snapshot.hash, "coverage": snapshot.coverage()})


@datasets_app.command("validate")
@datasets_app.command("inspect")
def inspect_dataset(file: Path):
    snapshot = DatasetSnapshot.load(file)
    output(
        {
            "name": snapshot.name,
            "hash": snapshot.hash,
            "coverage": snapshot.coverage(),
            "development_informed": snapshot.development_informed,
        }
    )


@datasets_app.command("mark-informed")
def mark_informed(file: Path, save: Path, reason: str):
    snapshot = DatasetSnapshot.load(file).mark_informed(reason)
    snapshot.save(save)
    output({"hash": snapshot.hash, "parent_hash": snapshot.parent_hash})


def builtin_policy(domain, configuration, home):
    if domain == "access":
        from .domains.access.pack import AccessPolicy, access_domain

        pack = access_domain(home, policy=AccessPolicy.model_validate(configuration))
    elif domain == "refunds":
        from .domains.refunds.contracts import Policy
        from .domains.refunds.pack import refund_domain

        pack = refund_domain(home, policy=Policy.model_validate(configuration))
    else:
        raise ValueError("Choose access/refunds or an explicit policy_factory")
    return EvaluationPolicy.from_domain(pack)


def build_model(config):
    from .adapters.models import FixtureModel
    from .core.contracts import Assessment

    if config.get("kind") == "fixture":
        a = Assessment.model_validate(config["assessment"])
        return FixtureModel(a), config
    if config.get("kind") == "laya":
        from .adapters.laya import LAYA_MODEL, LAYA_REVISION, LazyLayaModel

        model = LazyLayaModel(config["questions"], device=config.get("device", "auto"))
        return model, {**config, "model": LAYA_MODEL, "revision": LAYA_REVISION}
    if "factory" not in config or "manifest" not in config:
        raise ValueError("External models need a factory and explicit manifest")
    return factory(config["factory"])(), config["manifest"]


@experiments_app.command("run")
def run_experiment(config_file: Path, destination: Path):
    config = load(config_file)
    dataset = DatasetSnapshot.load(config_file.parent / config["dataset"])
    variants = []
    # Built-in factories initialize only isolated simulator files, never a live runtime directory.
    with tempfile.TemporaryDirectory(prefix="firewall-experiment-") as temp:
        for index, item in enumerate(config["variants"]):
            policy = (
                factory(item["policy_factory"])()
                if "policy_factory" in item
                else builtin_policy(item["domain"], item.get("policy", {}), Path(temp) / str(index))
            )
            if not isinstance(policy, EvaluationPolicy):
                raise TypeError("Policy factory must return a capability-limited EvaluationPolicy")
            model, manifest = build_model(item["model"]) if "model" in item else (None, None)
            if "context" in item:
                if model is None:
                    raise ValueError("Context requires an explicit model")
                from .context import ContextualModel, LexicalHistoryRetriever, RenderedContextModel

                settings = item["context"]
                measure = getattr(model, "measure_input", None)
                model = ContextualModel(
                    model if hasattr(model, "assess_context") else RenderedContextModel(model),
                    LexicalHistoryRetriever(
                        settings["reference_ids"], limit=settings.get("limit", 3)
                    ),
                    max_input_units=settings.get("budget", 256 if measure else 4096),
                    measure=measure,
                )
            variants.append(ExperimentVariant(item["name"], policy, model, manifest))
        evaluators = [factory(name)() for name in config.get("evaluators", [])]
        result = ExperimentRunner(variants, evaluators=evaluators).run(
            dataset, ExperimentSpec.model_validate(config["spec"]), destination
        )
    output(
        {
            "passed": result.passed,
            "failures": result.failures,
            "report": str(destination / "report.html"),
        }
    )
    if not result.passed:
        raise typer.Exit(2)


@experiments_app.command("compare")
def compare_experiments(runs: list[Path]):
    output(compare_reports(runs))


@policy_app.command("inspect")
def inspect_policy(
    domain: str = "access",
    config: Path | None = None,
    plugin: str | None = None,
    context_file: Path | None = None,
):
    from .core.audit import digest

    with tempfile.TemporaryDirectory() as temp:
        policy = (
            factory(plugin)()
            if plugin
            else builtin_policy(domain, load(config) if config else {}, Path(temp))
        )
        inspection = {"manifest": policy.manifest, "fingerprint": digest(policy.manifest)}
        if context_file is not None:
            from .core.contracts import Context
            from .core.policy import evaluate_context

            pinned = load(context_file)
            if not {"proposal", "assessment", "evidence", "usage", "now"}.issubset(pinned):
                raise ValueError(
                    "Inspection requires explicit proposal, assessment, evidence, usage and now"
                )
            rules: list = []
            decision = evaluate_context(policy, Context.model_validate(pinned), rules)
            inspection["decision"] = decision.model_dump(mode="json")
            inspection["rule_results"] = [rule.model_dump(mode="json") for rule in rules]
        output(inspection)
