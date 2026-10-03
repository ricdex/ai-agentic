import importlib
import json
from types import SimpleNamespace

rag = importlib.import_module("06_agentic_rag")

DOCS = {"pagos": "ERR_402 → 3 reintentos", "deploy": "corre en ECS"}


class FakeRetriever:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def search(self, query, top_k=3):
        self.calls.append((query, top_k))
        return [(d, 1.0) for d in self.mapping.get(query, [])][:top_k]


def tool_use(id_, query):
    return SimpleNamespace(type="tool_use", id=id_, input={"query": query})


def reply(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def text(t):
    return SimpleNamespace(type="text", text=t)


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_answers_without_searching_when_model_does_not_need_to():
    client = ScriptedClient([reply("end_turn", text("No está en la documentación."))])
    r = rag.answer(client, FakeRetriever({}), DOCS, "¿qué DB usamos?")
    assert r.answer == "No está en la documentación."
    assert r.queries == [] and r.stop == "end_turn"
    assert client.calls[0]["tools"] == [rag.SEARCH_TOOL]


def test_decomposes_into_parallel_searches_and_collects_sources():
    retriever = FakeRetriever({"ERR_402": ["pagos"], "dónde corre": ["deploy"]})
    client = ScriptedClient([
        reply("tool_use", tool_use("t1", "ERR_402"), tool_use("t2", "dónde corre")),
        reply("end_turn", text("Reintenta 3 veces [pagos] y corre en ECS [deploy].")),
    ])
    r = rag.answer(client, retriever, DOCS, "pregunta compuesta")
    assert r.queries == ["ERR_402", "dónde corre"]
    assert r.sources == {"pagos", "deploy"}
    # Los dos tool_result vuelven en UN solo mensaje de usuario.
    tool_msg = client.calls[1]["messages"][2]
    assert tool_msg["role"] == "user"
    assert [b["tool_use_id"] for b in tool_msg["content"]] == ["t1", "t2"]
    assert json.loads(tool_msg["content"][0]["content"])[0]["id"] == "pagos"


def test_search_limit_returns_error_result_and_keeps_tools():
    retriever = FakeRetriever({"q": ["pagos"]})
    client = ScriptedClient([
        reply("tool_use", tool_use("t1", "q")),
        reply("tool_use", tool_use("t2", "q")),
        reply("end_turn", text("respuesta parcial")),
    ])
    r = rag.answer(client, retriever, DOCS, "x", max_searches=1)
    assert r.queries == ["q"]
    limited = client.calls[2]["messages"][4]["content"][0]  # user msg con tool_result de t2
    assert limited["is_error"] is True
    assert all(c["tools"] == [rag.SEARCH_TOOL] for c in client.calls)
    assert r.answer == "respuesta parcial"


def test_gives_up_after_hard_turn_limit():
    client = ScriptedClient([reply("tool_use", tool_use(f"t{i}", "q")) for i in range(3)])
    r = rag.answer(client, FakeRetriever({}), DOCS, "x", max_searches=1)
    assert r.stop == "max_searches"


def test_execute_search_validates_input():
    retriever = FakeRetriever({"q": ["pagos", "deploy"]})
    payload, ids = rag.execute_search(retriever, DOCS, {"query": "  "})
    assert "error" in json.loads(payload) and ids == []
    _, ids = rag.execute_search(retriever, DOCS, {"query": "q", "top_k": 99})
    assert retriever.calls[-1] == ("q", 5)
    assert ids == ["pagos", "deploy"]
