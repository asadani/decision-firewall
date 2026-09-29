"""Check an explicitly supplied local OpenAI-compatible model before an agent run."""

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def probe(base_url, model, completion_fn=None):
    url = urllib.parse.urlsplit(base_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
    ):
        raise ValueError("Provide an HTTP(S) API base URL without credentials or query parameters")
    root = base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("BENCHMARK_LOCAL_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key

    def completion(messages, tools=None):
        if completion_fn is not None:
            return completion_fn(messages, tools)
        body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 128}
        if tools:
            body.update(tools=tools, tool_choice="required")
        request = urllib.request.Request(
            root + "/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        return json.load(urllib.request.urlopen(request, timeout=60))

    messages = [
        {
            "role": "user",
            "content": "Call benchmark_echo with text='ping'. After its result, reply exactly DONE in uppercase and nothing else.",
        }
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "benchmark_echo",
                "description": "A local benchmark capability check, with no external effect.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    started = time.perf_counter()
    result = {
        "base_url": root,
        "model": model,
        "api_reachable": False,
        "tool_call_valid": False,
        "tool_result_roundtrip": False,
        "error": None,
    }
    try:
        first = completion(messages, tools)
        result["api_reachable"] = True
        message = first["choices"][0]["message"]
        calls = message.get("tool_calls", [])
        valid = (
            len(calls) == 1
            and calls[0]["function"]["name"] == "benchmark_echo"
            and json.loads(calls[0]["function"]["arguments"]) == {"text": "ping"}
        )
        result["tool_call_valid"] = valid
        if valid:
            messages += [
                {"role": "assistant", "content": message.get("content"), "tool_calls": calls},
                {"role": "tool", "tool_call_id": calls[0]["id"], "content": "ping"},
            ]
            second = completion(messages)
            result["tool_result_roundtrip"] = (
                "DONE" == (second["choices"][0]["message"].get("content") or "").strip()
            )
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        RuntimeError,
    ) as exc:
        # Exception bodies can include server content/credentials; retain only the class.
        result["error"] = type(exc).__name__
    result["duration_ms"] = (time.perf_counter() - started) * 1000
    result["ready"] = result["tool_call_valid"] and result["tool_result_roundtrip"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="For example http://127.0.0.1:1234/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.base_url, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ready"] else 2)
