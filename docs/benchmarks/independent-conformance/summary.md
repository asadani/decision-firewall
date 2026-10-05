# Independent control-conformance pilot

Measured on Windows-11-10.0.26200-SP0, Python 3.12.14.

| Arm | Injection | PASS | FAIL | ERROR | Expected result |
|---|---|---:|---:|---:|---|
| application | healthy | 3 | 0 | 0 | True |
| application | stale_approval | 2 | 1 | 0 | True |
| application | duplicate_effect | 2 | 1 | 0 | True |
| application | lost_response | 2 | 1 | 0 | True |
| framework | healthy | 3 | 0 | 0 | True |
| framework | stale_approval | 2 | 1 | 0 | True |
| framework | duplicate_effect | 2 | 1 | 0 | True |
| framework | lost_response | 2 | 1 | 0 | True |

Development-informed synthetic fixtures; one export domain
Six injected behavioural faults, not mutation coverage
No human productivity or production-effectiveness measurement
Elapsed time includes fresh-interpreter recovery; not a performance benchmark

A detected fault must produce FAIL on its targeted case. ERROR does not count as detection.
Source hashes and individual reasons are in results.json. Historical benchmark files are unchanged.

## Integration inventory

Six test protocol methods. Nonblank lines including comments:
- `benchmarks/control_conformance/adapters.py`: 136
- `benchmarks/control_conformance/recover.py`: 13
- `benchmarks/reuse_observability/application.py`: 200
- `benchmarks/reuse_observability/framework.py`: 112

Shared bridge/oracle plus reused engine source; not time saved or total system size
