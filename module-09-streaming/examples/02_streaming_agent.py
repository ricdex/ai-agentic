"""
Módulo 9 — Ejemplo 2: Agente con streaming completo + SSE endpoint

Demuestra:
- Agente con tool use que streamed su razonamiento en tiempo real
- Callbacks visuales para cada evento (texto, tool call, tool result)
- Endpoint FastAPI con Server-Sent Events para consumo desde frontend

Ejecutar solo el agente en consola:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 02_streaming_agent.py

Ejecutar como servidor HTTP:
    pip install fastapi uvicorn
    python 02_streaming_agent.py --server
    # Luego: curl -N http://localhost:8000/stream -d '{"task":"listá archivos en /tmp"}'
"""

import sys
import time
import json
from pathlib import Path
import anthropic

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "read_file",
        "description": "Lee un archivo.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "list_files",
        "description": "Lista archivos en un directorio.",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string", "default": "."}},
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    if name == "read_file":
        try:
            return Path(inputs["path"]).read_text(errors="replace")[:2000]
        except Exception as e:
            return f"ERROR: {e}"
    elif name == "list_files":
        d = Path(inputs.get("directory", "."))
        if not d.exists():
            return f"ERROR: Directorio no encontrado: {d}"
        files = [str(p) for p in sorted(d.iterdir()) if not p.name.startswith(".")]
        return "\n".join(files) or "Directorio vacío"
    return f"ERROR: herramienta desconocida '{name}'"


# --- Agente con streaming ---

def run_streaming_agent(task: str, on_text=None, on_tool_start=None, on_tool_end=None):
    """
    Corre el agente streameando cada evento.

    Callbacks:
      on_text(str)                       — fragmento de texto
      on_tool_start(name, inputs)        — antes de ejecutar una herramienta
      on_tool_end(name, result_preview)  — después de ejecutar
    """
    on_text = on_text or (lambda t: print(t, end="", flush=True))
    on_tool_start = on_tool_start or (lambda n, i: print(f"\n[→ {n}({list(i.values())[0] if i else ''})]", flush=True))
    on_tool_end = on_tool_end or (lambda n, r: print(f"[← {r[:80]}{'...' if len(r) > 80 else ''}]", flush=True))

    messages = [{"role": "user", "content": task}]
    total_input = total_output = total_cached = 0

    for iteration in range(6):
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=TOOLS,
            messages=messages,
            system="Sos un agente que explora el filesystem. Respondé solo basándote en lo que leés."
        ) as stream:
            for text in stream.text_stream:
                on_text(text)

            message = stream.get_final_message()

        total_input += message.usage.input_tokens
        total_output += message.usage.output_tokens
        total_cached += getattr(message.usage, "cache_read_input_tokens", 0)

        if message.stop_reason == "end_turn":
            return {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cached_tokens": total_cached,
                "iterations": iteration + 1
            }

        if message.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": message.content})
            tool_results = []

            for block in message.content:
                if block.type != "tool_use":
                    continue

                on_tool_start(block.name, block.input)
                result = execute_tool(block.name, block.input)
                on_tool_end(block.name, result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

            messages.append({"role": "user", "content": tool_results})

    return {"error": "Límite de iteraciones alcanzado"}


# --- SSE Server (FastAPI) ---

def run_server():
    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse
        from pydantic import BaseModel
    except ImportError:
        print("Instalá: pip install fastapi uvicorn")
        sys.exit(1)

    app = FastAPI()

    class TaskRequest(BaseModel):
        task: str

    @app.post("/stream")
    async def stream_agent(req: TaskRequest):
        async def generate():
            events = []

            def on_text(t):
                events.append(json.dumps({"type": "text", "content": t}))

            def on_tool_start(name, inputs):
                events.append(json.dumps({"type": "tool_start", "name": name}))

            def on_tool_end(name, result):
                events.append(json.dumps({"type": "tool_end", "name": name, "preview": result[:100]}))

            import threading
            done = threading.Event()
            stats = {}

            def run():
                stats.update(run_streaming_agent(req.task, on_text, on_tool_start, on_tool_end))
                done.set()

            t = threading.Thread(target=run)
            t.start()

            import asyncio
            while not done.is_set() or events:
                if events:
                    yield f"data: {events.pop(0)}\n\n"
                else:
                    await asyncio.sleep(0.05)

            yield f"data: {json.dumps({'type': 'done', 'stats': stats})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    print("Servidor SSE en http://localhost:8000")
    print('Ejemplo: curl -N -X POST http://localhost:8000/stream -H "Content-Type: application/json" -d \'{"task": "listá archivos en /tmp"}\'')
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    if "--server" in sys.argv:
        run_server()
    else:
        print("Tarea: explorar el directorio /tmp y listar los archivos más recientes\n")
        print("=" * 60)
        start = time.time()

        stats = run_streaming_agent(
            "Listá los archivos en /tmp y leé el contenido del más reciente que encuentres"
        )

        elapsed = time.time() - start
        print(f"\n\n--- Stats ---")
        print(f"  Iteraciones:    {stats.get('iterations', '?')}")
        print(f"  Tokens in/out:  {stats.get('input_tokens', 0)} / {stats.get('output_tokens', 0)}")
        print(f"  Cached:         {stats.get('cached_tokens', 0)}")
        print(f"  Latencia total: {elapsed:.1f}s")
