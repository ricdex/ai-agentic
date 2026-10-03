import importlib
from types import SimpleNamespace

import pytest

ar = importlib.import_module("05_advanced_retrieval")


def bow_embed(text):
    """Embedder determinista para tests: bolsa de palabras sobre un vocabulario fijo."""
    vocab = ["pago", "cobro", "falla", "error", "secretos", "credenciales", "deploy", "lambda"]
    tokens = ar.tokenize(text)
    synonyms = {"cobro": "pago", "credenciales": "secretos"}
    normalized = [synonyms.get(t, t) for t in tokens]
    return [float(normalized.count(v)) for v in vocab]


DOCS = {
    "a": "El pago falla con ERR_402 y se reintenta",
    "b": "El cobro es asíncrono",
    "c": "Las credenciales viven en Secrets Manager",
    "d": "deploy en lambda",
}


def text_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self, text):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self._text = text

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return text_response(self._text)


# --- BM25 -------------------------------------------------------------------

def test_tokenize_lowercases_and_keeps_identifiers():
    assert ar.tokenize("Error ERR_402 en Pagos") == ["error", "err_402", "en", "pagos"]


def test_bm25_finds_exact_identifier():
    results = ar.BM25(DOCS).search("ERR_402")
    assert results[0][0] == "a"
    assert len(results) == 1


def test_bm25_no_match_and_empty_corpus():
    assert ar.BM25(DOCS).search("kubernetes") == []
    assert ar.BM25({}).search("x") == []


# --- dense / RRF / hybrid ---------------------------------------------------

def test_cosine_handles_zero_vectors():
    assert ar.cosine([0, 0], [1, 1]) == 0.0
    assert ar.cosine([1, 0], [1, 0]) == pytest.approx(1.0)


def test_dense_index_finds_synonyms():
    top = ar.DenseIndex(DOCS, bow_embed).search("dónde están los secretos", top_k=1)
    assert top[0][0] == "c"


def test_rrf_rewards_documents_ranked_by_both():
    fused = ar.reciprocal_rank_fusion([["x", "y", "z"], ["y", "x", "w"]])
    ids = [d for d, _ in fused]
    assert set(ids[:2]) == {"x", "y"}
    assert ids[-1] in {"z", "w"}


def test_hybrid_combines_lexical_and_semantic():
    hybrid = ar.HybridRetriever(DOCS, bow_embed)
    # BM25 solo ve "a" (pago + ERR_402); el dense además trae "b" ("cobro" ≈ "pago").
    ids = [d for d, _ in hybrid.search("pago ERR_402", top_k=2)]
    assert ids[0] == "a"
    assert "b" in ids


# --- rerank -----------------------------------------------------------------

def test_rerank_orders_by_scorer():
    cands = [("a", "x"), ("b", "y"), ("c", "z")]
    ranked = ar.rerank("q", cands, lambda q, texts: [1, 9, 5], top_k=2)
    assert ranked == [("b", 9), ("c", 5)]


def test_rerank_keeps_retrieval_order_when_scorer_fails():
    cands = [("a", "x"), ("b", "y")]
    assert ar.rerank("q", cands, lambda q, t: [], top_k=1) == [("a", 0.0)]
    assert ar.rerank("q", [], lambda q, t: [1]) == []


def test_llm_scorer_parses_json_array():
    client = FakeClient("Puntajes: [2, 8.5]")
    scores = ar.llm_scorer(client)("q", ["doc1", "doc2"])
    assert scores == [2.0, 8.5]
    assert client.calls[0]["model"] == ar.AUX_MODEL


@pytest.mark.parametrize("raw", ["sin json", '["a", "b"]'])
def test_llm_scorer_returns_empty_on_bad_output(raw):
    assert ar.llm_scorer(FakeClient(raw))("q", ["d"]) == []


# --- HyDE -------------------------------------------------------------------

def test_hyde_appends_hypothetical_answer():
    assert ar.hyde_query("¿dónde?", lambda q: " En Secrets Manager. ") == "¿dónde?\nEn Secrets Manager."
    assert ar.hyde_query("¿dónde?", lambda q: "  ") == "¿dónde?"


def test_claude_generator_returns_text():
    gen = ar.claude_generator(FakeClient("párrafo"))
    assert gen("q") == "párrafo"


# --- SemanticCache ----------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_cache_hit_on_paraphrase_and_miss_on_other_topic():
    cache = ar.SemanticCache(bow_embed, threshold=0.9)
    cache.put("¿dónde están los secretos?", "Secrets Manager")
    assert cache.get("¿dónde se guardan las credenciales?") == "Secrets Manager"
    assert cache.get("¿cómo hago deploy?") is None
    assert (cache.hits, cache.misses) == (1, 1)


def test_cache_is_scoped_per_tenant():
    cache = ar.SemanticCache(bow_embed)
    cache.put("secretos", "respuesta de A", scope="tenant-a")
    assert cache.get("secretos", scope="tenant-b") is None
    assert cache.get("secretos", scope="tenant-a") == "respuesta de A"


def test_cache_expires_and_invalidates():
    clock = Clock()
    cache = ar.SemanticCache(bow_embed, ttl_seconds=10, clock=clock)
    cache.put("secretos", "x")
    clock.now = 11
    assert cache.get("secretos") is None
    cache.put("secretos", "y")
    cache.invalidate()
    assert cache.get("secretos") is None
