"""Export deterministic scenario/policy examples and editable architecture diagrams."""

import hashlib
import json
from pathlib import Path

from decision_firewall.contracts import Policy
from decision_firewall.providers import LAYA_MODEL, LAYA_REVISION, QUESTIONS, FixtureProvider
from decision_firewall.scenarios import scenarios

ROOT = Path(__file__).resolve().parents[1]


def save(path, text):
    file = ROOT / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def main():
    cases = scenarios()
    save("evaluations/scenarios.json", json.dumps(cases, indent=2))
    save("policies/refund-demo-v1.json", Policy().model_dump_json(indent=2))
    save("examples/refund/payment.json", json.dumps(cases[0]["payment"], indent=2))
    save("examples/refund/proposal.json", json.dumps(cases[0]["proposal"], indent=2))
    save("examples/refund/assessment.json", FixtureProvider().assess("").model_dump_json(indent=2))
    save(
        "evaluations/model-manifest.json",
        json.dumps(
            {
                "model": LAYA_MODEL,
                "revision": LAYA_REVISION,
                "sdk": "laya==0.3.20",
                "questions": QUESTIONS,
            },
            indent=2,
        ),
    )
    save(
        "docs/reference-hashes.json",
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((ROOT / "refer").iterdir())
                if p.is_file()
            },
            indent=2,
        ),
    )
    diagrams = {
        "system-context": """flowchart LR
subgraph Untrusted[Untrusted proposal boundary]
Customer[Customer message] --> Model[Laya or another provider]
Model --> Proposal[Refund proposal]
end
subgraph Trusted[Trusted local operator boundary]
Ledger[(Payment evidence)] --> Gate[Decision Firewall]
Policy[Versioned policy and identities] --> Gate
Reviewer[Authorized reviewer] --> Gate
Gate --> Broker[Bound execution]
Broker --> Processor[Simulated payment processor]
Gate --> Audit[(Signed audit chain)]
Processor --> Audit
end
Proposal --> Gate
Audit --> Inspector[Local inspector and reports]
""",
        "components": """flowchart TD
CLI[Typer CLI] --> SDK[Firewall SDK]
UI[FastAPI and Jinja inspector] --> SDK
Providers[Fixture / baseline / Laya] --> Contracts[Pydantic assessment contracts]
Contracts --> SDK
SDK --> Evaluator[Pure policy evaluator]
SDK --> Store[(Governance SQLite)]
SDK --> Signer[Canonical JSON and Ed25519]
SDK --> Adapter[Payment simulator adapter]
Adapter --> Ledger[(Independent payment SQLite)]
Benchmark[Evaluation runner] --> SDK
Benchmark --> Reports[JSON / CSV / Markdown / HTML]
""",
        "refund-workflow": """sequenceDiagram
participant C as Customer / app
participant M as Laya
participant F as Firewall
participant E as Trusted evidence
participant R as Reviewer
participant P as Payment simulator
C->>M: Classify refund request
M-->>C: Typed assessment, no authority
C->>F: Submit exact refund proposal
F->>E: Resolve payment and remaining balance
E-->>F: Versioned transaction facts
F->>F: Evaluate deterministic policy
alt Missing facts
F-->>C: REQUIRE_EVIDENCE
else Review needed
F->>R: Request bounded review
R->>F: Decision and reason
F->>F: Re-evaluate hard constraints
end
F-->>C: Signed exact authorization if allowed
C->>F: Execute authorization
F->>F: Revalidate and reserve atomically
F->>P: Refund with stable idempotency key
P-->>F: Success / failure / uncertain response
F-->>C: Signed outcome-linked receipt
""",
        "authorization-lifecycle": """stateDiagram-v2
[*] --> ISSUED: Policy permits
ISSUED --> REVOKED: Revision / revocation / replacement
ISSUED --> RESERVED: Revalidate and claim atomically
RESERVED --> SUCCEEDED: Downstream commit confirmed
RESERVED --> FAILED: Definitive failure
RESERVED --> UNKNOWN: Timeout or delayed outcome
UNKNOWN --> SUCCEEDED: Reconciliation confirms commit
UNKNOWN --> FAILED: Authoritative failure
UNKNOWN --> UNKNOWN: Still pending
SUCCEEDED --> [*]
FAILED --> [*]
REVOKED --> [*]
""",
        "timeout-recovery": """sequenceDiagram
participant F as Firewall ledger
participant P as Payment ledger
F->>F: Persist reservation and attempt key K
F->>P: Refund using K
P->>P: Atomically record K and refund
P--xF: Response lost
F->>F: Record UNKNOWN, retain balance reservation
Note over F,P: Restart is safe - no new refund key
F->>P: Query authoritative status of K
P-->>F: SUCCEEDED
F->>F: Record success and finalize reservation
""",
        "evaluation-flow": """flowchart LR
Fixtures[40 curated scenarios] --> Split[Family-separated dev and evaluation]
Variations[200 seeded wrappers] --> Split
Split --> Assess[Fixture / keywords / Laya]
Assess --> Gate[Policy and execution]
Gate --> Ledger[(Durable simulated effects)]
Assess --> ModelStats[Accuracy / Brier / calibration]
Gate --> GateStats[Agreement / false allows / reviews]
Ledger --> EffectStats[Over-refunds / duplicates / unknowns]
Tests[Adversarial pytest suite] --> Faults[Concurrency / outages / revocation]
ModelStats --> Report[Measured report and manifest]
GateStats --> Report
EffectStats --> Report
Faults --> Report
""",
    }
    for name, text in diagrams.items():
        save(f"docs/diagrams/{name}.mmd", text)


if __name__ == "__main__":
    main()
