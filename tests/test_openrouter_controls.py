import io
import json
import random
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError

import pytest

from benchmarks.agent_suites.openrouter import Budget, Client, Settings, delay_seconds


def reply(cost=0.00001, finish="stop"):
    return io.BytesIO(
        json.dumps(
            {
                "model": "openai/gpt-oss-20b",
                "provider": "Darkbloom",
                "usage": {"cost": cost},
                "choices": [
                    {"finish_reason": finish, "message": {"role": "assistant", "content": "DONE"}}
                ],
            }
        ).encode()
    )


def test_backoff_caps_seed_and_costs(tmp_path):
    bodies, sleeps = [], []

    def send(request, timeout):
        bodies.append(json.loads(request.data))
        if len(bodies) == 1:
            raise HTTPError(request.full_url, 429, "limited", {"Retry-After": "7"}, None)
        return reply()

    budget = Budget(tmp_path / "budget.db")
    client = Client("SECRET", budget, sleep=sleeps.append, send=send)
    client.complete([{"role": "user", "content": "private"}], case_id="case-1")
    assert bodies[0] == bodies[1]
    assert bodies[0]["max_tokens"] == 1024
    assert bodies[0]["seed"] == client.events[0]["seed"]
    assert sleeps == [7]
    assert budget.db.execute("SELECT status FROM calls ORDER BY rowid").fetchall() == [
        ("reserved",),
        ("reported",),
    ]
    assert "SECRET" not in json.dumps(client.events)
    assert "private" not in json.dumps(client.events)
    persisted = budget.db.execute("SELECT metadata FROM attempts ORDER BY reservation").fetchall()
    assert len(persisted) == 2
    assert (
        json.loads(persisted[0][0])["request_hash"] == json.loads(persisted[1][0])["request_hash"]
    )
    assert "SECRET" not in str(persisted) and "private" not in str(persisted)


def test_retry_after_date_and_long_wait():
    now = datetime(2026, 9, 28, tzinfo=UTC)
    assert delay_seconds("Mon, 28 Sep 2026 00:02:00 GMT", 0, random.Random(1), now) == 120


@pytest.mark.parametrize("status", [401, 402, 404, 500])
def test_no_retry_for_other_errors(tmp_path, status):
    calls = []

    def send(request, timeout):
        calls.append(1)
        raise HTTPError(request.full_url, status, "secret server body", {}, None)

    client = Client("SECRET", Budget(tmp_path / "budget.db"), send=send)
    with pytest.raises(RuntimeError):
        client.complete([], case_id="x")
    assert len(calls) == 1


def test_ambiguous_network_failure_keeps_reservation_after_restart(tmp_path):
    path = tmp_path / "budget.db"

    def send(request, timeout):
        raise URLError("credential-bearing error")

    client = Client("SECRET", Budget(path, limit=0.005, previous_spend_reserve=0), send=send)
    with pytest.raises(RuntimeError, match="no blind retry"):
        client.complete([], case_id="x")
    restarted = Budget(path, limit=0.005, previous_spend_reserve=0)
    with pytest.raises(RuntimeError, match="exhausted"):
        restarted.reserve(0.004)


@pytest.mark.parametrize(
    "cost,finish", [(None, "stop"), (float("nan"), "stop"), (0.00001, "length")]
)
def test_unknown_cost_and_truncation_stop(tmp_path, cost, finish):
    client = Client(
        "SECRET", Budget(tmp_path / "budget.db"), send=lambda *a, **k: reply(cost, finish)
    )
    with pytest.raises((RuntimeError, TypeError)):
        client.complete([], case_id="x")


def test_retry_limit_and_long_retry_after(tmp_path):
    for suffix, header, expected in [("bounded", "0", 4), ("defer", "120", 1)]:
        calls = []

        def send(request, timeout, calls=calls, header=header):
            calls.append(1)
            raise HTTPError(request.full_url, 429, "limited", {"Retry-After": header}, None)

        client = Client("SECRET", Budget(tmp_path / suffix), sleep=lambda _: None, send=send)
        with pytest.raises(RuntimeError):
            client.complete([], case_id="x")
        assert len(calls) == expected


def test_limits_validate():
    with pytest.raises(ValueError):
        Settings(max_attempts=5)
    with pytest.raises(ValueError):
        Settings(max_tokens=0)


@pytest.mark.parametrize("amount", [-1, 0, float("nan"), float("inf")])
def test_invalid_reservation_never_changes_budget(tmp_path, amount):
    budget = Budget(tmp_path / "budget.db")
    with pytest.raises(ValueError):
        budget.reserve(amount)
    assert budget.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0


def test_settlement_once_and_overrun_blocks_restart(tmp_path):
    path = tmp_path / "budget.db"
    budget = Budget(path)
    row = budget.reserve(0.001)
    budget.settle(row, 0.0005)
    with pytest.raises(RuntimeError, match="already settled"):
        budget.settle(row, 0)
    assert budget.db.execute("SELECT cost FROM calls WHERE rowid=?", (row,)).fetchone()[0] == 0.0005
    row = budget.reserve(0.001)
    with pytest.raises(RuntimeError, match="Price bound"):
        budget.settle(row, 0.002)
    with pytest.raises(RuntimeError, match="previously"):
        Budget(path).reserve(0.001)


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "OtherProvider"},
        {"choices": []},
        {"choices": [{"finish_reason": "content_filter", "message": {"role": "assistant"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"role": "user", "content": "DONE"}}]},
        {
            "choices": [
                {"finish_reason": "tool_calls", "message": {"role": "assistant", "tool_calls": []}}
            ]
        },
        {"choices": [{"finish_reason": "error", "message": {"role": "assistant"}}]},
    ],
)
def test_bad_response_never_returned_for_execution(tmp_path, change):
    result = json.load(reply())
    result.update(change)
    client = Client(
        "SECRET",
        Budget(tmp_path / "budget.db"),
        send=lambda *a, **k: io.BytesIO(json.dumps(result).encode()),
    )
    with pytest.raises(RuntimeError):
        client.complete([], case_id="x")
    assert client.budget.db.execute("SELECT status FROM calls").fetchone()[0] == "reported"


def test_redirect_refused():
    from benchmarks.agent_suites.openrouter import NoRedirect

    assert (
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid") is None
    )
