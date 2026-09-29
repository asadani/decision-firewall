"""Best-effort observation; buffered until the governance operation leaves transactions."""

import hashlib
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class Observation:
    name: str
    correlation_id: str
    status: str
    duration_ms: float
    attributes: dict = field(default_factory=dict)


class Observer(Protocol):
    def emit(self, event: Observation) -> None: ...


_pending: ContextVar[list | None] = ContextVar("firewall_observations", default=None)
_current: ContextVar[tuple | None] = ContextVar("firewall_operation", default=None)
diagnostics = {"observer_errors": 0, "buffer_drops": 0}
MAX_OPERATION_EVENTS = 256


def emit(observer, name, correlation_id, status, duration_ms=0.0, *, attributes=None):
    if observer is None:
        return
    event = Observation(name, str(correlation_id), status, duration_ms, attributes or {})
    pending = _pending.get()
    if pending is not None:
        if len(pending) < MAX_OPERATION_EVENTS:
            pending.append((observer, event))
        else:
            diagnostics["buffer_drops"] += 1
    else:
        try:
            observer.emit(event)
        except Exception:  # noqa: BLE001 -- telemetry must not change governance outcomes
            diagnostics["observer_errors"] += 1


def set_correlation(rid):
    current = _current.get()
    if current:
        _current.set((current[0], rid))


def component(name, status="ok", duration_ms=0.0, **attributes):
    current = _current.get()
    if current:
        emit(current[0], name, current[1], status, duration_ms, attributes=attributes)


def observed(name):
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            observer = getattr(self, "observer", None)
            if observer is None:
                return function(self, *args, **kwargs)
            value = args[0] if args else None
            rid = (
                value
                if isinstance(value, str)
                else value.get("payload", {}).get("request_id")
                if isinstance(value, dict)
                else None
            )
            # Until runtime lookup succeeds, submitted identifiers/tokens are untrusted content.
            rid = hashlib.sha256(str(rid).encode()).hexdigest() if rid else uuid4().hex
            outer = _pending.get() is None
            pending_token = _pending.set([]) if outer else None
            current_token = _current.set((observer, rid))
            start, status = time.perf_counter(), "ok"
            try:
                result = function(self, *args, **kwargs)
                if name.endswith("submit") and isinstance(result, str):
                    rid = result
                return result
            except BaseException:
                status = "error"
                raise
            finally:
                current = _current.get()
                rid = current[1] if current else rid
                emit(observer, name, rid, status, (time.perf_counter() - start) * 1000)
                _current.reset(current_token)
                if outer:
                    pending = _pending.get() or []
                    assert pending_token is not None
                    _pending.reset(pending_token)
                    for target, event in pending:
                        try:
                            target.emit(event)
                        except Exception:  # noqa: BLE001 -- export errors are diagnostic only
                            diagnostics["observer_errors"] += 1

        return wrapped

    return decorate


def trace_id(correlation_id: str) -> int:
    # Reconstructible after restart without altering receipts or authorization fingerprints.
    return int(
        hashlib.sha256(("decision-firewall:" + correlation_id).encode()).hexdigest()[:32], 16
    )
