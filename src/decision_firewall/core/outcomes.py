"""Canonical-safe recording of authoritative outcomes, independent of adapter detail."""

from .audit import digest
from .contracts import ExecutionResult


def audit_outcome(outcome: ExecutionResult) -> ExecutionResult:
    """Preserve status and losslessly encode integers outside RFC 8785's safe range.

    Metadata must not wedge an already performed effect. Other unencodable detail
    is explicitly omitted; required audit write failures still propagate.
    """
    paths: list[list[str | int]] = []

    def normalize(value, path):
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53 - 1:
            paths.append(path)
            return str(value)
        if isinstance(value, list):
            return [normalize(item, [*path, index]) for index, item in enumerate(value)]
        if isinstance(value, dict):
            return {key: normalize(item, [*path, key]) for key, item in value.items()}
        return value

    try:
        detail = normalize(outcome.detail, [])
        if paths:
            detail = {"encoding": "safe-integers-v1", "value": detail, "integer_paths": paths}
        digest(detail)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        detail = {"audit_detail_omitted": True, "reason": "not_canonical_json"}
    return ExecutionResult(status=outcome.status, detail=detail)
