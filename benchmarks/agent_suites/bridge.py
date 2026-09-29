"""Identical-input response reuse and the sole paid-network entry point."""

import http.client
import json
import os
import urllib.request
from dataclasses import asdict

from decision_firewall.core.audit import digest

from .openrouter import Budget, Client, Settings, safe_open


class Bridge:
    def __init__(self, client, cache):
        self.client, self.cache = client, cache
        cache.mkdir(parents=True, exist_ok=True)
        self.calls = []

    def complete(self, messages, tools, case_id):
        key = digest(
            {
                "messages": messages,
                "tools": tools,
                "case": case_id,
                "settings": asdict(self.client.settings),
            }
        )
        path = self.cache / f"{key}.json"
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8"))
            cached = True
        else:
            result = self.client.complete(messages, tools=tools, case_id=case_id)
            with path.open("x", encoding="utf-8") as stream:
                json.dump(result, stream)
            cached = False
        self.calls.append(
            {
                "case_id": case_id,
                "response_hash": digest(result),
                "cache_hit": cached,
                "usage": result["usage"],
            }
        )
        return result


def configured_client(env_file, budget_db, max_tokens=2048):
    key = os.environ.get("OPENROUTER_API_KEY")
    if env_file:
        values = [
            line.split("=", 1)[1].strip().strip("\"'")
            for line in env_file.read_text(encoding="utf-8-sig").splitlines()
            if line.startswith("OPENROUTER_API_KEY=")
        ]
        if len(values) != 1:
            raise ValueError("Expected one key entry; values suppressed")
        key = values[0]
    if not key or any(c.isspace() for c in key):
        raise ValueError("Missing/malformed key; values suppressed")
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": "Bearer " + key},
    )
    try:
        with safe_open(request, timeout=30) as response:
            limits = json.load(response)["data"]
        if limits["limit"] != 5 or limits.get("limit_reset") is not None:
            raise ValueError("Expected authorized non-resetting $5 cap")
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        raise RuntimeError(
            "Could not verify non-resetting $5 remote cap; details suppressed"
        ) from None
    return Client(key, Budget(budget_db), Settings(max_tokens=max_tokens))
