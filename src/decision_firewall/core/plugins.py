"""Explicit dependency injection: plugins are trusted application code."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, JsonValue

from .audit import digest
from .contracts import Assessment, Context, Decision, Evidence, ExecutionResult, Proposal


class DecisionModel(Protocol):
    def assess(self, message: str) -> Assessment: ...


class Executor(Protocol):
    name: str
    version: str
    supported_constraints: frozenset[str]

    def execute(self, key: str, proposal: Proposal, evidence: Evidence) -> ExecutionResult: ...

    def reconcile(self, key: str) -> ExecutionResult: ...


class EvidenceResolver(Protocol):
    def __call__(self, proposal: Proposal) -> Evidence: ...


@dataclass(frozen=True)
class DomainPack:
    name: str
    version: str
    policy_version: str
    action_schema: type[BaseModel]
    resolve: EvidenceResolver
    evaluate: Callable[[Context], Decision]
    executor: Executor
    policy_config: dict[str, JsonValue] = field(default_factory=dict)
    authorization_seconds: int = 300

    def __post_init__(self):
        if not self.name or not self.version or not self.policy_version:
            raise ValueError("Domain, implementation and policy versions are required")
        if self.authorization_seconds <= 0:
            raise ValueError("Authorization lifetime must be positive")

    def manifest(self) -> dict:
        manifest = {
            "name": self.name,
            "version": self.version,
            "policy_version": self.policy_version,
            "policy_config": self.policy_config,
            "action_schema": self.action_schema.model_json_schema(),
            "executor": self.executor.name,
            "executor_version": self.executor.version,
            "constraints": sorted(self.executor.supported_constraints),
            "authorization_seconds": self.authorization_seconds,
        }

        if hasattr(self.evaluate, "manifest"):
            manifest["rules"] = self.evaluate.manifest()
        return manifest

    @property
    def supported_constraints(self):
        return self.executor.supported_constraints

    @property
    def fingerprint(self) -> str:
        return digest(self.manifest())

    def validate(self, proposal: Proposal) -> Proposal:
        action = self.action_schema.model_validate(proposal.action).model_dump(mode="json")
        return Proposal.model_validate({**proposal.model_dump(), "action": action})
