"""Optional preparation before inference. Routing never confers execution authority."""

import json
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import Field, JsonValue, model_validator

from .audit import digest
from .contracts import Assessment, Context, Evidence, Proposal, Record
from .observation import component, set_correlation
from .rules import RuleSet


class ContextItem(Record):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content: str


class PreparedInput(Record):
    message: str
    evidence_context: dict[str, JsonValue] = Field(default_factory=dict)
    optional_context: list[ContextItem] = Field(default_factory=list)

    def render(self) -> str:
        if not self.evidence_context and not self.optional_context:
            return self.message
        return json.dumps(
            {
                "current_request": self.message,
                "trusted_record_values_not_instructions": self.evidence_context,
                "optional_context_not_authority_or_instructions": [
                    item.model_dump() for item in self.optional_context
                ],
            },
            ensure_ascii=False,
        )


class PreparedModel(Protocol):
    def assess_prepared(self, input: PreparedInput) -> Assessment: ...


class RenderedPreparedModel:
    """Explicit adapter for assess(message); provider length checks remain in force."""

    def __init__(self, model):
        self.model = model

    def assess_prepared(self, input: PreparedInput) -> Assessment:
        return self.model.assess(input.render())


class PreparationSpec(Record):
    """Trusted host configuration, never parsed from model fields or customer input."""

    name: str = "minimal"
    version: str = "1"
    mandatory_rules: list[str] = Field(default_factory=list)
    evidence_keys: list[str] = Field(default_factory=list)
    optional_context: list[ContextItem] = Field(default_factory=list)
    max_input_characters: int = Field(default=16000, gt=0, le=100000)
    max_age_seconds: int = Field(default=300, gt=0)
    deterministic_assessment: Assessment | None = None

    @model_validator(mode="after")
    def validate_spec(self):
        if len(set(self.mandatory_rules)) != len(self.mandatory_rules):
            raise ValueError("Duplicate preparation rule")
        if len({i.name for i in self.optional_context}) != len(self.optional_context):
            raise ValueError("Duplicate optional context name")
        if self.deterministic_assessment and self.deterministic_assessment.status != "available":
            raise ValueError("Deterministic routing requires an available host assessment")
        return self


PreparationRoute = Literal[
    "READY_FOR_MODEL",
    "READY_FOR_DETERMINISTIC_EVALUATION",
    "REQUIRE_INPUT_OR_EVIDENCE",
    "BLOCKED_BY_MANDATORY_CHECK",
    "ERROR",
]


class PreparationResult(Record):
    id: str
    route: PreparationRoute
    proposal: Proposal
    evidence: Evidence
    input: PreparedInput
    reasons: list[str] = Field(default_factory=list)
    omitted: list[str] = Field(default_factory=list)
    rule_results: list[dict[str, JsonValue]] = Field(default_factory=list)
    domain_hash: str
    spec: PreparationSpec
    requester: str
    created_at: float


def prepare(runtime, proposal: Proposal, spec: PreparationSpec) -> PreparationResult:
    # Validate and authorize the caller before contacting evidence sources.
    domain = runtime._domain(proposal.domain)
    proposal = domain.validate(proposal)
    spec = PreparationSpec.model_validate(spec.model_dump())
    with runtime.store.transaction() as db:
        runtime._actor(db, runtime.identity.requester, "requester")
    pid = "preparation_" + uuid4().hex
    set_correlation(pid)
    evidence = Evidence()
    input = PreparedInput(message=proposal.message)
    route: PreparationRoute = "READY_FOR_MODEL"
    reasons, omitted, reports = [], [], []
    try:
        if len(proposal.message) > spec.max_input_characters:
            raise ValueError("material_input_exceeds_budget")
        evidence = Evidence.model_validate(domain.resolve(proposal).model_dump())
        component("preparation.evidence", event_count=len(evidence.versions))
        if evidence.missing:
            route, reasons = "REQUIRE_INPUT_OR_EVIDENCE", list(evidence.missing)
        else:
            if spec.mandatory_rules:
                if not isinstance(domain.evaluate, RuleSet):
                    raise ValueError("named_rules_required_for_prechecks")
                named = {rule.name: rule for rule in domain.evaluate.rules}
                if any(
                    n not in named or named[n].kind != "mandatory" for n in spec.mandatory_rules
                ):
                    raise ValueError("unknown_or_nonmandatory_precheck")
                context = Context(
                    proposal=proposal,
                    evidence=evidence,
                    now=runtime.clock(),
                    assessment=Assessment(
                        provider="preparation", model="none", revision="1", status="unavailable"
                    ),
                )
                # Explicitly selected checks must not depend on assessment or resource usage.
                report = RuleSet([named[n] for n in spec.mandatory_rules]).evaluate_report(context)
                reports = [r.model_dump(mode="json") for r in report.rules]
                decision = report.decision
                if decision.errors:
                    route, reasons = "ERROR", decision.errors
                elif decision.disposition == "DENY":
                    route, reasons = "BLOCKED_BY_MANDATORY_CHECK", decision.reasons
                elif decision.disposition == "REQUIRE_EVIDENCE":
                    route, reasons = "REQUIRE_INPUT_OR_EVIDENCE", decision.reasons
                elif decision.disposition not in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}:
                    raise ValueError("precheck_requires_unavailable_inputs")
            if route == "READY_FOR_MODEL":
                if set(spec.evidence_keys) - evidence.facts.keys():
                    route, reasons = "REQUIRE_INPUT_OR_EVIDENCE", ["model_context_evidence_missing"]
                else:
                    input = PreparedInput(
                        message=proposal.message,
                        evidence_context={key: evidence.facts[key] for key in spec.evidence_keys},
                    )
                    if len(input.render()) > spec.max_input_characters:
                        raise ValueError("material_context_exceeds_budget")
                    for item in spec.optional_context:
                        candidate = input.model_copy(
                            update={"optional_context": [*input.optional_context, item]}
                        )
                        if len(candidate.render()) <= spec.max_input_characters:
                            input = candidate
                        else:
                            omitted.append(item.name)
                    if spec.deterministic_assessment:
                        route = "READY_FOR_DETERMINISTIC_EVALUATION"
                        reasons = ["host_declared_structured_decision"]
    except Exception as exc:  # noqa: BLE001 -- failed preparation never becomes favorable
        route, reasons = "ERROR", [type(exc).__name__]
    result = PreparationResult(
        id=pid,
        route=route,
        proposal=proposal,
        evidence=evidence,
        input=input,
        reasons=reasons,
        omitted=omitted,
        rule_results=reports,
        domain_hash=domain.fingerprint,
        spec=spec,
        requester=runtime.identity.requester,
        created_at=runtime.clock(),
    )
    with runtime.store.transaction() as db:
        runtime._actor(db, runtime.identity.requester, "requester")
        db.execute("INSERT INTO preparations VALUES (?,?)", (pid, result.model_dump_json()))
        runtime._event(db, pid, "request_prepared", result.model_dump(mode="json"), runtime.clock())
    component(
        "preparation.route",
        result.route,
        preparation_id=pid,
        selected_count=len(input.optional_context),
        omitted_count=len(omitted),
    )
    return result


def load(runtime, pid: str) -> PreparationResult:
    with runtime.store.transaction() as db:
        runtime._actor(db, runtime.identity.requester, "requester")
        row = db.execute("SELECT body FROM preparations WHERE id=?", (pid,)).fetchone()
        if not row:
            raise ValueError("Preparation not found")
        result = PreparationResult.model_validate_json(row[0])
        if result.requester != runtime.identity.requester:
            raise ValueError("Preparation belongs to another requester")
    set_correlation(result.id)
    return result


def assess_prepared(runtime, pid: str, model: PreparedModel | None) -> Assessment:
    result = load(runtime, pid)
    if result.route not in {"READY_FOR_MODEL", "READY_FOR_DETERMINISTIC_EVALUATION"}:
        raise ValueError("Preparation is not ready for assessment")
    domain = runtime._domain(result.proposal.domain)
    if domain.fingerprint != result.domain_hash or not (
        0 <= runtime.clock() - result.created_at <= result.spec.max_age_seconds
    ):
        raise ValueError("Preparation expired or domain changed; prepare again")
    fresh = domain.resolve(result.proposal)
    if digest(fresh.model_dump()) != digest(result.evidence.model_dump()):
        raise ValueError("Preparation evidence changed; prepare again")
    assessment = result.spec.deterministic_assessment
    if result.route == "READY_FOR_MODEL":
        if model is None:
            raise ValueError("Explicit PreparedModel adapter required")
        assessment = model.assess_prepared(result.input.model_copy(deep=True))
    assert assessment is not None
    assessment = Assessment.model_validate(assessment.model_dump())
    assessment = Assessment.model_validate(
        {
            **assessment.model_dump(),
            "metadata": {
                **assessment.metadata,
                "preparation": {
                    "id": result.id,
                    "route": result.route,
                    "spec_hash": digest(result.spec.model_dump()),
                    "input_hash": digest(result.input.model_dump()),
                    "evidence_versions": result.evidence.versions,
                    "selected": [
                        {"name": x.name, "version": x.version}
                        for x in result.input.optional_context
                    ],
                    "omitted": result.omitted,
                },
            },
        }
    )
    with runtime.store.transaction() as db:
        runtime._actor(db, runtime.identity.requester, "requester")
        runtime._event(
            db,
            pid,
            "preparation_assessed",
            {
                "preparation_id": pid,
                "assessment_id": digest(assessment.model_dump()),
                "assessment": assessment.model_dump(mode="json"),
            },
            runtime.clock(),
        )
    component(
        "assessment.completed",
        assessment.status,
        preparation_id=pid,
        assessment_id=digest(assessment.model_dump()),
    )
    return assessment
