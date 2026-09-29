# Examples

Install the package from the repository root first. None of these connect to real action systems.

| Example | Command | Demonstrates |
|---|---|---|
| Access | `python examples/access/quickstart.py` | Non-financial policy, review, execution, receipt, replay |
| Refunds | `firewall framework --domain refunds demo` | Refund domain on the generic runtime |
| Custom domain | `firewall init my-app` then `python my-app/run.py` | Independent editable domain outside this repository |
| Existing refund workbench | `firewall demo` then `firewall serve` | v0.1-compatible reference inspector |

`refund/*.json` retains the v0.1 proposal/assessment format. New generic proposals wrap domain data in `action` and declare `domain`. See the framework model guide for local Laya and external SDK integration.
