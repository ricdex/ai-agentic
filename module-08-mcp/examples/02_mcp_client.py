"""
Módulo 8 — Ejemplo 2: Cliente MCP + Claude

Conecta un servidor MCP (01_mcp_server.py) con Claude.
El cliente:
1. Lanza el servidor como subprocess
2. Descubre sus herramientas automáticamente
3. Las convierte al formato tool_use de Claude
4. Corre el loop de agente usando esas herramientas

Esto es la base de cómo funciona Claude Code internamente.

Requisitos:
    pip install anthropic mcp

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 02_mcp_client.py
"""

import asyncio
import json
import sys
from pathlib import Path
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

claude = anthropic.Anthropic()
SERVER_SCRIPT = str(Path(__file__).parent / "01_mcp_server.py")


def mcp_tool_to_claude_tool(mcp_tool) -> dict:
    """Convierte una tool definition MCP al formato que Claude espera."""
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description or "",
        "input_schema": mcp_tool.inputSchema
    }


async def run_agent_with_mcp(question: str, workspace_path: str):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_SCRIPT],
        env={"WORKSPACE_PATH": workspace_path}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Descubrir herramientas del servidor
            tools_response = await session.list_tools()
            claude_tools = [mcp_tool_to_claude_tool(t) for t in tools_response.tools]

            print(f"[MCP] {len(claude_tools)} herramientas disponibles: "
                  f"{[t['name'] for t in claude_tools]}")
            print(f"\nPregunta: {question}\n")

            messages = [{"role": "user", "content": question}]

            for _ in range(10):
                response = claude.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    tools=claude_tools,
                    messages=messages,
                    system=(
                        "Sos un asistente que explora código. "
                        "Usá las herramientas disponibles para responder con información concreta del repo. "
                        "No inventes código ni estructuras — solo reportá lo que encontrás."
                    )
                )

                if response.stop_reason == "end_turn":
                    text = next((b.text for b in response.content if hasattr(b, "text")), "")
                    print(f"Respuesta:\n{text}")
                    return

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})
                    tool_results = []

                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        first_arg = str(list(block.input.values())[0])[:50] if block.input else ""
                        print(f"  → {block.name}({first_arg})")

                        # Llamar la herramienta via MCP
                        result = await session.call_tool(block.name, arguments=block.input)
                        result_text = "\n".join(
                            c.text for c in result.content if hasattr(c, "text")
                        )

                        print(f"  ← {result_text[:100]}{'...' if len(result_text) > 100 else ''}")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text
                        })

                    messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    import os

    # Apuntar al proyecto final del curso como workspace demo
    workspace = str(Path(__file__).parent.parent.parent.parent / "final-project")

    questions = [
        "¿Cuáles son los archivos principales del agent-core? ¿Qué hace el orchestrator?",
        "¿Dónde se valida la firma del webhook? Mostrá el código relevante.",
    ]

    for q in questions:
        print("=" * 70)
        asyncio.run(run_agent_with_mcp(q, workspace))
        print()
