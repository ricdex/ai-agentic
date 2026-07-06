# Módulo 8 — Ejemplos con Output Esperado

---

## Ejemplo 1 — MCP Server mínimo

**Archivo:** `examples/01_mcp_server.py`

Un servidor MCP que expone herramientas de búsqueda de código. Cualquier cliente MCP (Claude Code, Cursor, etc.) puede usarlo.

```python
import asyncio
import json
import os
import subprocess
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

server = Server("code-search-server")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_code",
            description="Busca un patrón en todos los archivos .py del repositorio",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Texto o regex a buscar"
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directorio donde buscar (default: '.')",
                        "default": "."
                    }
                },
                "required": ["pattern"]
            }
        ),
        types.Tool(
            name="list_files",
            description="Lista archivos .py en un directorio",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "default": "."}
                },
                "required": []
            }
        ),
        types.Tool(
            name="read_file",
            description="Lee el contenido de un archivo",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "search_code":
        pattern = arguments["pattern"]
        directory = arguments.get("directory", ".")
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", pattern, directory],
            capture_output=True, text=True
        )
        output = result.stdout if result.stdout else "Sin resultados"
        return [types.TextContent(type="text", text=output)]

    elif name == "list_files":
        directory = arguments.get("directory", ".")
        files = []
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in filenames:
                if f.endswith('.py'):
                    files.append(os.path.join(root, f))
        return [types.TextContent(type="text", text="\n".join(files))]

    elif name == "read_file":
        try:
            content = open(arguments["path"]).read()
            return [types.TextContent(type="text", text=content)]
        except FileNotFoundError:
            return [types.TextContent(type="text", text=f"Archivo no encontrado: {arguments['path']}")]

    raise ValueError(f"Tool desconocida: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

**Cómo arranca el servidor:**

```bash
python examples/01_mcp_server.py
```

```
# El servidor no imprime nada — espera conexiones por stdin/stdout
# Así lo ve el cliente MCP al conectarse:
```

**Intercambio de mensajes MCP cuando el cliente llama `search_code`:**

```
# Cliente → Servidor
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {"pattern": "process_payment", "directory": "./src"}
  }
}

# Servidor → Cliente
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "./src/payments.py:23:def process_payment(amount, method):\n./src/orders.py:87:    result = process_payment(order.total, order.payment_method)"
      }
    ]
  }
}
```

---

## Ejemplo 2 — MCP Client: conectar Claude con el servidor

**Archivo:** `examples/02_mcp_client.py`

Cliente que conecta el servidor MCP con Claude. Claude puede llamar las herramientas del servidor como si fueran tool_use normales.

```python
import asyncio
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

client = anthropic.Anthropic()

async def run_agent_with_mcp():
    # 1. Lanzar el servidor MCP como subprocess
    server_params = StdioServerParameters(
        command="python",
        args=["examples/01_mcp_server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 2. Descubrir las herramientas disponibles en el servidor
            tools_response = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema
                }
                for t in tools_response.tools
            ]
            print(f"Herramientas disponibles: {[t['name'] for t in tools]}\n")

            # 3. Usar Claude con esas herramientas
            messages = [{
                "role": "user",
                "content": "¿Dónde se llama a process_payment en el código? Lista todos los lugares."
            }]

            while True:
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=500,
                    tools=tools,
                    messages=messages
                )

                if response.stop_reason == "end_turn":
                    print("Respuesta final:")
                    print(response.content[0].text)
                    break

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})
                    results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            print(f"  [MCP] Llamando {block.name}({block.input})")
                            # 4. Ejecutar la herramienta en el servidor MCP
                            result = await session.call_tool(block.name, block.input)
                            content = result.content[0].text if result.content else ""
                            print(f"  [MCP] Resultado: {content[:100]}...")
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": content
                            })
                    messages.append({"role": "user", "content": results})

asyncio.run(run_agent_with_mcp())
```

**Output esperado:**

```
Herramientas disponibles: ['search_code', 'list_files', 'read_file']

  [MCP] Llamando search_code({'pattern': 'process_payment', 'directory': '.'})
  [MCP] Resultado: ./src/payments.py:23:def process_payment(amount, method):
./src/orders.py:87:    result = process_payment(order.total...

Respuesta final:
`process_payment` se llama en 2 lugares:

1. **`src/payments.py:23`** — aquí está definida la función
2. **`src/orders.py:87`** — es llamada durante el checkout, pasando `order.total` y `order.payment_method`

Si querés ver el contexto completo de alguno de estos lugares, puedo leer el archivo.
```

---

## Ejemplo 3 — Configurar el servidor en Claude Code

Una vez que tenés el servidor MCP, podés agregarlo a Claude Code en `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "code-search": {
      "command": "python",
      "args": ["/ruta/absoluta/a/01_mcp_server.py"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."
      }
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_CONNECTION_STRING": "postgresql://user:pass@localhost/mydb"
      }
    }
  }
}
```

**Lo que ve el usuario en Claude Code después de configurarlo:**

```
$ claude
> ¿Hay alguna función que procese reembolsos?

[usando code-search: search_code("refund")]
[usando code-search: search_code("reembolso")]

Encontré referencias a reembolsos en 2 archivos:
- `src/payments.py:145`: `def process_refund(payment_id, amount)`
- `src/admin.py:67`: `refund_btn.on_click(lambda: api.refund(payment.id))`

¿Querés que lea la implementación completa de `process_refund`?
```

**La diferencia vs tool_use hardcodeado:**

```
Sin MCP:
  Tu app define las tools → Solo tu app puede usarlas
  Cambiar de Claude a GPT → Reescribir todas las tools

Con MCP:
  El servidor define las tools → Claude Code, Cursor, tu app, todos las usan
  Cambiar de Claude a GPT → Cambiar solo el cliente, el servidor no cambia
```

---

Ver el [README principal](./README.md) para la arquitectura MCP completa y cuándo construir vs usar un servidor existente.
