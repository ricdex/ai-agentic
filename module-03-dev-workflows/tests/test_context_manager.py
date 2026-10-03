from types import SimpleNamespace

import pytest

import context_manager as cm


class FakeMessages:
    def __init__(self, text="ok"):
        self.calls = []
        self.text = text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


class FakeClient:
    def __init__(self):
        self.messages = FakeMessages()
        self.beta = SimpleNamespace(messages=FakeMessages())


# --- estimate_tokens / truncate_tool_output --------------------------------

def test_estimate_tokens_string_and_structure():
    assert cm.estimate_tokens("") == 0
    assert cm.estimate_tokens("a" * 400) == 100
    assert cm.estimate_tokens([{"role": "user", "content": "x" * 400}]) > 100


def test_truncate_keeps_short_text_untouched():
    assert cm.truncate_tool_output("hola", max_chars=500) == "hola"


def test_truncate_keeps_head_and_tail_within_budget():
    log = "START\n" + "ruido\n" * 5000 + "FAIL: assertion error\n"
    out = cm.truncate_tool_output(log, max_chars=1000)
    assert len(out) <= 1000
    assert out.startswith("START")
    assert "FAIL: assertion error" in out
    assert "caracteres omitidos" in out


def test_truncate_rejects_tiny_budget():
    with pytest.raises(ValueError):
        cm.truncate_tool_output("x" * 1000, max_chars=50)


# --- order_for_attention ----------------------------------------------------

@pytest.mark.parametrize("items, expected", [
    ([], []),
    ([1], [1]),
    ([1, 2], [1, 2]),
    ([1, 2, 3, 4, 5], [1, 3, 5, 4, 2]),
])
def test_order_for_attention_puts_best_at_edges(items, expected):
    assert cm.order_for_attention(items) == expected


# --- ContextPolicy ----------------------------------------------------------

@pytest.mark.parametrize("used, action", [
    (10_000, "ok"),
    (80_000, "clear_tool_results"),
    (140_000, "compact"),
    (180_000, "handoff"),
])
def test_policy_thresholds(used, action):
    assert cm.ContextPolicy(window_tokens=200_000).decide(used) == action


def test_policy_rejects_unordered_thresholds():
    with pytest.raises(ValueError):
        cm.ContextPolicy(clear_at=0.8, compact_at=0.5)


def test_context_management_mapping():
    assert cm.context_management_for("ok") == {}
    clear = cm.context_management_for("clear_tool_results")
    assert clear["betas"] == [cm.CONTEXT_EDITING_BETA]
    assert clear["context_management"]["edits"][0]["type"] == "clear_tool_uses_20250919"
    compact = cm.context_management_for("compact")
    assert compact["betas"] == [cm.COMPACTION_BETA]
    assert compact["context_management"]["edits"][0]["type"] == "compact_20260112"


# --- TaskState --------------------------------------------------------------

def test_handoff_contains_all_sections():
    state = cm.TaskState(goal="g", done=["a"], decisions=["usar Decimal"])
    note = state.to_handoff()
    assert "**Objetivo:** g" in note
    assert "- a" in note
    assert "- usar Decimal" in note
    assert "## Pendiente (en orden)\n- (nada)" in note


# --- run_turn ---------------------------------------------------------------

def test_run_turn_ok_uses_plain_endpoint_and_appends_full_content():
    client = FakeClient()
    messages = [{"role": "user", "content": "hola"}]
    response, action = cm.run_turn(client, messages, cm.ContextPolicy(), tools=[{"name": "t"}])
    assert action == "ok"
    assert len(client.messages.calls) == 1 and not client.beta.messages.calls
    assert client.messages.calls[0]["tools"] == [{"name": "t"}]
    assert messages[-1] == {"role": "assistant", "content": response.content}


def test_run_turn_uses_beta_when_context_is_large():
    client = FakeClient()
    policy = cm.ContextPolicy(window_tokens=1_000)
    messages = [{"role": "user", "content": "x" * 2_000}]  # ~500 tokens → 50%
    _, action = cm.run_turn(client, messages, policy)
    assert action == "clear_tool_results"
    call = client.beta.messages.calls[0]
    assert call["betas"] == [cm.CONTEXT_EDITING_BETA]
    assert "tools" not in call


def test_run_turn_handoff_does_not_call_model():
    client = FakeClient()
    policy = cm.ContextPolicy(window_tokens=100)
    response, action = cm.run_turn(client, [{"role": "user", "content": "x" * 4_000}], policy)
    assert (response, action) == (None, "handoff")
    assert not client.messages.calls and not client.beta.messages.calls
