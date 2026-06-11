"""
Módulo 6 — Ejemplo 2: Pipeline RAG completo

Implementa un sistema RAG que:
1. Indexa documentos técnicos (README, docs, código)
2. Responde preguntas usando solo el contenido indexado
3. Cita las fuentes que usó

Stack:
- Embeddings: sentence-transformers (local)
- Vector store: SQLite + numpy (sin dependencias externas)
- LLM: Claude Sonnet

Requisitos:
    pip install anthropic sentence-transformers numpy

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 02_rag_pipeline.py
"""

import json
import sqlite3
import textwrap
import numpy as np
import anthropic
from pathlib import Path
from sentence_transformers import SentenceTransformer

EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
DB_PATH = "/tmp/rag_demo.db"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
TOP_K = 3

client = anthropic.Anthropic()


# --- Vector store sobre SQLite ---

def init_store():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def embed(text: str) -> np.ndarray:
    return EMBED_MODEL.encode(text, normalize_embeddings=True)


def store_chunk(source: str, content: str):
    vec = embed(content)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO chunks (source, content, embedding) VALUES (?, ?, ?)",
        (source, content, vec.tobytes())
    )
    conn.commit()
    conn.close()


def search(query: str, top_k: int = TOP_K) -> list[dict]:
    query_vec = embed(query)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT source, content, embedding FROM chunks").fetchall()
    conn.close()

    if not rows:
        return []

    scored = []
    for source, content, emb_bytes in rows:
        stored_vec = np.frombuffer(emb_bytes, dtype=np.float32)
        sim = float(np.dot(query_vec, stored_vec))
        scored.append({"source": source, "content": content, "score": sim})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# --- Chunking ---

def chunk_text(text: str, source: str) -> list[tuple[str, str]]:
    """Divide texto en chunks con overlap."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + CHUNK_SIZE]
        chunks.append((source, " ".join(chunk_words)))
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# --- RAG ---

def index_documents(docs: dict[str, str]):
    """Indexa un dict {nombre: contenido}."""
    print("[Indexando documentos...]")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM chunks")  # re-index
    conn.commit()
    conn.close()

    total = 0
    for name, content in docs.items():
        for source, chunk in chunk_text(content, name):
            store_chunk(source, chunk)
            total += 1
    print(f"  {total} chunks indexados de {len(docs)} documentos\n")


def answer(question: str) -> str:
    """Responde una pregunta usando RAG."""
    results = search(question)

    if not results:
        return "No encontré información relevante en los documentos indexados."

    context_parts = []
    for r in results:
        context_parts.append(f"[{r['source']}] (relevancia: {r['score']:.2f})\n{r['content']}")

    context = "\n\n---\n\n".join(context_parts)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "Respondé SOLO basándote en el contexto provisto. "
            "Si la información no está en el contexto, decí explícitamente que no encontraste esa información. "
            "Citá la fuente entre corchetes al final de cada afirmación relevante."
        ),
        messages=[{
            "role": "user",
            "content": f"Contexto:\n{context}\n\nPregunta: {question}"
        }]
    )
    return response.content[0].text


# --- Demo ---

DEMO_DOCS = {
    "arquitectura.md": """
    # Arquitectura del sistema

    El sistema usa una arquitectura de microservicios con tres componentes principales:
    el webhook handler en TypeScript que recibe eventos de GitHub,
    el agent core en Python que procesa los issues usando Claude,
    y el test runner en Go que ejecuta los tests de forma aislada.

    La comunicación entre componentes se hace via Redis como cola de mensajes.
    Esto permite escalar cada componente independientemente.
    """,

    "pagos.md": """
    # Módulo de pagos

    El procesamiento de pagos usa Stripe como proveedor principal.
    Los pagos se procesan de forma asíncrona: el usuario recibe confirmación inmediata
    y el cobro real ocurre en background.

    Manejo de errores: si Stripe retorna error 402, el sistema reintenta 3 veces
    con backoff exponencial. Si falla después de 3 intentos, notifica al usuario
    y guarda el intento fallido en la tabla payment_attempts.

    Los webhooks de Stripe se validan con firma HMAC antes de procesar.
    """,

    "deployment.md": """
    # Deployment

    El sistema se despliega en AWS. El webhook handler corre en Lambda detrás de API Gateway.
    El agent core corre como worker en ECS Fargate.
    El test runner corre en Lambda con 3GB de memoria para correr pytest sin problemas.

    Las variables de entorno se almacenan en AWS Secrets Manager.
    El deployment se hace con GitHub Actions: push a main dispara el pipeline de CD.
    No hay deployment manual a producción.
    """
}


if __name__ == "__main__":
    init_store()
    index_documents(DEMO_DOCS)

    questions = [
        "¿Cómo se comunican los componentes entre sí?",
        "¿Qué pasa cuando falla un pago?",
        "¿Dónde se almacenan los secretos de producción?",
        "¿Qué base de datos usa el sistema?",  # no está en los docs
    ]

    for q in questions:
        print(f"Q: {q}")
        print(f"A: {answer(q)}")
        print("-" * 60)
        print()
