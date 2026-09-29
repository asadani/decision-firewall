# Connect a decision model

Models implement `assess(message: str) -> Assessment`. An adapter, fixture or externally submitted JSON uses the same contract. Policy does not choose providers.

```python
from decision_firewall.adapters.models import CallableModel

model = CallableModel(lambda message: {
    "provider": "your-provider", "model": "your-model", "revision": "pinned-version",
    "signals": {"intent": {"kind": "choice", "value": "access"}},
})
assessment = model.assess("Please grant access")
```

Replace the lambda with your SDK call/mapping. Validation failures and exceptions propagate. No favorable fixture is substituted. Applications may explicitly record `Assessment(status="unavailable", ...)`; execution then needs a new available assessment, rather than approving away a model failure.

Signals distinguish `choice`, `probability`, `ordinal` and `text`. Probabilities must be finite and in [0,1]; ordinals retain their scale. Record model identity, revision, calibration and runtime metadata. Default calibration is `uncalibrated`. Scores do not establish facts, eligibility or caller permissions.

## Local Laya with your questions

Install the optional model runtime from [Windows setup](../windows-setup.md). Importing the framework never loads Torch or downloads weights.

```python
from decision_firewall.adapters.laya import LayaModel

model = LayaModel({
    "intent": {
        "type": "choice",
        "instructions": "What is the person requesting?",
        "criteria": {"access": "Temporary resource access", "other": "Another request"},
    },
    "urgent": {"type": "noul", "instructions": "Is the request explicitly urgent?"},
})
assessment = model.assess("I need temporary access to the engineering docs")
```

Checkpoint: `convaiinnovations/laya-typed-decisions`, revision `1a793eb568e6718f15941d08f85432581df534e3`, SDK `0.3.20`. Choice maps to choice, `noul` to probability and `score` to ordinal. Raw output stays in metadata. One worker, FP32 and batch size one remain defaults; CUDA failure attempts CPU and reports fallback. Inputs above 256 state tokens and templates above 192 tokens are rejected to avoid silent truncation.

The old refund `LayaProvider` is a facade over this configurable adapter. `RefundModelAdapter` maps legacy fixture/keyword/Laya outputs to generic signals. The customer's declared reason remains independent in the action; classification cannot select a more favorable eligibility path.
