"""
Módulo 6 — Ejemplo 6: Agentic RAG

En el RAG clásico el CÓDIGO decide: siempre busca una vez, con la pregunta
literal, y pasa el top-k al modelo. En agentic RAG el MODELO decide:

- si necesita buscar o ya puede responder,
- con qué query (reformula, descompone preguntas compuestas),
- si lo que encontró alcanza o tiene que buscar otra vez,
- cuándo parar y decir "no está en la documentación".

Es el loop de agente del módulo 1 con una sola herramienta: `search_docs`.
Más flexible y más caro: usalo cuando las preguntas son compuestas o ambiguas;
para preguntas directas el RAG del ejemplo 02 alcanza.

Requisitos:
    pip install anthropic sentence-transformers

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 06_agentic_rag.py
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field

import anthropic

retrieval = importlib.import_module("05_advanced_retrieval")

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5-5")
MAX_SEARCHES = int(os.environ.get("RAG_MAX_SEARCHES", "4"))

SYSTEM = (
    "Respondés preguntas sobre la documentación interna usando la herramienta search_docs. "
    "Si la pregunta tiene varias partes, buscá cada parte por separado. "
    "Si un resultado no responde, reformulá la búsqueda con otros términos. "
    "Respondé SOLO con información de los resultados y citá el id entre corchetes. "
    "Si después de buscar no encontrás la respuesta, decí que no está en la documentación."
)

SEARCH_TOOL = {
    "name": "search_docs",
    "description": (
        "Busca en la documentación interna (búsqueda híbrida: palabras exactas + significado). "
        "Devuelve hasta top_k fragmentos con su id. Usá queries cortas y específicas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Qué buscar"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


@dataclass
class RagResult:
    answer: str
    queries: list[str] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    stop: str = "end_turn"


def execute_search(retriever, docs: dict[str, str], tool_input: dict) -> tuple[str, list[str]]:
    query = str(tool_input.get("query", "")).strip()
    if not query:
        return json.dumps({"error": "query vacía"}), []
    top_k = max(1, min(int(tool_input.get("top_k", 3)), 5))
    hits = retriever.search(query, top_k=top_k)
    results = [{"id": doc_id, "text": docs[doc_id]} for doc_id, _ in hits]
    return json.dumps(results, ensure_ascii=False), [r["id"] for r in results]


def answer(client, retriever, docs: dict[str, str], question: str,
           max_searches: int = MAX_SEARCHES) -> RagResult:
    messages = [{"role": "user", "content": question}]
    result = RagResult(answer="")

    # Cota dura de turnos: las búsquedas permitidas + un turno para responder + margen.
    for _ in range(max_searches + 2):
        response = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM, tools=[SEARCH_TOOL], messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            result.answer = "".join(b.text for b in response.content if b.type == "text")
            result.stop = response.stop_reason
            return result

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if len(result.queries) >= max_searches:
                # No quitar la tool: el historial ya tiene tool_use y el API exige `tools`.
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id, "is_error": True,
                    "content": "Límite de búsquedas alcanzado. Respondé con lo que ya encontraste.",
                })
                continue
            payload, ids = execute_search(retriever, docs, block.input)
            result.queries.append(str(block.input.get("query", "")))
            result.sources.update(ids)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": payload})
        messages.append({"role": "user", "content": tool_results})

    result.stop = "max_searches"
    result.answer = "No pude completar la respuesta dentro del límite de búsquedas."
    return result


def _demo():  # pragma: no cover - llama a la API real
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(text: str) -> list[float]:
        return model.encode(text, normalize_embeddings=True).tolist()

    docs = retrieval.DEMO_DOCS
    retriever = retrieval.HybridRetriever(docs, embed)
    client = anthropic.Anthropic()

    for question in (
        "¿Qué pasa si un cobro falla con ERR_402 y dónde corre el servicio que lo procesa?",
        "¿Qué base de datos relacional usamos?",
    ):
        r = answer(client, retriever, docs, question)
        print(f"Q: {question}")
        print(f"   búsquedas: {r.queries}")
        print(f"   fuentes:   {sorted(r.sources)}")
        print(f"A: {r.answer}\n")


if __name__ == "__main__":  # pragma: no cover
    _demo()
