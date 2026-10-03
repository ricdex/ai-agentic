"""
Módulo 6 — Ejemplo 5: Retrieval avanzado

El pipeline del ejemplo 02 (embedding → top-k por coseno) falla en casos
predecibles. Cada técnica de este archivo ataca uno:

| Falla del RAG básico                                  | Técnica                  |
|-------------------------------------------------------|--------------------------|
| Query con identificadores exactos (ERR_402, SKU-991)  | Hybrid search (BM25+RRF) |
| Top-k trae chunks "parecidos" pero no los que responden | Reranking              |
| Pregunta corta vs. documento largo: vectores lejanos  | HyDE                     |
| Misma pregunta 1000 veces/día → 1000 llamadas al LLM  | Semantic cache           |

Todo está en Python puro (sin numpy) y recibe las dependencias externas
(embedder, LLM) por parámetro, para poder testearlo sin red.

Requisitos:
    pip install anthropic sentence-transformers

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 05_advanced_retrieval.py
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence

import anthropic

# Modelo barato para tareas auxiliares (rerank, HyDE). Configurable.
AUX_MODEL = os.environ.get("RAG_AUX_MODEL", "claude-haiku-4-5")

Embedder = Callable[[str], Sequence[float]]

_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9_]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ---------------------------------------------------------------------------
# 1. Hybrid search: BM25 (léxico) + dense (semántico) fusionados con RRF
# ---------------------------------------------------------------------------

class BM25:
    """BM25 Okapi. Encuentra coincidencias exactas que los embeddings diluyen:
    códigos de error, nombres de funciones, SKUs, siglas."""

    def __init__(self, docs: dict[str, str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_tokens = {doc_id: tokenize(text) for doc_id, text in docs.items()}
        self.doc_len = {d: len(toks) for d, toks in self.doc_tokens.items()}
        self.avg_len = (sum(self.doc_len.values()) / len(docs)) if docs else 0.0
        self.tf = {d: Counter(toks) for d, toks in self.doc_tokens.items()}
        df = Counter()
        for toks in self.doc_tokens.values():
            df.update(set(toks))
        n = len(docs)
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        terms = tokenize(query)
        scores = {}
        for doc_id, tf in self.tf.items():
            norm = self.k1 * (1 - self.b + self.b * self.doc_len[doc_id] / (self.avg_len or 1))
            score = sum(
                self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm)
                for t in terms if t in tf
            )
            if score > 0:
                scores[doc_id] = score
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class DenseIndex:
    def __init__(self, docs: dict[str, str], embed: Embedder):
        self.embed = embed
        self.vectors = {doc_id: embed(text) for doc_id, text in docs.items()}

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        q = self.embed(query)
        scored = [(d, cosine(q, v)) for d, v in self.vectors.items()]
        return sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Fusiona rankings usando solo la POSICIÓN, no el score.

    BM25 devuelve scores 0..∞ y coseno -1..1: no se pueden sumar. RRF evita
    normalizar: score(d) = Σ 1 / (k + rank). k=60 es el valor del paper original.
    """
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    def __init__(self, docs: dict[str, str], embed: Embedder):
        self.docs = docs
        self.bm25 = BM25(docs)
        self.dense = DenseIndex(docs, embed)

    def search(self, query: str, top_k: int = 5, candidates: int = 20) -> list[tuple[str, float]]:
        lexical = [d for d, _ in self.bm25.search(query, candidates)]
        semantic = [d for d, _ in self.dense.search(query, candidates)]
        return reciprocal_rank_fusion([lexical, semantic])[:top_k]


# ---------------------------------------------------------------------------
# 2. Reranking: recuperar mucho (barato), reordenar poco (caro y preciso)
# ---------------------------------------------------------------------------

Scorer = Callable[[str, list[str]], list[float]]


def rerank(query: str, candidates: list[tuple[str, str]], scorer: Scorer,
           top_k: int = 3) -> list[tuple[str, float]]:
    """candidates: [(doc_id, texto)]. El scorer ve query y documento JUNTOS
    (como un cross-encoder), a diferencia del embedding que los codifica por
    separado. Por eso es más preciso y por eso solo se aplica a ~20 candidatos.
    """
    if not candidates:
        return []
    scores = scorer(query, [text for _, text in candidates])
    if len(scores) != len(candidates):
        # Scorer roto → no inventar un orden: mantener el de retrieval.
        return [(doc_id, 0.0) for doc_id, _ in candidates[:top_k]]
    ranked = sorted(zip((d for d, _ in candidates), scores), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def llm_scorer(client, model: str = AUX_MODEL) -> Scorer:
    """Scorer con Claude: una sola llamada puntúa todos los candidatos.

    En producción con mucho volumen, un cross-encoder local
    (sentence_transformers.CrossEncoder) es más barato y rápido.
    """
    def score(query: str, texts: list[str]) -> list[float]:
        listing = "\n\n".join(f"[{i}] {t[:1500]}" for i, t in enumerate(texts))
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=(
                "Puntuá de 0 a 10 cuánto ayuda cada documento a RESPONDER la pregunta "
                "(no solo si habla del mismo tema). Respondé solo un array JSON de "
                "números, uno por documento, en el mismo orden."
            ),
            messages=[{"role": "user", "content": f"Pregunta: {query}\n\nDocumentos:\n{listing}"}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        match = re.search(r"\[.*\]", text, re.DOTALL)
        try:
            values = json.loads(match.group(0)) if match else []
            return [float(v) for v in values]
        except (ValueError, TypeError):
            return []

    return score


# ---------------------------------------------------------------------------
# 3. HyDE: buscar con una respuesta hipotética, no con la pregunta
# ---------------------------------------------------------------------------

def hyde_query(question: str, generate: Callable[[str], str]) -> str:
    """Genera un párrafo hipotético que RESPONDERÍA la pregunta y lo usa como
    query. Un documento se parece más a otro documento que a una pregunta.

    El texto generado puede contener datos inventados: solo se usa para buscar,
    nunca se muestra ni se usa como fuente.
    """
    hypothetical = generate(question).strip()
    return f"{question}\n{hypothetical}" if hypothetical else question


def claude_generator(client, model: str = AUX_MODEL) -> Callable[[str], str]:
    def generate(question: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=300,
            system=(
                "Escribí un párrafo breve, en el estilo de documentación técnica interna, "
                "que respondería esta pregunta. No aclares que es hipotético."
            ),
            messages=[{"role": "user", "content": question}],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

    return generate


# ---------------------------------------------------------------------------
# 4. Semantic cache: no pagar dos veces por la misma pregunta
# ---------------------------------------------------------------------------

class SemanticCache:
    """Cache por similitud de la pregunta, no por string exacto.

    Riesgos que hay que diseñar, no ignorar:
    - Falso hit: "¿cómo cancelo mi plan?" vs "¿cómo cambio mi plan?" pueden
      tener similitud alta. El threshold debe ser alto (>= 0.92) y medido.
    - Fuga entre usuarios: la clave incluye un `scope` (tenant/usuario/rol).
    - Respuestas viejas: TTL obligatorio; invalidar al reindexar documentos.
    """

    def __init__(self, embed: Embedder, threshold: float = 0.92, ttl_seconds: float = 3600,
                 clock: Callable[[], float] = time.monotonic):
        self.embed = embed
        self.threshold = threshold
        self.ttl = ttl_seconds
        self.clock = clock
        self.entries: list[dict] = []
        self.hits = 0
        self.misses = 0

    def get(self, query: str, scope: str = "global") -> str | None:
        now = self.clock()
        self.entries = [e for e in self.entries if now - e["at"] < self.ttl]
        q = self.embed(query)
        best, best_sim = None, -1.0
        for e in self.entries:
            if e["scope"] != scope:
                continue
            sim = cosine(q, e["vec"])
            if sim > best_sim:
                best, best_sim = e, sim
        if best is not None and best_sim >= self.threshold:
            self.hits += 1
            return best["answer"]
        self.misses += 1
        return None

    def put(self, query: str, answer: str, scope: str = "global") -> None:
        self.entries.append({
            "scope": scope, "vec": self.embed(query), "answer": answer, "at": self.clock(),
        })

    def invalidate(self) -> None:
        """Llamar cuando se reindexan los documentos fuente."""
        self.entries.clear()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

DEMO_DOCS = {
    "pagos-errores": (
        "Cuando Stripe devuelve ERR_402 (fondos insuficientes) el sistema reintenta 3 veces "
        "con backoff exponencial y luego notifica al usuario."
    ),
    "pagos-general": (
        "El procesamiento de cobros es asíncrono: el usuario recibe confirmación inmediata "
        "y el cargo real ocurre en background."
    ),
    "deploy": "El webhook handler corre en Lambda; el agent core en ECS Fargate.",
    "secretos": "Las credenciales de producción viven en AWS Secrets Manager, nunca en el repo.",
    "redis": "Los componentes se comunican a través de colas en Redis.",
}


def _demo():  # pragma: no cover - descarga un modelo y llama a la API
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(text: str) -> list[float]:
        return model.encode(text, normalize_embeddings=True).tolist()

    client = anthropic.Anthropic()
    query = "qué pasa con ERR_402"

    print(f"Query: {query!r}\n")
    print("Solo dense :", [d for d, _ in DenseIndex(DEMO_DOCS, embed).search(query, 3)])
    print("Solo BM25  :", [d for d, _ in BM25(DEMO_DOCS).search(query, 3)])
    hybrid = HybridRetriever(DEMO_DOCS, embed)
    print("Hybrid RRF :", [d for d, _ in hybrid.search(query, 3)])

    question = "¿Dónde se guardan las API keys de prod?"
    candidates = [(d, DEMO_DOCS[d]) for d, _ in hybrid.search(question, 5)]
    print(f"\nRerank para {question!r}:")
    for doc_id, score in rerank(question, candidates, llm_scorer(client)):
        print(f"  {score:4.1f}  {doc_id}")

    print("\nHyDE query:")
    print(" ", hyde_query(question, claude_generator(client)).replace("\n", "\n  "))

    cache = SemanticCache(embed, threshold=0.85)
    cache.put("¿Dónde se guardan los secretos?", "En AWS Secrets Manager.")
    for q in ("¿Dónde se almacenan los secretos?", "¿Cómo se despliega el webhook?"):
        print(f"\ncache.get({q!r}) → {cache.get(q)}")
    print(f"hits={cache.hits} misses={cache.misses}")


if __name__ == "__main__":  # pragma: no cover
    _demo()
