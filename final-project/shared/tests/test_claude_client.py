from types import SimpleNamespace
from unittest.mock import patch

from shared import claude_client


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, tool_input, block_id="tool_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_model_aliases_resolve_to_known_claude_ids():
    assert claude_client.MODELS["fast"].startswith("claude-haiku")
    assert claude_client.MODELS["standard"].startswith("claude-sonnet")
    assert claude_client.MODELS["powerful"].startswith("claude-opus")


def test_run_agent_stops_on_end_turn_and_returns_final_text():
    response = _response([_text_block("Listo.")], "end_turn")

    with patch.object(claude_client.client.messages, "create", return_value=response):
        final_text, history = claude_client.run_agent(
            system="sos un agente de prueba",
            tools=[],
            messages=[{"role": "user", "content": "hola"}],
        )

    assert final_text == "Listo."
    assert history[-1]["role"] == "assistant"


def test_run_agent_executes_tool_calls_and_continues_loop():
    tool_call = _response(
        [_tool_use_block("read_file", {"path": "a.py"})], "tool_use"
    )
    final = _response([_text_block("Analizado.")], "end_turn")

    calls = []

    def tool_handler(name, tool_input):
        calls.append((name, tool_input))
        return "contenido del archivo"

    with patch.object(
        claude_client.client.messages, "create", side_effect=[tool_call, final]
    ):
        final_text, history = claude_client.run_agent(
            system="sos un agente de prueba",
            tools=[{"name": "read_file"}],
            messages=[{"role": "user", "content": "leé a.py"}],
            tool_handler=tool_handler,
        )

    assert final_text == "Analizado."
    assert calls == [("read_file", {"path": "a.py"})]
    # history: [user original, assistant tool_use, user tool_result, assistant final]
    tool_result_message = history[2]
    assert tool_result_message["role"] == "user"
    assert tool_result_message["content"][0]["content"] == "contenido del archivo"


def test_run_agent_stops_when_task_complete_tool_is_called():
    tool_call = _response(
        [_tool_use_block("task_complete", {"summary": "done"})], "tool_use"
    )

    completions = []

    def tool_handler(name, tool_input):
        completions.append((name, tool_input))
        return "ignored"

    with patch.object(
        claude_client.client.messages, "create", return_value=tool_call
    ) as mock_create:
        claude_client.run_agent(
            system="sos un agente de prueba",
            tools=[{"name": "task_complete"}],
            messages=[{"role": "user", "content": "hacé la tarea"}],
            tool_handler=tool_handler,
        )
        # task_complete detiene el loop: la única llamada al modelo fue la primera.
        assert mock_create.call_count == 1

    assert completions == [("task_complete", {"summary": "done"})]


def test_run_agent_respects_max_iterations_without_hanging():
    tool_call = _response([_tool_use_block("noop", {})], "tool_use")

    with patch.object(
        claude_client.client.messages, "create", return_value=tool_call
    ) as mock_create:
        claude_client.run_agent(
            system="sos un agente de prueba",
            tools=[{"name": "noop"}],
            messages=[{"role": "user", "content": "loop"}],
            max_iterations=3,
            tool_handler=lambda name, inp: "ok",
        )
        assert mock_create.call_count == 3
