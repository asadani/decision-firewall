"""A small, runnable domain extension; no code generation dependencies."""

from pathlib import Path

PLUGIN = """from pathlib import Path
from pydantic import Field
from decision_firewall.core import Decision, Disposition, DomainPack, Evidence, Record
from decision_firewall.adapters.simulator import SimulatedExecutor
from decision_firewall.rules import Rule, RuleResult, RuleSet
from decision_firewall.experiments import EvaluationPolicy

class Action(Record):
    title: str = Field(min_length=1)
    destination: str

class Parameters(Record):
    review_required: bool = True

def rules(review_required=True):
    config = Parameters(review_required=review_required)
    def destination(context, config):
        permitted = context.proposal.action["destination"] == context.evidence.facts["allowed_destination"]
        return RuleResult(status="pass" if permitted else "deny", reasons=["destination_checked"])
    def review(context, config):
        return RuleResult(status="review" if config.review_required else "pass", reasons=["editor_review"])
    return RuleSet([
        Rule("destination", "1", "Only the trusted destination is permitted", destination, config),
        Rule("editor", "1", "Require editorial approval", review, config, kind="review"),
    ], finalize=lambda context: Decision(disposition=Disposition.ALLOW_WITH_CONSTRAINTS,
                                        constraints=["exact_action", "single_use"]))

def create_domain(home, review_required=True):
    def resolve(proposal):
        return Evidence(facts={"allowed_destination": "sandbox"}, versions={"config": "1"})
    return DomainPack(name="documents", version="2", policy_version="documents-v2",
                      action_schema=Action, resolve=resolve, evaluate=rules(review_required),
                      executor=SimulatedExecutor(Path(home) / "documents.db"))

def create_policy():
    return offline_policy(True)

def candidate_policy():
    return offline_policy(False)

def offline_policy(review_required):
    policy = rules(review_required)
    return EvaluationPolicy({"name": "documents", "policy_version": "documents-v2",
                             "rules": policy.manifest()}, Action, policy,
                            frozenset({"exact_action", "single_use"}))
"""

EVALUATORS = """from decision_firewall.experiments import Score

class DestinationInvariant:
    name, version = "destination-invariant", "1"
    def __call__(self, case, result):
        forbidden = case.record.proposal.action["destination"] != case.record.evidence.facts["allowed_destination"]
        allowed = result["actual"] in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
        return [Score(name=self.name, value=not (forbidden and allowed), hard_invariant=True,
                      detail="Approval cannot authorize a prohibited destination")]

def create_evaluator():
    return DestinationInvariant()
"""

WORKFLOW = """import json
import sys
from pathlib import Path
from decision_firewall.history import ExpectedLabels, FieldMapper, HistoryStore
from decision_firewall.core import Disposition
from decision_firewall.experiments import ExperimentRunner, ExperimentSpec, ExperimentVariant, Threshold
from plugin import create_policy, candidate_policy
from evaluators import create_evaluator

root = Path(__file__).parent
output = Path(sys.argv[1]) if len(sys.argv) > 1 else root / ".runtime" / "experiment"
store = HistoryStore(root / ".runtime" / "history")
mapper = FieldMapper(**json.loads((root / "mapping.json").read_text()))
validation = store.import_file(root / "history.jsonl", mapper=mapper, dry_run=True)
assert validation["valid"], validation
imported = store.import_file(root / "history.jsonl", mapper=mapper)
assert imported["valid"], imported
memberships = {"development": [], "validation": [], "evaluation": []}
expected = [Disposition.REQUIRE_REVIEW, Disposition.DENY, Disposition.REQUIRE_REVIEW]
for index, rid in enumerate(imported["record_ids"]):
    store.annotate(rid, ExpectedLabels(disposition=expected[index]), reviewer="example-curator",
                   reason="Expected behavior reviewed separately from historical approval", available_at=500)
    memberships[list(memberships)[index]].append(rid)
snapshot = store.snapshot("documents-example", memberships, group_by="case_family")
result = ExperimentRunner([
    ExperimentVariant("review-required", create_policy()),
    ExperimentVariant("candidate-no-review", candidate_policy()),
], evaluators=[create_evaluator()]).run(snapshot, ExperimentSpec(
    name="editorial-policy-comparison", split="development",
    thresholds=[Threshold(metric="false_allows", maximum=0)]), output)
print(json.dumps(result.summaries, indent=2))
print("Report:", output / "report.html")
# This candidate deliberately fails the predeclared threshold. It is never adopted.
assert not result.passed and result.summaries["candidate-no-review"]["false_allows"] == 1
"""

RUN = """from pathlib import Path
from plugin import create_domain
from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.core import Review, verify_receipt

home = Path(__file__).parent / ".runtime"
fw = DecisionFirewall(home, [create_domain(home)])
rid = fw.submit(Proposal(domain="documents", message="Publish my draft",
                        action={"title": "Hello", "destination": "sandbox"}),
                Assessment(provider="fixture", model="example", revision="1"))
assert fw.evaluate(rid)["result"]["disposition"] == "REQUIRE_REVIEW"
evaluation = fw.review(rid, Review(decision="approve", reason="Reviewed the draft"), revision=1)
print(fw.execute(evaluation["authorization"]))
assert fw.replay(evaluation["evaluation_id"])["matches"]
assert verify_receipt(fw.receipt(), fw.store.public)
"""


def scaffold(directory: Path):
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise ValueError("Choose an empty directory; existing work is never overwritten")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.py").write_text(PLUGIN, encoding="utf-8")
    (directory / "run.py").write_text(RUN, encoding="utf-8")
    (directory / "workflow.py").write_text(WORKFLOW, encoding="utf-8")
    (directory / "prepare.py").write_text(
        "from decision_firewall import DecisionFirewall, PreparationSpec, Proposal\n"
        "from plugin import create_domain\n"
        "fw = DecisionFirewall('.runtime', [create_domain('.runtime')])\n"
        "proposal = Proposal(domain='documents', message='Publish this draft', "
        "action={'title': 'Draft', 'destination': 'sandbox'})\n"
        "prepared = fw.prepare(proposal, PreparationSpec(mandatory_rules=['destination']))\n"
        "print(prepared.model_dump_json(indent=2))\n"
        "# No model call, authorization or effect. Use a PreparedModel to assess READY_FOR_MODEL.\n",
        encoding="utf-8",
    )
    (directory / "evaluators.py").write_text(EVALUATORS, encoding="utf-8")
    import json

    mapping = {
        "fields": {
            "source_id": "id",
            "proposal": "request",
            "evidence": "facts",
            "decision_at": "time",
            "available_at": "available",
            "groups": "groups",
        },
        "constants": {
            "source": "starter-synthetic",
            "source_revision": "1",
            "evidence_available_at": 1,
            "usage": {},
            "policy_version": "external-v0",
            "assessment": {"provider": "fixture", "model": "example", "revision": "1"},
            "historical_decision": {"disposition": "ALLOW"},
        },
    }
    (directory / "mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    records = [
        {
            "id": str(i),
            "time": 100 * i,
            "available": 100 * i + 1,
            "groups": {"case_family": str(i)},
            "request": {
                "domain": "documents",
                "message": "Publish draft " + str(i),
                "action": {
                    "title": "Draft " + str(i),
                    "destination": "external" if i == 2 else "sandbox",
                },
            },
            "facts": {"facts": {"allowed_destination": "sandbox"}, "versions": {"config": "1"}},
        }
        for i in range(1, 4)
    ]
    (directory / "history.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    config = {
        "dataset": ".runtime/experiment/dataset.json",
        "spec": {
            "name": "validation",
            "split": "validation",
            "thresholds": [{"metric": "false_allows", "maximum": 0}],
        },
        "variants": [
            {"name": "review-required", "policy_factory": "plugin:create_policy"},
            {"name": "candidate-no-review", "policy_factory": "plugin:candidate_policy"},
        ],
        "evaluators": ["evaluators:create_evaluator"],
    }
    (directory / "experiment.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (directory / ".gitignore").write_text(".runtime/\n__pycache__/\n", encoding="utf-8")
    (directory / "README.md").write_text(
        "# Your decision domain\n\nInstall Decision Firewall from its checkout first: "
        "`python -m pip install /path/to/decision-firewall`. It is not yet published to PyPI.\n\n"
        "Run `python run.py` from this directory. All effects are simulated.\n\n"
        "Run `python prepare.py` for evidence and mandatory checks before model inference. "
        "Preparation never creates execution authority.\n\n"
        "Run `python workflow.py` for history import, reviewed labels, immutable splits and "
        "a deliberately failing candidate comparison. Inspect `.runtime/experiment/report.html`. "
        "Then run `python -m decision_firewall.cli experiments run experiment.json .runtime/validation` "
        "from this directory (or set PYTHONPATH to this directory when using firewall). "
        "Change the split to evaluation only after choosing the candidate on development/validation. "
        "Each output directory must be new. Edit mapping.json, history.jsonl, plugin.py, "
        "experiment.json and evaluators.py for your domain. No configuration is auto-adopted.\n\n"
        "Edit `plugin.py`: action schema, trusted evidence resolver, hard policy rules, "
        "review rules, then an idempotent executor. Keep core lifecycle logic unchanged. "
        "Bump domain/policy versions whenever semantics change. Add tests for denial, "
        "stale evidence, unknown outcomes, reconciliation, and retries before integrating "
        "a real executor. Plugins are trusted host code, not a sandbox.\n",
        encoding="utf-8",
    )
