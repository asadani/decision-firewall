"""Framework integration over the same business functions and fake service."""

from decision_firewall import Assessment, DecisionFirewall, Proposal
from decision_firewall.adapters.models import FixtureModel
from decision_firewall.core import (
    Claim,
    Decision,
    DomainPack,
    Evidence,
    ExecutionResult,
    Record,
    Review,
)

from .policies import policy


class Action(Record):
    # Keep domain data intact; the frozen input contract is checked by the shared policy.
    parameters: dict


class Executor:
    name, version = "reuse-fake-service", "1"
    supported_constraints = frozenset({"exact_action", "single_use"})

    def __init__(self, service):
        self.service = service

    def execute(self, key, proposal, evidence):
        return ExecutionResult(
            status=self.service.execute(
                key, proposal.action["parameters"], evidence.facts["record"]
            )
        )

    def reconcile(self, key):
        return ExecutionResult(status=self.service.reconcile(key))


def domain_pack(domain, config, service):
    def resolve(proposal):
        facts = service.facts()
        return Evidence(
            facts={"record": facts},
            versions={"record": str(facts["version"])} if facts else {},
            missing=[] if facts else ["material_evidence_missing"],
        )

    def evaluate(context):
        result, reasons, claims = policy(
            domain,
            context.proposal.action["parameters"],
            context.assessment.signals["request_type"].value,
            context.evidence.facts["record"],
            config,
            bool(context.review and context.review.decision == "approve"),
            context.usage,
        )
        return Decision(
            disposition="ALLOW_WITH_CONSTRAINTS" if result == "ALLOW" else result,
            reasons=reasons,
            constraints=["exact_action", "single_use"] if result == "ALLOW" else [],
            claims=[
                Claim(
                    key=c["key"],
                    units=c["units"],
                    capacity=c["capacity"],
                    retain_on_success=c["retain"],
                )
                for c in claims
            ],
        )

    return DomainPack(
        name=domain,
        version="1",
        policy_version=config["version"],
        action_schema=Action,
        resolve=resolve,
        evaluate=evaluate,
        executor=Executor(service),
        policy_config=config,
    )


class Framework:
    def __init__(self, home, domain, config, service, clock, observer=None):
        self.domain = domain
        self.fw = DecisionFirewall(
            home, [domain_pack(domain, config, service)], clock=clock, observer=observer
        )

    def prepare(self, action, label, assessment):
        assessed = self.fw.assess(
            FixtureModel(Assessment.model_validate(assessment)), "MESSAGE-CANARY"
        )
        rid = self.fw.submit(
            Proposal(domain=self.domain, action={"parameters": action}, message="MESSAGE-CANARY"),
            assessed,
        )
        evaluated = self.fw.evaluate(rid)
        return {
            "id": rid,
            "token": evaluated["authorization"],
            "disposition": "ALLOW"
            if evaluated["result"]["disposition"] == "ALLOW_WITH_CONSTRAINTS"
            else evaluated["result"]["disposition"],
        }

    def approve(self, handle, authorized):
        if not authorized:
            self.fw.configure_identity("reviewer", "reviewer", active=False)
        result = self.fw.review(
            handle["id"],
            Review(decision="approve", reason="Authorized synthetic review"),
            revision=1,
        )
        handle.update(token=result["authorization"], disposition=result["result"]["disposition"])

    def dispatch(self, handle):
        if not handle["token"]:
            raise ValueError("No authorization")
        return self.fw.execute(handle["token"])["status"]

    def revoke(self, handle):
        self.fw.revoke(handle["token"]["payload"]["id"])

    def reconcile(self, handle):
        return self.fw.reconcile(handle["token"]["payload"]["id"])["status"]
