import base64
import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.cli import app
from decision_firewall.context import ContextualModel, LexicalHistoryRetriever
from decision_firewall.core import (
    Context,
    Decision,
    Disposition,
    Evidence,
    Review,
    Signal,
    verify_receipt,
)
from decision_firewall.core.rules import Rule, RuleResult, RuleSet
from decision_firewall.domains.access.pack import AccessPolicy, access_domain
from decision_firewall.domains.access.pack_v1 import access_domain as old_access
from decision_firewall.experiments import (
    EvaluationPolicy,
    ExperimentRunner,
    ExperimentSpec,
    ExperimentVariant,
    Score,
    Threshold,
)
from decision_firewall.history import (
    DatasetSnapshot,
    ExpectedLabels,
    FieldMapper,
    HistoricalDecision,
    HistoryStore,
)


def record(source_id="one", *, at=100.0, hours=4):
    return HistoricalDecision(
        source="synthetic",
        source_id=source_id,
        source_revision="1",
        proposal=Proposal(
            domain="access",
            message=f"Request engineering documentation {source_id}",
            action={"employee": "alice", "resource": "engineering-docs", "hours": hours},
        ),
        decision_at=at,
        available_at=at + 1,
        evidence_available_at=at - 1,
        evidence=Evidence(
            facts={"employee": {"active": True, "resources": ["engineering-docs"], "version": 1}},
            versions={"directory": "1"},
        ),
        assessment=Assessment(
            provider="fixture",
            model="test",
            revision="1",
            signals={"intent": Signal(kind="choice", value="access")},
        ),
        usage={},
        historical_decision=Decision(disposition=Disposition.ALLOW),
        groups={"customer": source_id},
        policy_version="access-demo-v1",
    )


def test_policy_cannot_mutate_input_snapshot(tmp_path):
    from decision_firewall.core.policy import evaluate_context

    item = record()
    context = Context(
        proposal=item.proposal,
        assessment=item.assessment,
        evidence=item.evidence,
        now=100,
        usage={},
    )
    before = context.model_dump()

    def mutate(value):
        value.proposal.action["hours"] = 168
        value.evidence.facts["employee"]["active"] = False
        return Decision(disposition=Disposition.DENY)

    policy = replace(EvaluationPolicy.from_domain(access_domain(tmp_path)), evaluate=mutate)
    assert evaluate_context(policy, context).disposition == Disposition.DENY
    assert context.model_dump() == before


def test_evaluator_cannot_contaminate_later_variant(tmp_path):
    snapshot = dataset(tmp_path / "history")
    policy = EvaluationPolicy.from_domain(access_domain(tmp_path / "domain"))

    class MutatingEvaluator:
        name, version = "mutating", "1"

        def __call__(self, case, result):
            case.record.proposal.action["hours"] = 168
            case.record.evidence.facts["employee"]["active"] = False
            return []

    result = ExperimentRunner(
        [ExperimentVariant("one", policy), ExperimentVariant("two", policy)],
        evaluators=[MutatingEvaluator()],
    ).run(snapshot, ExperimentSpec(name="isolation"), tmp_path / "report")
    assert result.passed
    assert [r["actual"] for r in result.observations] == ["ALLOW_WITH_CONSTRAINTS"] * 2
    assert snapshot.cases[0].record.proposal.action["hours"] == 4


def dataset(tmp_path, records=None):
    store = HistoryStore(tmp_path)
    imported = store.import_records(records or [record("past", at=10), record("current", at=100)])
    assert imported["valid"]
    for rid in imported["record_ids"]:
        store.annotate(
            rid,
            ExpectedLabels(
                disposition=Disposition.ALLOW_WITH_CONSTRAINTS, signals={"intent": "access"}
            ),
            reviewer="curator",
            reason="Reviewed expected behavior",
            available_at=200,
        )
    return store.snapshot(
        "sample",
        {"development": imported["record_ids"][:1], "evaluation": imported["record_ids"][1:]},
        group_by="customer",
    )


def test_atomic_import_dry_run_revisions_and_conflict(tmp_path):
    store = HistoryStore(tmp_path)
    assert store.import_records([record()], dry_run=True)["created"] == 0
    result = store.import_records([record()])
    rid = result["record_ids"][0]
    assert result["created"] == 1 and store.import_records([record()])["duplicates"] == 1
    changed = record().model_copy(update={"source_revision": "2", "outcome": {"success": True}})
    second = store.import_records([changed])["record_ids"][0]
    assert store.inspect(second)["previous_id"] == rid
    conflict = changed.model_copy(update={"outcome": {"success": False}})
    failed = store.import_records([record("new"), conflict])
    assert not failed["committed"] and failed["created"] == 0 and failed["errors"]
    assert store.import_records([record("new")])["created"] == 1
    assert not (tmp_path / "governance.db").exists() and not (tmp_path / "signing.key").exists()


def test_csv_mapper_jsonl_errors_and_missing_times(tmp_path):
    file = tmp_path / "input.csv"
    with file.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["payload"])
        writer.writeheader()
        writer.writerow({"payload": record().model_dump_json()})
    mapper = FieldMapper({"source": "payload.source"})
    assert not HistoryStore(tmp_path).import_file(file, mapper=mapper)["valid"]

    class Mapper:
        def __call__(self, row):
            return HistoricalDecision.model_validate_json(row["payload"])

    assert HistoryStore(tmp_path).import_file(file, mapper=Mapper())["created"] == 1
    mapped = tmp_path / "mapped.csv"
    with mapped.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "action"])
        writer.writeheader()
        writer.writerow({"id": "mapped", "action": json.dumps(record().proposal.action)})
    mapping = FieldMapper(
        {"source_id": "id", "proposal.action": "action"},
        json_fields=["proposal.action"],
        constants={
            "source": "csv",
            "proposal": {"domain": "access", "message": "Imported request"},
        },
    )
    imported = HistoryStore(tmp_path).import_file(mapped, mapper=mapping)
    assert imported["valid"]
    assert (
        HistoryStore(tmp_path).inspect(imported["record_ids"][0])["record"]["decision_at"] is None
    )
    file = tmp_path / "bad.jsonl"
    file.write_text(record("valid").model_dump_json() + "\n{invalid}\n")
    result = HistoryStore(tmp_path).import_file(file)
    assert not result["committed"] and result["errors"][0]["row"] == 2


def test_labels_not_derived_from_past_approvals_and_immutable_snapshot(tmp_path):
    store = HistoryStore(tmp_path)
    rid = store.import_records([record()])["record_ids"][0]
    snap = store.snapshot("unlabeled", {"development": [rid]})
    assert snap.cases[0].labels is None
    store.annotate(
        rid,
        ExpectedLabels(disposition=Disposition.DENY),
        reviewer="r",
        reason="Past approval was wrong",
        available_at=200,
    )
    new = store.snapshot("curated", {"development": [rid]})
    assert new.hash != snap.hash and snap.cases[0].labels is None
    file = tmp_path / "dataset.json"
    new.save(file)
    with pytest.raises(FileExistsError):
        new.save(file)
    assert DatasetSnapshot.load(file).hash == new.hash
    tampered = json.loads(file.read_text())
    tampered["cases"][0]["labels"]["disposition"] = "ALLOW"
    with pytest.raises(ValueError, match="hash mismatch"):
        DatasetSnapshot.model_validate(tampered)
    informed = new.mark_informed("Evaluation case informed a rule correction")
    assert informed.parent_hash == new.hash and informed.development_informed


@pytest.mark.parametrize("kind", ["content", "group", "source_revision"])
def test_split_leakage_rejected(tmp_path, kind):
    first, second = record("a"), record("b")
    if kind == "content":
        second = second.model_copy(update={"proposal": first.proposal})
    elif kind == "group":
        second = second.model_copy(update={"groups": first.groups})
    else:
        second = first.model_copy(update={"source_revision": "2", "decision_at": 200})
    store = HistoryStore(tmp_path)
    ids = store.import_records([first, second])["record_ids"]
    with pytest.raises(ValueError):
        store.snapshot(
            "leak", {"development": [ids[0]], "evaluation": [ids[1]]}, group_by="customer"
        )


def test_history_retrieval_excludes_future_unknown_self_and_heldout(tmp_path):
    records = [
        record("past", at=10),
        record("future", at=300),
        record("unknown", at=20).model_copy(update={"available_at": None}),
        record("current", at=100),
    ]
    store = HistoryStore(tmp_path)
    ids = store.import_records(records)["record_ids"]
    snap = store.snapshot("retrieval", {"development": ids[:3], "evaluation": ids[3:]})
    selected = LexicalHistoryRetriever(ids[:3]).retrieve(snap.cases[-1], snap)
    assert [e.record_id for e in selected] == ids[:1]
    with pytest.raises(ValueError, match="Validation/evaluation"):
        LexicalHistoryRetriever(ids).retrieve(snap.cases[-1], snap)
    assert LexicalHistoryRetriever(ids[:1]).retrieve(snap.cases[0], snap) == []


def test_context_budget_preserves_request_and_records_omissions(tmp_path):
    snap = dataset(tmp_path)
    case = snap.cases[-1]

    class Model:
        def assess_context(self, input):
            assert input.message == case.record.proposal.message
            assert input.examples == []
            return record().assessment

    model = ContextualModel(
        Model(),
        LexicalHistoryRetriever([snap.cases[0].id]),
        max_input_units=len(case.record.proposal.message),
    )
    result = model.assess_case(case, snap)
    assert result.metadata["historical_context"]["omitted"]
    assert result.metadata["historical_context"]["selected"] == []
    with pytest.raises(ValueError, match="never truncated"):
        ContextualModel(Model(), model.retriever, max_input_units=1).assess_case(case, snap)


def test_offline_policy_never_resolves_or_executes(tmp_path):
    snap = dataset(tmp_path / "history")
    pack = access_domain(tmp_path / "runtime")

    def forbidden(*args, **kwargs):
        raise AssertionError("Live capability invoked")

    pack = replace(pack, resolve=forbidden)
    pack.executor.execute = forbidden
    pack.executor.reconcile = forbidden
    policy = EvaluationPolicy.from_domain(pack)
    assert not hasattr(policy, "executor") and not hasattr(policy, "resolve")
    runner = ExperimentRunner([ExperimentVariant("base", policy)])
    spec = ExperimentSpec(
        name="offline", split="evaluation", thresholds=[Threshold(metric="false_allows", maximum=0)]
    )
    one = runner.run(snap, spec, tmp_path / "one")
    two = runner.run(snap, spec, tmp_path / "two")
    assert one.passed and one.manifest == two.manifest
    assert one.summaries["base"]["disposition_agreement"] == 1
    assert one.observations[0]["rules"]
    assert not (tmp_path / "runtime" / "governance.db").exists()
    assert {
        "results.json",
        "observations.csv",
        "manifest.json",
        "dataset.json",
        "summary.md",
        "report.html",
    } <= {p.name for p in (tmp_path / "one").iterdir()}


@pytest.mark.parametrize(
    "field", ["usage", "evidence", "evidence_available_at", "decision_at", "assessment"]
)
def test_incomplete_snapshots_are_not_invented(tmp_path, field):
    snap = dataset(
        tmp_path / "history",
        [record("past", at=10), record("now").model_copy(update={field: None})],
    )
    policy = EvaluationPolicy.from_domain(access_domain(tmp_path / "runtime"))
    result = ExperimentRunner([ExperimentVariant("base", policy)]).run(
        snap, ExperimentSpec(name="incomplete", split="evaluation"), tmp_path / "run"
    )
    assert not result.passed and result.summaries["base"]["incomplete"] == 1
    assert result.observations[0]["actual"] is None


def test_metrics_custom_invariant_and_model_failure(tmp_path):
    snap = dataset(tmp_path / "history")

    class Model:
        def assess(self, message):
            return Assessment(
                provider="fixture",
                model="signals",
                revision="1",
                signals={
                    "intent": Signal(kind="choice", value="access"),
                    "risk": Signal(kind="probability", value=0.25),
                    "urgency": Signal(kind="ordinal", value=2.0),
                },
            )

    data = snap.model_dump()
    data["hash"] = ""
    data["cases"][-1]["labels"]["signals"].update(risk=0.0, urgency=3.0)
    snap = DatasetSnapshot.model_validate(data)

    class Invariant:
        name = "expected_failure"
        version = "1"

        def __call__(self, case, result):
            return [Score(name=self.name, value=False, hard_invariant=True)]

    policy = EvaluationPolicy.from_domain(access_domain(tmp_path / "runtime"))
    runner = ExperimentRunner(
        [ExperimentVariant("model", policy, Model(), {"model": "signals", "revision": "1"})],
        evaluators=[Invariant()],
    )
    result = runner.run(
        snap, ExperimentSpec(name="scores", mode="model", split="evaluation"), tmp_path / "scores"
    )
    assert not result.passed and result.summaries["model"]["hard_invariant_failures"] == 1
    scores = result.summaries["model"]["signals"]
    assert scores["risk"]["brier"] == 0.0625 and scores["urgency"]["mean_absolute_error"] == 1

    class Broken:
        def assess(self, message):
            raise RuntimeError("Unavailable")

    result = ExperimentRunner(
        [ExperimentVariant("bad", policy, Broken(), {"model": "bad", "revision": "1"})]
    ).run(snap, ExperimentSpec(name="bad", mode="model", split="evaluation"), tmp_path / "bad")
    assert (
        result.summaries["bad"]["invalid_outputs"] == 1 and result.observations[0]["actual"] is None
    )


def test_named_rules_hard_denial_exceptions_and_conflicting_claims(tmp_path):
    config = AccessPolicy()
    r = record()
    context = Context(
        proposal=r.proposal,
        assessment=r.assessment,
        evidence=r.evidence,
        usage={},
        now=100,
        review=Review(decision="approve", reason="Approved by reviewer"),
    )
    deny = Rule(
        "hard", "1", "Mandatory", lambda c, p: RuleResult(status="deny", reasons=["no"]), config
    )
    review = Rule(
        "review",
        "1",
        "Discretionary",
        lambda c, p: RuleResult(status="review"),
        config,
        kind="review",
    )
    report = RuleSet([review, deny]).evaluate_report(context)
    assert report.decision.disposition == "DENY" and report.rules[0].name == "hard"
    assert report.rules[1].status == "satisfied_by_review"

    def broken(c, p):
        raise OSError("rule failed")

    assert RuleSet([Rule("broken", "1", "fail", broken, config), deny])(context).errors
    from decision_firewall.core import Claim

    def claim(c, p):
        return RuleResult(claims=[Claim(key="same", units=1, capacity=10)])

    assert RuleSet(
        [Rule("a", "1", "claim", claim, config), Rule("b", "1", "claim", claim, config)]
    )(context).errors


def test_v02_receipt_and_policy_snapshot_still_verify(tmp_path):
    golden = json.loads((Path(__file__).parent / "fixtures/v02-compat.json").read_text())
    assert verify_receipt(golden["receipt"], base64.b64decode(golden["receipt"]["public_key"]))
    pack = old_access(tmp_path)
    assert pack.fingerprint == golden["fingerprint"]
    from decision_firewall.core.policy import evaluate_context

    old = golden["check"]
    assert evaluate_context(pack, Context.model_validate_json(old["context"])).model_dump(
        mode="json"
    ) == json.loads(old["result"])
    fw = DecisionFirewall(tmp_path, [pack])
    with fw.store.transaction() as db:
        db.execute(
            "INSERT INTO checks VALUES (?,?,?,?,?,?)",
            tuple(
                old[k] for k in ("id", "request_id", "domain_hash", "manifest", "context", "result")
            ),
        )
    assert fw.replay(old["id"])["matches"]


def test_cli_file_workflow_and_threshold_exit(tmp_path):
    runner = CliRunner()
    file = tmp_path / "history.jsonl"
    home = tmp_path / "history"
    file.write_text(record().model_dump_json() + "\n")
    imported = runner.invoke(app, ["history", "import", str(file), "--home", str(home)])
    assert imported.exit_code == 0, imported.output
    rid = json.loads(imported.output)["record_ids"][0]
    labels = tmp_path / "labels.json"
    labels.write_text('{"disposition":"DENY"}')
    assert (
        runner.invoke(
            app,
            [
                "history",
                "annotate",
                rid,
                str(labels),
                "reviewer",
                "Reviewed sample",
                "200",
                "--home",
                str(home),
            ],
        ).exit_code
        == 0
    )
    memberships = tmp_path / "memberships.json"
    memberships.write_text(json.dumps({"evaluation": [rid]}))
    save = tmp_path / "dataset.json"
    assert (
        runner.invoke(
            app, ["datasets", "create", "test", str(memberships), str(save), "--home", str(home)]
        ).exit_code
        == 0
    )
    config = tmp_path / "experiment.json"
    config.write_text(
        json.dumps(
            {
                "dataset": "dataset.json",
                "spec": {
                    "name": "threshold",
                    "split": "evaluation",
                    "thresholds": [{"metric": "false_allows", "maximum": 0}],
                },
                "variants": [{"name": "base", "domain": "access"}],
            }
        )
    )
    run = runner.invoke(app, ["experiments", "run", str(config), str(tmp_path / "run")])
    assert run.exit_code == 2 and (tmp_path / "run" / "report.html").exists(), run.output


def test_malformed_csv_is_atomic(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text('id,message\n1,"unterminated', encoding="utf-8")
    result = HistoryStore(tmp_path).import_file(path)
    assert not result["committed"] and "Malformed CSV" in result["errors"][0]["error"]


def test_future_evidence_is_incomplete_and_thresholds_need_bounds(tmp_path):
    future = record("future").model_copy(update={"evidence_available_at": 1000})
    snapshot = dataset(tmp_path, [record("past", at=10), future])
    result = ExperimentRunner(
        [ExperimentVariant("base", EvaluationPolicy.from_domain(access_domain(tmp_path)))]
    ).run(snapshot, ExperimentSpec(name="future", split="evaluation"), tmp_path / "run")
    assert not result.passed and result.summaries["base"]["incomplete"] == 1
    with pytest.raises(ValueError):
        Threshold(metric="false_allows")


def test_custom_retriever_cannot_inject_unpinned_context(tmp_path):
    snapshot = dataset(tmp_path)
    original = LexicalHistoryRetriever([snapshot.cases[0].id])

    class Unsafe:
        def manifest(self):
            return original.manifest()

        def retrieve(self, case, data):
            result = original.retrieve(case, data)
            return [result[0].model_copy(update={"message": "Injected approval"})]

    class Model:
        def assess_context(self, input):
            raise AssertionError("Unsafe retrieval must be rejected before inference")

    with pytest.raises(ValueError, match="pinned history"):
        ContextualModel(Model(), Unsafe()).assess_case(snapshot.cases[1], snapshot)
