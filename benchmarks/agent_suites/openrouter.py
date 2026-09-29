"""Sequential, budgeted OpenRouter transport for benchmark integrations, not core."""

import hashlib
import http.client
import json
import math
import random
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a bearer credential to a redirect target.
        return None


def safe_open(request, timeout):
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout)


@dataclass(frozen=True)
class Settings:
    model: str = "openai/gpt-oss-20b"
    provider: str = "darkbloom"
    seed: int = 20260928
    max_tokens: int = 1024
    max_attempts: int = 4
    max_wait_seconds: float = 60
    # Endpoint price ceilings, dollars per million tokens.
    input_price: float = 0.03
    output_price: float = 0.15
    context_tokens: int = 131072

    def __post_init__(self):
        if self.model != "openai/gpt-oss-20b":
            raise ValueError("Revalidate context and pricing bounds for a different model")
        if not 1 <= self.max_tokens <= 4096 or not 1 <= self.max_attempts <= 4:
            raise ValueError("Invalid output or attempt limit")
        if not 0 < self.max_wait_seconds <= 60:
            raise ValueError("Wait limit must be within 60 seconds")
        if any(not math.isfinite(x) or x <= 0 for x in (self.input_price, self.output_price)):
            raise ValueError("Invalid price ceiling")
        if self.context_tokens != 131072:
            raise ValueError("Revalidate the model context bound before changing it")


class Budget:
    """Durable reservations survive crashes; unknown costs stay reserved.

    Share one database across agent, simulated user and retries. Initial reserve
    covers earlier pilot charges and delayed accounting; never infer spend from
    a temporarily stale remote counter.
    """

    def __init__(self, path, limit=5.0, previous_spend_reserve=0.01):
        if not 0 < limit <= 5 or not 0 <= previous_spend_reserve <= limit:
            raise ValueError("Invalid budget")
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS budget (cap REAL, prior REAL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS calls (cost REAL, status TEXT)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS attempts (reservation INTEGER PRIMARY KEY, metadata TEXT)"
        )
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            stored = self.db.execute("SELECT cap, prior FROM budget").fetchone()
            if stored is None:
                self.db.execute("INSERT INTO budget VALUES (?, ?)", (limit, previous_spend_reserve))
            elif stored != (limit, previous_spend_reserve):
                raise ValueError("Cannot silently change an existing budget")

    def record(self, row, event):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO attempts VALUES (?, ?)",
                (row, json.dumps(event, allow_nan=False)),
            )

    def reserve(self, amount):
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Invalid reservation")
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Invalid reservation")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute("SELECT 1 FROM calls WHERE status='overrun'").fetchone():
                raise RuntimeError("Price bound exceeded previously; reconcile before resuming")
            cap, prior = self.db.execute("SELECT cap, prior FROM budget").fetchone()
            used = self.db.execute("SELECT COALESCE(SUM(cost),0) FROM calls").fetchone()[0]
            if used + prior + amount > cap:
                raise RuntimeError("Benchmark budget exhausted")
            row = self.db.execute("INSERT INTO calls VALUES (?, 'reserved')", (amount,)).lastrowid
            self.db.commit()
            return row
        except Exception:
            self.db.rollback()
            raise

    def settle(self, row, cost):
        if isinstance(cost, bool) or not isinstance(cost, (int, float)):
            raise TypeError("Missing cost: reservation retained; stop run")
        if not math.isfinite(cost) or cost < 0:
            raise RuntimeError("Invalid cost: reservation retained; stop run")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            record = self.db.execute(
                "SELECT cost,status FROM calls WHERE rowid=?", (row,)
            ).fetchone()
            if record is None or record[1] != "reserved":
                raise RuntimeError("Reservation missing or already settled")
            held = record[0]
            status = "overrun" if cost > held else "reported"
            self.db.execute("UPDATE calls SET cost=?, status=? WHERE rowid=?", (cost, status, row))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if cost > held:
            raise RuntimeError("Price bound exceeded; stop run and reconcile billing")


def delay_seconds(header, attempt, rng, now=None):
    """Never retry earlier than Retry-After; caller defers if it exceeds its wait cap."""
    delay = min(30, 2 ** (attempt + 1)) + rng.uniform(0, 1)
    if header:
        try:
            retry = float(header)
        except ValueError:
            try:
                retry = (parsedate_to_datetime(header) - (now or datetime.now(UTC))).total_seconds()
            except (ValueError, TypeError, OverflowError):
                retry = 0
        if math.isfinite(retry):
            delay = max(delay, retry)
    return delay


class Client:
    def __init__(self, key, budget, settings=None, sleep=time.sleep, send=None):
        self.key, self.budget = key, budget
        self.settings = settings or Settings()
        self.sleep = sleep
        self.send = send or safe_open
        self.events = []  # Metadata only: no prompts, answers, headers or credentials.

    def complete(self, messages, *, case_id, tools=None):
        s = self.settings
        seed = int.from_bytes(hashlib.sha256(f"{s.seed}:{case_id}".encode()).digest()[:4], "big")
        seed %= 2**31
        body = {
            "model": s.model,
            "messages": messages,
            "seed": seed,
            "temperature": 0,
            "max_tokens": s.max_tokens,
            "reasoning": {"effort": "low"},
            "provider": {
                "only": [s.provider],
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {"prompt": s.input_price, "completion": s.output_price},
            },
        }
        if tools:
            body.update(tools=tools, tool_choice="auto")
        # Reserve against the whole model context, not an optimistic token estimate.
        reserve = (s.context_tokens * s.input_price + s.max_tokens * s.output_price) / 1_000_000
        encoded = json.dumps(body).encode()
        rng = random.Random(seed)
        for attempt in range(s.max_attempts):
            row = self.budget.reserve(reserve)
            event = {
                "case_id": case_id,
                "seed": seed,
                "attempt": attempt + 1,
                "settings": asdict(s),
                "reservation_usd": reserve,
                "request_hash": hashlib.sha256(encoded).hexdigest(),
            }
            self.events.append(event)
            self.budget.record(row, event)
            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=encoded,
                headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
            )
            started = time.perf_counter()
            try:
                with self.send(request, timeout=60) as response:
                    result = json.load(response)
            except urllib.error.HTTPError as exc:
                event["http_status"] = exc.code
                event["http_elapsed_ms"] = (time.perf_counter() - started) * 1000
                if exc.code != 429 or attempt + 1 == s.max_attempts:
                    raise RuntimeError(
                        f"OpenRouter HTTP {exc.code}; reservation retained"
                    ) from None
                delay = delay_seconds(exc.headers.get("Retry-After"), attempt, rng)
                event["retry_wait_seconds"] = delay
                if delay > s.max_wait_seconds:
                    raise RuntimeError(
                        "Rate limited: defer run until Retry-After expires"
                    ) from None
                self.sleep(delay)
                continue
            except (OSError, ValueError, http.client.HTTPException):
                raise RuntimeError(
                    "Transport/response failure; no blind retry; reservation retained"
                ) from None
            finally:
                event["elapsed_ms"] = (time.perf_counter() - started) * 1000
                self.budget.record(row, event)
            if not isinstance(result, dict) or not isinstance(result.get("usage"), dict):
                raise TypeError("Malformed response; reservation retained")
            usage = result["usage"]
            event["cost_usd"] = usage.get("cost")
            event["prompt_tokens"] = usage.get("prompt_tokens")
            event["completion_tokens"] = usage.get("completion_tokens")
            self.budget.settle(row, usage.get("cost"))
            self.budget.record(row, event)
            if result.get("model") != s.model:
                raise RuntimeError("Unexpected model; stop run")
            event["actual_provider"] = result.get("provider")
            if str(result.get("provider", "")).casefold() != s.provider.casefold():
                raise RuntimeError("Unexpected or missing provider; stop run")
            choices = result.get("choices")
            if (
                not isinstance(choices, list)
                or len(choices) != 1
                or not isinstance(choices[0], dict)
            ):
                raise RuntimeError("Malformed choices; stop run")
            finish = choices[0].get("finish_reason")
            event["finish_reason"] = finish
            self.budget.record(row, event)
            if finish == "length":
                event["truncated"] = True
                raise RuntimeError("Output token cap reached; record incomplete, do not execute")
            if finish not in {"stop", "tool_calls"}:
                raise RuntimeError("Incomplete or filtered response; do not execute")
            message = choices[0].get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise RuntimeError("Malformed assistant message; do not execute")
            if message.get("refusal"):
                raise RuntimeError("Model refusal; do not execute")
            calls = message.get("tool_calls") or []
            if finish == "tool_calls":
                names = {t["function"]["name"] for t in tools or []}
                seen = set()
                if not isinstance(calls, list) or not calls:
                    raise RuntimeError("Missing tool calls; do not execute")
                try:
                    for call in calls:
                        if (
                            not call["id"]
                            or call["id"] in seen
                            or call["type"] != "function"
                            or call["function"]["name"] not in names
                            or not isinstance(json.loads(call["function"]["arguments"]), dict)
                        ):
                            raise ValueError
                        seen.add(call["id"])
                except (ValueError, KeyError, TypeError):
                    raise RuntimeError("Invalid tool call envelope; do not execute") from None
            elif calls or not isinstance(message.get("content"), str):
                raise RuntimeError("Inconsistent completion; do not execute")
            return result
        raise RuntimeError("Retry limit reached")


def main():
    """Run a budgeted protocol smoke; this does not run either official suite."""
    import argparse
    import os
    from pathlib import Path

    from benchmarks.agent_suites.preflight import probe

    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--budget-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--max-tokens", type=int, default=1024)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; retain previous attempts")
    key = os.environ.get("OPENROUTER_API_KEY")
    if args.env_file:
        values = [
            line.split("=", 1)[1].strip().strip("\"'")
            for line in args.env_file.read_text(encoding="utf-8-sig").splitlines()
            if line.startswith("OPENROUTER_API_KEY=")
        ]
        if len(values) != 1:
            parser.error("Expected exactly one API key entry; values suppressed")
        key = values[0]
    if not key or any(c.isspace() for c in key):
        parser.error("Missing or malformed API key; values suppressed")
    try:
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key}
        )
        with safe_open(request, timeout=30) as response:
            limits = json.load(response)["data"]
        if limits["limit"] != 5 or limits.get("limit_reset") is not None:
            parser.error("Expected the authorized non-resetting $5 key cap")
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        parser.error("Could not verify remote key cap; details suppressed")
    args.budget_db.parent.mkdir(parents=True, exist_ok=True)
    client = Client(
        key, Budget(args.budget_db), Settings(seed=args.seed, max_tokens=args.max_tokens)
    )

    def completion(messages, tools):
        return client.complete(messages, tools=tools, case_id=f"echo-turn-{len(messages)}")

    result = probe("https://openrouter.ai/api/v1", client.settings.model, completion)
    result["attempts"] = client.events
    result["purpose"] = "Protocol smoke only; no official benchmark tasks"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ready"] else 2)


if __name__ == "__main__":
    main()
