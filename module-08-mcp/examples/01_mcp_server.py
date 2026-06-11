"""
Módulo 8 — Ejemplo 1: MCP Server mínimo

Implementa un servidor MCP con herramientas para explorar código:
- search_code: busca texto en archivos de un directorio
- read_file: lee el contenido de un archivo
- list_files: lista archivos en un directorio

Este servidor puede ser usado por:
- Claude Code (configurando en ~/.claude/settings.json)
- Cualquier cliente MCP
- El ejemplo 02_mcp_client.py de este módulo

Requisitos:
    pip install mcp

Uso:
    python 01_mcp_server.py

    # Para Claude Code, agregar en ~/.claude/settings.json:
    # {
    #   "mcpServers": {
    #     "code-explorer": {
    #       "command": "python",
    #       "args": ["/ruta/absoluta/01_mcp_server.py"]
    #     }
    #   }
    # }
"""

import os
import re
from pathlib import Path
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

server = Server("code-explorer")
WORKSPACE = Path(os.environ.get("WORKSPACE_PATH", "."))


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_code",
            description="Busca un patrón de texto en archivos del workspace. Retorna archivos y líneas donde aparece.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Texto o regex a buscar"
                    },
                    "file_extension": {
                        "type": "string",
                        "description": "Filtrar por extensión (ej: '.py', '.ts'). Opcional.",
                        "default": ""
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Máximo de resultados a retornar",
                        "default": 20
                    }
                },
                "required": ["pattern"]
            }
        ),
        types.Tool(
            name="read_file",
            description="Lee el contenido de un archivo del workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta relativa al workspace"
                    }
                },
                "required": ["path"]
            }
        ),
        types.Tool(
            name="list_files",
            description="Lista archivos en un directorio del workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directorio relativo al workspace (default: raíz)",
                        "default": "."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Listar recursivamente",
                        "default": False
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "search_code":
        return _search_code(
            arguments["pattern"],
            arguments.get("file_extension", ""),
            arguments.get("max_results", 20)
        )
    elif name == "read_file":
        return _read_file(arguments["path"])
    elif name == "list_files":
        return _list_files(
            arguments.get("directory", "."),
            arguments.get("recursive", False)
        )
    else:
        return [types.TextContent(type="text", text=f"ERROR: herramienta desconocida '{name}'")]


def _search_code(pattern: str, extension: str, max_results: int) -> list[types.TextContent]:
    results = []
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)

    count = 0
    for path in WORKSPACE.rglob("*"):
        if not path.is_file():
            continue
        if extension and path.suffix != extension:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue  # skip hidden dirs

        try:
            content = path.read_text(errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    rel = path.relative_to(WORKSPACE)
                    results.append(f"{rel}:{i}: {line.strip()}")
                    count += 1
                    if count >= max_results:
                        results.append(f"[Truncado: {max_results} resultados máximo]")
                        return [types.TextContent(type="text", text="\n".join(results))]
        except Exception:
            continue

    text = "\n".join(results) if results else f"No se encontró '{pattern}'"
    return [types.TextContent(type="text", text=text)]


def _read_file(rel_path: str) -> list[types.TextContent]:
    target = (WORKSPACE / rel_path).resolve()

    # Path traversal guard
    if not str(target).startswith(str(WORKSPACE.resolve())):
        return [types.TextContent(type="text", text="ERROR: Acceso denegado — ruta fuera del workspace")]

    if not target.exists():
        return [types.TextContent(type="text", text=f"ERROR: Archivo no encontrado: {rel_path}")]

    try:
        content = target.read_text(errors="replace")
        return [types.TextContent(type="text", text=content)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"ERROR: {e}")]


def _list_files(directory: str, recursive: bool) -> list[types.TextContent]:
    target = (WORKSPACE / directory).resolve()

    if not str(target).startswith(str(WORKSPACE.resolve())):
        return [types.TextContent(type="text", text="ERROR: Ruta fuera del workspace")]

    if not target.is_dir():
        return [types.TextContent(type="text", text=f"ERROR: No es un directorio: {directory}")]

    glob = target.rglob("*") if recursive else target.iterdir()
    files = []
    for p in sorted(glob):
        if any(part.startswith(".") for part in p.parts):
            continue
        if p.is_file():
            files.append(str(p.relative_to(WORKSPACE)))

    text = "\n".join(files) if files else "Directorio vacío"
    return [types.TextContent(type="text", text=text)]


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.server.stdio.run(server))
