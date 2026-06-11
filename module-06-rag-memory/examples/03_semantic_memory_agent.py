"""
Módulo 6 — Ejemplo 3: Agente con memoria episódica semántica

Reemplaza la memoria keyword-based del módulo 1 con búsqueda semántica.
El agente ahora encuentra episodios relevantes aunque no compartan palabras exactas.

Diferencia clave vs módulo 1:
- Módulo 1: busca episodios por keywords (LIKE '%pago%')
- Este módulo: busca por significado (similitud coseno de embeddings)

Requisitos:
    pip install anthropic sentence-transformers numpy

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 03_semantic_memory_agent.py
"""

import sqlite3
import numpy as np
import anthropic
from sentence_transformers import SentenceTransformer

EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
DB_PATH = "/tmp/semantic_memory.db"
SIMILARITY_THRESHOLD = 0.6

client = anthropic.Anthropic()


def embed(text: str) -> np.ndarray:
    return EMBED_MODEL.encode(text, normalize_embeddings=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            outcome TEXT NOT NULL,
            lesson TEXT,
            embedding BLOB NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_episode(task: str, outcome: str, lesson: str):
    vec = embed(task)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO episodes (task, outcome, lesson, embedding) VALUES (?, ?, ?, ?)",
        (task, outcome, lesson, vec.tobytes())
    )
    conn.commit()
    conn.close()


def find_similar_episodes(task: str, top_k: int = 3) -> list[dict]:
    query_vec = embed(task)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT task, outcome, lesson, embedding FROM episodes").fetchall()
    conn.close()

    if not rows:
        return []

    scored = []
    for task_stored, outcome, lesson, emb_bytes in rows:
        stored_vec = np.frombuffer(emb_bytes, dtype=np.float32)
        sim = float(np.dot(query_vec, stored_vec))
        if sim >= SIMILARITY_THRESHOLD:
            scored.append({
                "task": task_stored,
                "outcome": outcome,
                "lesson": lesson,
                "similarity": sim
            })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]


def build_memory_context(task: str) -> str:
    episodes = find_similar_episodes(task)
    if not episodes:
        return ""

    lines = ["## Episodios similares en memoria\n"]
    for ep in episodes:
        lines.append(f"- **Similitud:** {ep['similarity']:.2f} | **Tarea:** {ep['task']}")
        lines.append(f"  **Resultado:** {ep['outcome']}")
        if ep["lesson"]:
            lines.append(f"  **Lección:** {ep['lesson']}")
        lines.append("")

    return "\n".join(lines)


TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    if name == "read_file":
        try:
            from pathlib import Path
            return Path(inputs["path"]).read_text()
        except Exception as e:
            return f"ERROR: {e}"
    return f"ERROR: herramienta desconocida {name}"


def run_agent(task: str) -> tuple[str, str]:
    memory_context = build_memory_context(task)

    similar_count = len(find_similar_episodes(task))
    if similar_count:
        print(f"  [Memoria] {similar_count} episodio(s) similar(es) encontrado(s)")
    else:
        print(f"  [Memoria] No hay episodios previos relevantes")

    system = f"""Sos un agente de ingeniería con memoria semántica de experiencias pasadas.

{memory_context}

Usá los episodios relevantes para informar tu approach. Si encontraste lecciones
que aplican a esta tarea, aplicalas — no repitas los mismos errores."""

    messages = [{"role": "user", "content": task}]

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            return text, "success"

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    print(f"  → {block.name}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "user", "content": tool_results})

    return "Límite de iteraciones alcanzado", "failure"


if __name__ == "__main__":
    init_db()

    # Poblar memoria con episodios pasados
    print("[Poblando memoria con episodios históricos...]")
    save_episode(
        task="El webhook de Stripe falla con error 400 al recibir eventos de pago",
        outcome="success",
        lesson="Stripe requiere que valides la firma HMAC antes de parsear el body. "
               "Usar request.body raw, no el body parseado por el framework."
    )
    save_episode(
        task="El agente no puede leer archivos fuera del directorio de trabajo",
        outcome="success",
        lesson="Agregar validación de path traversal con os.path.realpath antes de leer archivos."
    )
    save_episode(
        task="Los tests de integración fallan en CI pero pasan localmente",
        outcome="success",
        lesson="El problema era variables de entorno no seteadas en CI. "
               "Agregar .env.example con todas las variables necesarias."
    )

    print(f"  3 episodios guardados\n")

    # Tarea nueva — comparte significado con episodios anteriores pero no keywords exactas
    tasks = [
        "cobro rechazado con error al procesar evento de pago externo",   # similar al episodio 1
        "pipeline de CD falla: vars de entorno no encontradas en el runner",  # similar al episodio 3
        "implementar endpoint de health check para el webhook handler",  # nuevo, sin memoria
    ]

    for task in tasks:
        print(f"\nTarea: {task}")
        print("-" * 60)
        response, outcome = run_agent(task)
        print(f"Respuesta: {response[:300]}{'...' if len(response) > 300 else ''}")
        print(f"Outcome: {outcome}")
