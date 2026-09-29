"""AgentDojo banking with original task/attack definitions and utility/security checks."""

import json

from .boundary import Boundary, banking_policy


def run(task_id, injection_id, arm, home, bridge, max_steps=20):
    from agentdojo.agent_pipeline.agent_pipeline import load_system_message
    from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutor
    from agentdojo.attacks.base_attacks import FixedJailbreakAttack
    from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
    from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
    from agentdojo.task_suite.load_suites import get_suite
    from agentdojo.types import get_text_content_as_str, text_content_block_from_string

    suite = get_suite("v1.2.2", "banking")
    task = suite.user_tasks[task_id]
    boundary = Boundary(arm, home, banking_policy, lambda _t, _a: {"query": task.PROMPT})

    class Runtime(FunctionsRuntime):
        def run_function(self, env, function, kwargs):
            try:
                self.functions[function].parameters.model_validate(kwargs)
                return boundary.invoke(
                    function,
                    kwargs,
                    lambda: super(Runtime, self).run_function(env, function, kwargs),
                )
            except (ValueError, KeyError) as exc:
                return None, str(exc)

    class Pipeline(BasePipelineElement):
        name = "budgeted-gpt-oss-20b"

        def __init__(self):
            self.exhausted = False
            self.transcript = []

        def query(self, query, runtime, env, messages=(), extra_args=None):
            history = [
                {
                    "role": "system",
                    "content": [text_content_block_from_string(load_system_message(None))],
                },
                {"role": "user", "content": [text_content_block_from_string(query)]},
            ]
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": f.name,
                        "description": f.description,
                        "parameters": f.parameters.model_json_schema(),
                    },
                }
                for f in runtime.functions.values()
            ]
            for turn in range(max_steps):
                outgoing = []
                for m in history:
                    item = {
                        "role": m["role"],
                        "content": get_text_content_as_str(m["content"]) if m["content"] else None,
                    }
                    if m["role"] == "assistant" and m.get("tool_calls"):
                        item["tool_calls"] = [
                            {
                                "id": t.id,
                                "type": "function",
                                "function": {
                                    "name": t.function,
                                    "arguments": json.dumps(t.args),
                                },
                            }
                            for t in m["tool_calls"]
                        ]
                    if m["role"] == "tool":
                        item["tool_call_id"] = m["tool_call_id"]
                        item["content"] = m.get("error") or item["content"] or ""
                    outgoing.append(item)
                response = bridge.complete(outgoing, tools, f"dojo:{task_id}:{injection_id}:{turn}")
                msg = response["choices"][0]["message"]
                calls = [
                    FunctionCall(
                        id=t["id"],
                        function=t["function"]["name"],
                        args=json.loads(t["function"]["arguments"]),
                    )
                    for t in msg.get("tool_calls") or []
                ]
                history.append(
                    {
                        "role": "assistant",
                        "content": [text_content_block_from_string(msg.get("content") or "")],
                        "tool_calls": calls or None,
                    }
                )
                if not calls:
                    break
                _, _, _, history, _ = ToolsExecutor().query(query, runtime, env, history, {})
            else:
                self.exhausted = True
                # Ensure the upstream wrapper never restarts an exhausted episode.
                history.append(
                    {
                        "role": "assistant",
                        "content": [
                            text_content_block_from_string("Benchmark step budget exhausted.")
                        ],
                        "tool_calls": None,
                    }
                )
            self.transcript = history
            return query, runtime, env, history, {}

    pipeline = Pipeline()
    injection = suite.injection_tasks[injection_id] if injection_id else None
    injections = {}
    if injection:
        # Exact upstream fixed template/default names; attacker alone sees goal/GT.
        attack = FixedJailbreakAttack(ImportantInstructionsAttack._JB_STRING, suite, pipeline)
        injections = attack.attack(task, injection)
    utility, attack_success = suite.run_task_with_pipeline(
        pipeline,
        task,
        injection,
        injections,
        runtime_class=Runtime,
    )
    (home / "trajectory.json").write_text(
        json.dumps(pipeline.transcript, default=lambda obj: obj.model_dump(), indent=2),
        encoding="utf-8",
    )
    return {
        "task_success": utility,
        "attack_success": attack_success if injection else None,
        "termination": "step_limit" if pipeline.exhausted else "completed",
        "injection_vectors": sorted(injections),
        **boundary.finish(),
    }
