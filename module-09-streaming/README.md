# Módulo 9 — Streaming

> "Sin streaming, el usuario ve nada por 10 segundos y luego todo a la vez. Con streaming, ve el agente pensando en tiempo real."

---

## 9.1 Por qué streaming importa en producción

**Sin streaming:**
```
Usuario: "Analizá este PR"
         [............. 8 segundos de silencio .............]
Claude:  [Respuesta completa de 500 palabras aparece de golpe]
```

**Con streaming:**
```
Usuario: "Analizá este PR"
Claude:  "Revisando los cambios en auth.py..." ← aparece inmediatamente
         "Encontré un problema en la línea 42..."  ← sigue fluyendo
         "El fix propuesto es..."  ← el usuario ya está leyendo mientras Claude termina
```

Para agentes de larga duración (30s+), streaming es **obligatorio** en cualquier UI. Sin él, los usuarios asumen que la app se colgó.

---

## 9.2 Streaming básico con el SDK

```python
with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Explicá este código"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)  # cada token a medida que llega

# Después del with, accedés al mensaje completo si lo necesitás
final = stream.get_final_message()
print(f"\n\nTokens: {final.usage.input_tokens} in, {final.usage.output_tokens} out")
```

---

## 9.3 Streaming con tool use

Tool use y streaming se combinan, pero con una particularidad: los tool calls **no se streamed** en fragmentos intermedios — el SDK los entrega completos cuando el bloque termina.

```python
with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=2048,
    tools=my_tools,
    messages=messages
) as stream:
    # Texto se streamed token a token
    for text in stream.text_stream:
        print(text, end="", flush=True)

    # Al terminar el stream, inspeccionás el mensaje completo
    message = stream.get_final_message()

if message.stop_reason == "tool_use":
    # Procesás tool calls como siempre
    for block in message.content:
        if block.type == "tool_use":
            result = execute_tool(block.name, block.input)
            # ... continuar el loop
```

---

## 9.4 Server-Sent Events para APIs web

Para exponer un agente vía HTTP con streaming, SSE (Server-Sent Events) es el estándar:

```python
# FastAPI
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/agent/stream")
async def stream_agent(request: AgentRequest):
    async def generate():
        with client.messages.stream(...) as stream:
            for text in stream.text_stream:
                # Formato SSE: "data: {...}\n\n"
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

```javascript
// Frontend
const eventSource = new EventSource('/agent/stream');
eventSource.onmessage = (e) => {
    if (e.data === '[DONE]') return eventSource.close();
    const { text } = JSON.parse(e.data);
    document.getElementById('output').textContent += text;
};
```

---

## 9.5 Streaming en agentes multi-turn

El patrón completo para un agente con streaming en cada iteración:

```
Iteración 1: [stream texto pensando...] → [tool call completo] → ejecutar → continuar
Iteración 2: [stream texto con análisis...] → [tool call] → ejecutar → continuar
Iteración N: [stream respuesta final...] → end_turn
```

La UI puede mostrar:
- El texto de razonamiento en tiempo real
- Un indicador de "usando herramienta X..." cuando hay un tool call
- El resultado de la herramienta cuando vuelve

---

## 9.6 Métricas de streaming

```python
import time

first_token_time = None
start = time.time()

with client.messages.stream(...) as stream:
    for text in stream.text_stream:
        if first_token_time is None:
            first_token_time = time.time()
        print(text, end="", flush=True)

ttft = first_token_time - start  # Time to First Token — métrica clave de UX
total = time.time() - start
```

**TTFT (Time to First Token)** es la métrica de UX más importante en streaming. Objetivo: < 1 segundo.

---

## Ejemplos de código

- [`01_basic_stream.py`](./examples/01_basic_stream.py) — Streaming básico con métricas de latencia
- [`02_streaming_agent.py`](./examples/02_streaming_agent.py) — Agente completo con streaming + tool use + SSE endpoint

---

## Ejercicio

Tomá el `issue_solver.py` del módulo 3 y hacelo streameable:

1. Cada iteración del agente debe streamear el texto de razonamiento
2. Cuando hay un tool call, mostrar en tiempo real: `[→ usando read_file...]`
3. Cuando el tool retorna, mostrar: `[← resultado de read_file (X chars)]`
4. Al final, mostrar el resumen de costo y latencia

El usuario debe poder ver "qué está pensando" el agente en tiempo real.

---

Siguiente: [Módulo 10 → Evals](../module-10-evals/README.md)
