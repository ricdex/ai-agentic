# Módulo 1 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Hello Agent (ReAct loop mínimo)

**Archivo:** `examples/01_hello_agent.py`

El agente más simple posible: recibe una pregunta sobre un directorio, puede leer archivos y listar contenido, y responde sin inventar.

```python
import anthropic
import os

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "list_files",
        "description": "Lista los archivos de un directorio",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Ruta del directorio"}
            },
            "required": ["directory"]
        }
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del archivo"}
            },
            "required": ["path"]
        }
    }
]

SYSTEM = """Respondé preguntas sobre el código que encontrás en el directorio.
Usá las herramientas para buscar la información.
Si no encontrás lo que buscás, decí explícitamente qué buscaste y que no existe.
NUNCA inventes código o funciones que no leíste."""

def execute_tool(name: str, input: dict) -> str:
    if name == "list_files":
        try:
            files = os.listdir(input["directory"])
            return "\n".join(files) if files else "(directorio vacío)"
        except FileNotFoundError:
            return f"Error: directorio '{input['directory']}' no existe"
    elif name == "read_file":
        try:
            with open(input["path"]) as f:
                return f.read()
        except FileNotFoundError:
            return f"Error: archivo '{input['path']}' no existe"

def run_agent(question: str, directory: str) -> str:
    messages = [{"role": "user", "content": f"Directorio: {directory}\n\nPregunta: {question}"}]
    iterations = 0

    while iterations < 5:
        iterations += 1
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            return response.content[0].text

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool] {block.name}({block.input})")
                    result = execute_tool(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "user", "content": results})

    return "Límite de iteraciones alcanzado sin respuesta."

# Casos de prueba
questions = [
    "¿Dónde está definida la función calculate_tax?",
    "¿Qué archivos hay en el directorio src/?",
    "¿Existe una función llamada send_invoice?"
]

for q in questions:
    print(f"\nPregunta: {q}")
    answer = run_agent(q, "./sample_project")
    print(f"Respuesta: {answer}")
```

**Output esperado:**

```
Pregunta: ¿Dónde está definida la función calculate_tax?
  [tool] list_files({'directory': './sample_project'})
  [tool] list_files({'directory': './sample_project/src'})
  [tool] read_file({'path': './sample_project/src/billing.py'})
Respuesta: La función `calculate_tax` está definida en `src/billing.py`, línea 23.
Recibe un `amount` (float) y un `region` (str), y retorna el monto con impuesto aplicado.

Pregunta: ¿Qué archivos hay en el directorio src/?
  [tool] list_files({'directory': './sample_project/src'})
Respuesta: En el directorio `src/` hay 4 archivos:
- billing.py
- orders.py
- payments.py
- __init__.py

Pregunta: ¿Existe una función llamada send_invoice?
  [tool] list_files({'directory': './sample_project'})
  [tool] list_files({'directory': './sample_project/src'})
  [tool] read_file({'path': './sample_project/src/billing.py'})
  [tool] read_file({'path': './sample_project/src/orders.py'})
  [tool] read_file({'path': './sample_project/src/payments.py'})
Respuesta: No encontré ninguna función llamada `send_invoice` en el directorio.
Busqué en todos los archivos de `src/` (billing.py, orders.py, payments.py) y no existe.
```

**Qué muestra:** el agente usa múltiples tool calls para explorar el directorio antes de responder. Cuando la función no existe, dice que buscó — no inventa.

---

## Ejemplo 2 — Tool use con criterio de terminación explícito

**Archivo:** `examples/02_tool_use.py`

Mismo agente pero con una herramienta `task_complete` que el modelo llama cuando terminó. Evita que el agente responda a medias.

```python
import anthropic
import os

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "search_in_file",
        "description": "Busca un patrón en un archivo y retorna las líneas que lo contienen",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "pattern": {"type": "string"}
            },
            "required": ["path", "pattern"]
        }
    },
    {
        "name": "task_complete",
        "description": "Llamá esto cuando tengas la respuesta completa y confirmada",
        "input_schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "description": "La respuesta final"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de archivos consultados"
                }
            },
            "required": ["answer", "confidence", "sources"]
        }
    }
]

def execute_tool(name, input):
    if name == "read_file":
        return open(input["path"]).read()
    elif name == "search_in_file":
        lines = []
        with open(input["path"]) as f:
            for i, line in enumerate(f, 1):
                if input["pattern"].lower() in line.lower():
                    lines.append(f"L{i}: {line.rstrip()}")
        return "\n".join(lines) if lines else "Sin coincidencias"
    return None

def run_agent(question: str) -> dict:
    messages = [{"role": "user", "content": question}]
    MAX_ITERATIONS = 8

    for i in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=TOOLS,
            messages=messages
        )

        # El agente decidió terminar con task_complete
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "task_complete":
                        # Esta es la respuesta final
                        return block.input
                    result = execute_tool(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "user", "content": results})

        elif response.stop_reason == "end_turn":
            return {"answer": response.content[0].text, "confidence": "low", "sources": []}

    return {"answer": "Límite de iteraciones alcanzado", "confidence": "low", "sources": []}

result = run_agent("¿Cuáles son todos los endpoints de la API definidos en src/api.py?")
print(f"Respuesta: {result['answer']}")
print(f"Confianza: {result['confidence']}")
print(f"Fuentes consultadas: {', '.join(result['sources'])}")
```

**Output esperado:**

```
Respuesta: Los endpoints definidos en src/api.py son:
- POST /api/orders — crear una orden nueva
- GET  /api/orders/{id} — obtener orden por ID
- PUT  /api/orders/{id}/status — actualizar estado
- POST /api/payments — iniciar pago
- GET  /api/payments/{id}/status — consultar estado del pago

Confianza: high
Fuentes consultadas: src/api.py
```

**Qué muestra:** el patrón `task_complete` garantiza que el modelo entregue una respuesta estructurada con metadatos (confianza, fuentes). El código sabe exactamente cuándo el agente terminó.

---

## Ejemplo 3 — Memoria in-context vs externa

**Archivo:** `examples/03_memory.py`

Compara dos tipos de memoria: in-context (ephímera, se pierde al terminar) y SQLite (persiste entre sesiones).

```python
import anthropic
import sqlite3
import json
import time

client = anthropic.Anthropic()

# ── TIPO 1: Memoria in-context ──────────────────────────────────
# Vive en `messages`. Muere cuando termina el proceso.

def chat_with_memory(conversation_history: list, user_message: str) -> str:
    conversation_history.append({"role": "user", "content": user_message})
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system="Sos un asistente que recuerda lo que te dicen en la conversación.",
        messages=conversation_history
    )
    reply = response.content[0].text
    conversation_history.append({"role": "assistant", "content": reply})
    return reply

# ── TIPO 2: Memoria externa (SQLite) ────────────────────────────
# Persiste entre sesiones. Sobrevive reinicios del proceso.

def setup_db():
    conn = sqlite3.connect("agent_memory.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY,
        task TEXT,
        outcome TEXT,
        learned TEXT,
        timestamp REAL
    )""")
    conn.commit()
    return conn

def save_episode(conn, task: str, outcome: str, learned: str):
    conn.execute(
        "INSERT INTO episodes (task, outcome, learned, timestamp) VALUES (?, ?, ?, ?)",
        (task, outcome, learned, time.time())
    )
    conn.commit()

def recall_similar(conn, current_task: str) -> list:
    # Búsqueda simple por keyword (el módulo 6 lo reemplaza con embeddings)
    words = current_task.lower().split()
    results = []
    for word in words:
        rows = conn.execute(
            "SELECT task, outcome, learned FROM episodes WHERE task LIKE ?",
            (f"%{word}%",)
        ).fetchall()
        results.extend(rows)
    return list({r[0]: r for r in results}.values())  # dedup

# ── Demo ─────────────────────────────────────────────────────────

print("=== TIPO 1: Memoria in-context ===\n")
history = []

r1 = chat_with_memory(history, "Me llamo Ricardo y trabajo en un proyecto de e-commerce.")
print(f"User: Me llamo Ricardo y trabajo en un proyecto de e-commerce.")
print(f"Agent: {r1}\n")

r2 = chat_with_memory(history, "¿Cómo me llamo?")
print(f"User: ¿Cómo me llamo?")
print(f"Agent: {r2}\n")

# Nueva sesión — historia perdida
print("--- Nueva sesión (historia vacía) ---\n")
new_history = []
r3 = chat_with_memory(new_history, "¿Cómo me llamo?")
print(f"User: ¿Cómo me llamo?")
print(f"Agent: {r3}\n")

print("\n=== TIPO 2: Memoria externa (SQLite) ===\n")
conn = setup_db()

# Guardar episodios pasados
save_episode(conn,
    task="Implementar sistema de cupones",
    outcome="Exitoso. Tests pasan.",
    learned="Los cupones deben validarse antes de congelar el precio (ADR-001)"
)
save_episode(conn,
    task="Optimizar queries de órdenes",
    outcome="Exitoso. Latencia bajó 60%.",
    learned="Agregar índice en orders.created_at antes de cualquier query por fecha"
)

# Nueva tarea — buscar experiencias relevantes
task = "Agregar descuento por volumen"
similar = recall_similar(conn, task)
print(f"Tarea actual: {task}")
print(f"Episodios relevantes encontrados: {len(similar)}")
for ep in similar:
    print(f"  • [{ep[0]}] → {ep[2]}")

conn.close()
```

**Output esperado:**

```
=== TIPO 1: Memoria in-context ===

User: Me llamo Ricardo y trabajo en un proyecto de e-commerce.
Agent: ¡Hola Ricardo! Es un gusto. ¿En qué puedo ayudarte con tu proyecto de e-commerce?

User: ¿Cómo me llamo?
Agent: Te llamas Ricardo.

--- Nueva sesión (historia vacía) ---

User: ¿Cómo me llamo?
Agent: No lo sé — no tenemos historial de conversación previo. ¿Cómo te llamas?


=== TIPO 2: Memoria externa (SQLite) ===

Tarea actual: Agregar descuento por volumen
Episodios relevantes encontrados: 1
  • [Implementar sistema de cupones] → Los cupones deben validarse antes de congelar el precio (ADR-001)
```

**Qué muestra:**
- In-context: la segunda sesión no recuerda nada. La memoria muere con el proceso.
- Externa: la nueva sesión encuentra el episodio de "cupones" porque comparte palabras con "descuento". El aprendizaje persiste.
- Limitación visible: la búsqueda por keyword no encontró el episodio de "órdenes" porque no comparte palabras con "descuento por volumen". El módulo 6 resuelve esto con embeddings.

---

Ver el [README principal](./README.md) para los conceptos de agentes, ReAct loop y tipos de memoria.
