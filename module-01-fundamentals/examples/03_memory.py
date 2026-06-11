"""
Módulo 1 — Ejemplo 3: Tipos de memoria en agentes

Demuestra tres estrategias de memoria:
1. In-context (conversación continua — efímera)
2. External (SQLite — persiste entre sesiones)
3. Episodic (aprende de errores pasados)

Caso de uso: agente de debugging que recuerda qué falló antes
para no repetir los mismos errores.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 03_memory.py
"""

import sqlite3
import json
import datetime
import anthropic
from pathlib import Path

client = anthropic.Anthropic()
DB_PATH = "/tmp/agent_memory.db"


# --- Capa de memoria externa (SQLite) ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            approach TEXT NOT NULL,
            outcome TEXT NOT NULL,  -- 'success' | 'failure'
            error_msg TEXT,
            lesson TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_episode(task: str, approach: str, outcome: str, error_msg: str = None, lesson: str = None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO episodes (task, approach, outcome, error_msg, lesson) VALUES (?, ?, ?, ?, ?)",
        (task, approach, outcome, error_msg, lesson)
    )
    conn.commit()
    conn.close()


def get_relevant_episodes(task: str, limit: int = 3) -> list[dict]:
    """Recupera episodios similares a la tarea actual (búsqueda simple por keywords)."""
    conn = sqlite3.connect(DB_PATH)
    words = task.lower().split()[:3]
    like_clauses = " OR ".join(f"LOWER(task) LIKE ?" for _ in words)
    params = [f"%{w}%" for w in words]

    rows = conn.execute(
        f"""
        SELECT task, approach, outcome, error_msg, lesson, created_at
        FROM episodes
        WHERE {like_clauses}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        params + [limit]
    ).fetchall()
    conn.close()

    return [
        {
            "task": r[0],
            "approach": r[1],
            "outcome": r[2],
            "error_msg": r[3],
            "lesson": r[4],
            "when": r[5]
        }
        for r in rows
    ]


# --- Agente con memoria ---

TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Escribe contenido en un archivo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    if name == "read_file":
        try:
            return Path(inputs["path"]).read_text()
        except Exception as e:
            return f"ERROR: {e}"
    elif name == "write_file":
        try:
            Path(inputs["path"]).write_text(inputs["content"])
            return "Archivo escrito exitosamente"
        except Exception as e:
            return f"ERROR: {e}"
    return f"ERROR: herramienta desconocida {name}"


def build_memory_context(task: str) -> str:
    """Construye el contexto de memoria episódica para el system prompt."""
    episodes = get_relevant_episodes(task)
    if not episodes:
        return ""

    lines = ["## Memoria de episodios anteriores\n"]
    lines.append("Basándote en tareas similares anteriores, considerá estas lecciones:\n")

    for ep in episodes:
        lines.append(f"- **Tarea:** {ep['task'][:80]}")
        lines.append(f"  **Resultado:** {ep['outcome']}")
        if ep['error_msg']:
            lines.append(f"  **Error:** {ep['error_msg'][:100]}")
        if ep['lesson']:
            lines.append(f"  **Lección aprendida:** {ep['lesson']}")
        lines.append("")

    return "\n".join(lines)


def run_agent_with_memory(task: str) -> tuple[str, str]:
    """
    Corre el agente con memoria episódica.
    Retorna (respuesta, outcome) donde outcome es 'success' o 'failure'.
    """
    memory_context = build_memory_context(task)

    system = f"""Sos un agente de debugging con memoria de episodios pasados.

{memory_context}

Cuando terminés, reflexioná sobre:
1. ¿Qué approach usaste?
2. ¿Funcionó? ¿Por qué?
3. ¿Qué lección sacarías para la próxima vez?
"""

    messages = [{"role": "user", "content": task}]
    approach_notes = []

    print(f"\n[Agente con Memoria] {task}")
    if memory_context:
        print("[Memoria] Encontré episodios relevantes — informando decisiones")
    print("-" * 50)

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=TOOLS,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            print(f"\n[Respuesta]\n{text}")
            return text, "success"

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    approach_notes.append(f"{block.name}: {block.input}")
                    result = execute_tool(block.name, block.input)
                    print(f"  → {block.name}({list(block.input.values())[0][:40] if block.input else ''})")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

    return "Límite de iteraciones", "failure"


# --- Demo ---

if __name__ == "__main__":
    init_db()

    # Simulamos un problema con un archivo
    Path("/tmp/config.json").write_text('{"debug": true, "max_retries": 3}')

    # Primera vez: el agente no tiene memoria previa
    response1, outcome1 = run_agent_with_memory(
        "Lee el archivo /tmp/config.json y dime su contenido"
    )
    save_episode(
        task="Leer y analizar archivo de configuración JSON",
        approach="Leer el archivo directamente con read_file",
        outcome=outcome1,
        lesson="read_file funciona bien para archivos JSON pequeños"
    )

    print("\n" + "=" * 60)
    print("Segunda ejecución — ahora el agente tiene memoria del episodio anterior")
    print("=" * 60)

    # Segunda vez: el agente recuerda el episodio anterior
    response2, outcome2 = run_agent_with_memory(
        "Necesito ver la configuración en /tmp/config.json"
    )

    print(f"\n[Memoria guardada en: {DB_PATH}]")
    print("En una app real, esta memoria persistiría entre reinicios del agente.")
