import io
import json

import pytest

from benchmarks.agent_suites.preflight import probe


def test_tool_protocol_probe_has_no_external_tool_effect(monkeypatch):
    received = []

    def respond(request, timeout):
        body = json.loads(request.data)
        received.append(body)
        message = (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "local-call",
                        "type": "function",
                        "function": {
                            "name": "benchmark_echo",
                            "arguments": '{"text":"ping"}',
                        },
                    }
                ],
            }
            if len(received) == 1
            else {"role": "assistant", "content": "DONE"}
        )
        return io.BytesIO(json.dumps({"choices": [{"message": message}]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", respond)
    result = probe("http://127.0.0.1:1234/v1", "local-model")
    assert result["ready"]
    assert len(received) == 2
    assert received[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "local-call",
        "content": "ping",
    }


def test_probe_rejects_embedded_credentials_before_network():
    with pytest.raises(ValueError, match="without credentials"):
        probe("http://user:secret@localhost/v1", "local-model")


def test_probe_does_not_accept_negative_done_sentence():
    def completion(messages, tools):
        message = {"content": "NOT DONE"}
        if tools:
            message = {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call",
                        "type": "function",
                        "function": {"name": "benchmark_echo", "arguments": '{"text":"ping"}'},
                    }
                ],
            }
        return {"choices": [{"message": message}]}

    result = probe("http://localhost/v1", "fixture", completion)
    assert result["tool_call_valid"]
    assert not result["ready"]
