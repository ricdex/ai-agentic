# Módulo 9 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Streaming básico con métricas de latencia

**Archivo:** `examples/01_basic_stream.py`

La diferencia entre recibir todo el texto al final vs token a token. Incluye TTFT (Time to First Token).

```python
import anthropic
import time

client = anthropic.Anthropic()

PROMPT = "Explicá en detalle cómo funciona el garbage collector de Python, incluyendo el algoritmo de conteo de referencias y el collector de ciclos."

# ── SIN streaming ────────────────────────────────────────────────
print("=== Sin streaming ===")
start = time.time()
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=400,
    messages=[{"role": "user", "content": PROMPT}]
)
total = time.time() - start
print(f"[{total:.2f}s de espera, luego todo de golpe]\n")
print(response.content[0].text[:200] + "...\n")

# ── CON streaming ────────────────────────────────────────────────
print("=== Con streaming ===")
start = time.time()
first_token_time = None
token_count = 0

with client.messages.stream(
    model="claude-haiku-4-5-20251001",
    max_tokens=400,
    messages=[{"role": "user", "content": PROMPT}]
) as stream:
    for text in stream.text_stream:
        if first_token_time is None:
            first_token_time = time.time()
            ttft = first_token_time - start
            print(f"[primer token en {ttft:.2f}s → texto aparece inmediatamente]\n")
        print(text, end="", flush=True)
        token_count += 1

total = time.time() - start
final = stream.get_final_message()

print(f"\n\n--- Métricas ---")
print(f"TTFT (Time to First Token): {ttft:.2f}s")
print(f"Tiempo total:               {total:.2f}s")
print(f"Chunks recibidos:           {token_count}")
print(f"Tokens de output:           {final.usage.output_tokens}")
print(f"Tokens/segundo:             {final.usage.output_tokens / total:.0f}")
```

**Output esperado:**

```
=== Sin streaming ===
[3.87s de espera, luego todo de golpe]

Python usa dos mecanismos para gestionar memoria: conteo de referencias y un garbage
collector para ciclos...

=== Con streaming ===
[primer token en 0.31s → texto aparece inmediatamente]

Python usa dos mecanismos para gestionar memoria:

**1. Conteo de referencias (Reference Counting)**
Cada objeto en Python tiene un contador interno (`ob_refcnt`). Cuando el contador
llega a 0, el objeto se libera inmediatamente. Es determinístico y de bajo overhead.

**2. Collector de ciclos (Cyclic GC)**
El conteo de referencias no puede manejar referencias circulares (A → B → A).
El GC de Python corre periódicamente usando el algoritmo de "generaciones"...

--- Métricas ---
TTFT (Time to First Token): 0.31s
Tiempo total:               3.91s
Chunks recibidos:           187
Tokens de output:           312
Tokens/segundo:             80
```

**Qué muestra:**
- Sin streaming: 3.87s de silencio → todo aparece junto
- Con streaming: primer token en 0.31s → el usuario empieza a leer mientras el modelo sigue generando
- La diferencia de UX es enorme para respuestas de 3+ segundos

---

## Ejemplo 2 — Agente con streaming: ver el razonamiento en tiempo real

**Archivo:** `examples/02_streaming_agent.py`

El agente completo del módulo 3 pero con streaming. El usuario ve qué está pensando y qué herramienta está usando.

```python
import anthropic
import time
import json

client = anthropic.Anthropic()

TOOLS = [
    {"name": "read_file", "description": "Lee un archivo",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "search_code", "description": "Busca en el código",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "run_tests", "description": "Corre los tests",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
]

FAKE_TOOLS = {
    "read_file": lambda i: "def process_payment(amount):\n    return amount * 1.1  # aplica siempre IVA",
    "search_code": lambda i: "src/payments.py:5: def process_payment",
    "run_tests": lambda i: "1 passed in 0.09s",
}

def run_streaming_agent(task: str):
    messages = [{"role": "user", "content": task}]
    iteration = 0

    while iteration < 4:
        iteration += 1
        print(f"\n{'─'*40}")
        print(f"Iteración {iteration}:")
        print(f"{'─'*40}")

        all_text = ""
        tool_calls = []
        start = time.time()
        first_token = None

        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=600,
            tools=TOOLS,
            messages=messages
        ) as stream:
            for event in stream:
                # Texto del razonamiento: se streamed token a token
                if hasattr(event, 'type') and event.type == 'content_block_delta':
                    if hasattr(event.delta, 'text'):
                        if first_token is None:
                            first_token = time.time()
                            print(f"  [primer token: {first_token - start:.2f}s]")
                        print(event.delta.text, end="", flush=True)
                        all_text += event.delta.text

            # Tool calls: se entregan completos al terminar el stream
            message = stream.get_final_message()

        if message.stop_reason == "end_turn":
            print(f"\n\n✓ Agente finalizó en iteración {iteration}")
            return

        if message.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": message.content})
            results = []
            for block in message.content:
                if block.type == "tool_use":
                    print(f"\n  [→ {block.name}({list(block.input.values())[0]!r:.40s})]")
                    result = FAKE_TOOLS.get(block.name, lambda i: "ok")(block.input)
                    print(f"  [← {result[:60]!r}]")
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": results})

run_streaming_agent("Hay un bug: process_payment aplica IVA a clientes exentos. Encontrá y arreglá el problema.")
```

**Output esperado:**

```
────────────────────────────────────────
Iteración 1:
────────────────────────────────────────
  [primer token: 0.28s]
Voy a buscar el código de process_payment para entender el problema.

  [→ search_code('process_payment')]
  [← 'src/payments.py:5: def process_payment']

  [→ read_file('src/payments.py')]
  [← 'def process_payment(amount):\n    return amount * 1.1  # aplica siempre IVA']

────────────────────────────────────────
Iteración 2:
────────────────────────────────────────
  [primer token: 0.31s]
Encontré el bug. La función siempre multiplica por 1.1 sin verificar si el cliente
es exento. Voy a corregirlo agregando el parámetro `exempt`.

  [→ read_file('src/payments.py')]   ← confirma el contenido antes de editar
  [← 'def process_payment(amount):\n    return amount * 1.1  # aplica siempre IVA']

────────────────────────────────────────
Iteración 3:
────────────────────────────────────────
  [primer token: 0.25s]
Corrijo la función y corro los tests para verificar.

  [→ run_tests('tests/test_payments.py')]
  [← '1 passed in 0.09s']

✓ Agente finalizó en iteración 3
```

**Qué muestra:**
- El texto de razonamiento aparece token a token (primer token en ~0.3s)
- Los tool calls aparecen completos cuando el stream termina
- El usuario puede leer "Voy a buscar..." y ver la herramienta ejecutarse sin esperar
- En una UI, esto se vería como el agente "escribiendo" su razonamiento en tiempo real

---

## Ejemplo 3 — SSE endpoint: streaming desde API a browser

```python
# FastAPI server
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import anthropic
import json

app = FastAPI()
client = anthropic.Anthropic()

@app.post("/agent/stream")
async def stream_agent(request: dict):
    task = request.get("task", "")

    async def generate():
        try:
            # Evento de inicio
            yield f"data: {json.dumps({'type': 'start', 'task': task})}\n\n"

            with client.messages.stream(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": task}]
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"

            final = stream.get_final_message()
            yield f"data: {json.dumps({'type': 'done', 'tokens': final.usage.output_tokens})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

```javascript
// Frontend que consume el SSE
const output = document.getElementById('output');
const response = await fetch('/agent/stream', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({task: 'Analizá este PR'})
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const {done, value} = await reader.read();
    if (done) break;

    const lines = decoder.decode(value).split('\n');
    for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const event = JSON.parse(line.slice(6));

        if (event.type === 'text') {
            output.textContent += event.content;  // aparece token a token
        } else if (event.type === 'done') {
            console.log(`Completado: ${event.tokens} tokens`);
        }
    }
}
```

**Lo que ve el usuario en el browser:**

```
[El texto aparece letra a letra, como si alguien estuviera escribiendo]

"Revisando los cambios en auth.py...
 
 Encontré un problema en la línea 42: el token de sesión no se invalida
 al cambiar la contraseña. Esto permite que sesiones antiguas sigan activas
 después de un cambio de credenciales.
 
 Recomendación: llamar a session.invalidate_all(user_id) después de..."

[Completado: 187 tokens]
```

---

Ver el [README principal](./README.md) para las métricas de streaming y cómo manejar tool use en el stream.
