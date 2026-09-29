"""Pinned tau2 retail integration: upstream agent, user, orchestration and grading."""

import ast
import json
from collections import Counter

from .boundary import Boundary, retail_policy


def run(task_id, arm, home, bridge, max_steps=60):
    import tau2.agent.llm_agent as agent_module
    import tau2.evaluator.evaluator_nl_assertions as judge_module
    import tau2.user.user_simulator as user_module
    from tau2.data_model.message import AssistantMessage, ToolCall, ToolMessage
    from tau2.domains.retail.environment import get_environment, get_tasks
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
    from tau2.orchestrator.orchestrator import Orchestrator
    from tau2.registry import registry
    from tau2.utils.llm_utils import to_litellm_messages

    counts = {}

    def generate(model, messages, tools=None, call_name="other", **kwargs):
        counts[call_name] = counts.get(call_name, 0) + 1
        result = bridge.complete(
            to_litellm_messages(messages),
            [t.openai_schema for t in tools] if tools else None,
            f"tau:{task_id}:{call_name}:{counts[call_name]}",
        )
        message = result["choices"][0]["message"]
        if call_name == "nl_assertions_eval":
            # Upstream accepts an empty results list as all([])==True. Reject
            # incomplete judge output instead of manufacturing a passing grade.
            expected = ast.literal_eval(
                messages[-1].content.split("expectedOutcomes:", 1)[1].strip()
            )
            judged = json.loads(message.get("content") or "null")
            rows = judged.get("results") if isinstance(judged, dict) else None
            if (
                not isinstance(rows, list)
                or any(
                    not isinstance(row, dict)
                    or type(row.get("metExpectation")) is not bool
                    or not isinstance(row.get("reasoning"), str)
                    for row in rows
                )
                or Counter(row.get("expectedOutcome") for row in rows) != Counter(expected)
            ):
                raise ValueError("Incomplete or invalid NL judge output")
        calls = [
            ToolCall(
                id=t["id"],
                name=t["function"]["name"],
                arguments=json.loads(t["function"]["arguments"]),
            )
            for t in message.get("tool_calls") or []
        ]
        return AssistantMessage(
            role="assistant",
            content=message.get("content"),
            tool_calls=calls or None,
            cost=result["usage"]["cost"],
            usage=result["usage"],
        )

    task = next(t for t in get_tasks("train") if t.id == task_id)
    env = get_environment()
    authenticated = None
    suppressed = {}

    def facts(tool, arguments):
        order = env.tools.db.orders.get(arguments.get("order_id"))
        return {
            "authenticated_user": authenticated,
            "order": order.model_dump(mode="json") if order else None,
        }

    boundary = Boundary(arm, home, retail_policy, facts)
    original_response = env.get_response

    def get_response(call):
        nonlocal authenticated
        try:
            # Use the upstream argument schema before any effect, in every arm.
            schema = {t.name: t for t in env.get_tools()}[call.name].params
            schema.model_validate(call.arguments)
            response = boundary.invoke(call.name, call.arguments, lambda: original_response(call))
        except (ValueError, KeyError) as exc:
            response = ToolMessage(
                id=call.id,
                role="tool",
                requestor=call.requestor,
                content=json.dumps(f"Error: {exc}"),
                error=True,
            )
            suppressed[call.id] = response
        if call.name.startswith("find_user_id_by_") and not response.error:
            # Upstream leaves scalar strings plain; only structured returns are JSON.
            located = response.content
            if located in env.tools.db.users and authenticated is None:
                authenticated = located
                # Binding never changes following a second lookup. Subsequent
                # profile/order access is checked against the first identity.
        return response

    env.get_response = get_response
    old_agent, old_user, old_judge = (
        agent_module.generate,
        user_module.generate,
        judge_module.generate,
    )
    agent_module.generate = user_module.generate = judge_module.generate = generate
    try:
        agent = agent_module.LLMAgent(env.get_tools(), env.get_policy(), "budgeted-openrouter")
        user = user_module.UserSimulator(
            instructions=str(task.user_scenario), llm="budgeted-openrouter"
        )
        orchestrator = Orchestrator(
            "retail", agent, user, env, task, max_steps=max_steps, max_errors=10, seed=20260928
        )
        simulation = orchestrator.run()
        (home / "trajectory.json").write_text(
            simulation.model_dump_json(indent=2), encoding="utf-8"
        )

        # Replay denied calls as denied. Gold actions remain entirely unchanged.
        # Otherwise the upstream state grader would execute actions our adapter blocked.
        def replay_environment(**kwargs):
            replay = get_environment(**kwargs)
            original = replay.get_response
            replay.get_response = lambda call: suppressed.get(call.id) or original(call)
            return replay

        original_factory = registry._domains["retail"]
        registry._domains["retail"] = replay_environment
        try:
            reward = evaluate_simulation(simulation, task, EvaluationType.ALL, False, "retail")
        finally:
            registry._domains["retail"] = original_factory
        return {
            "task_success": reward.reward == 1.0,
            "reward": reward.model_dump(mode="json"),
            "termination": simulation.termination_reason.value,
            **boundary.finish(),
        }
    finally:
        agent_module.generate, user_module.generate, judge_module.generate = (
            old_agent,
            old_user,
            old_judge,
        )
