# Módulo 8 — MCP (Model Context Protocol)

> "MCP es al AI lo que HTTP fue a la web: el protocolo que permite que cualquier herramienta hable con cualquier modelo."

---

## 8.1 Qué es MCP y por qué importa

MCP (Model Context Protocol) es un protocolo open-source de Anthropic que estandariza cómo los modelos de lenguaje se conectan a herramientas y fuentes de datos externas.

**Antes de MCP:**
```
Claude ──→ tool_use hardcodeado en tu código
GPT    ──→ function calling hardcodeado en tu código
Gemini ──→ function calling hardcodeado en tu código
```
Cada integración era ad-hoc. Cambiar de modelo = reescribir todas las herramientas.

**Con MCP:**
```
[Claude] ─┐
[GPT]    ─┼──→ MCP Client ──→ MCP Server ──→ [GitHub, Jira, DB, filesystem, ...]
[Cursor] ─┘
```
Una herramienta implementada como MCP server funciona con cualquier cliente MCP.

---

## 8.2 Arquitectura MCP

```
┌─────────────────────────────────────────────────────────┐
│                     HOST (tu app)                       │
│                                                         │
│  ┌─────────────┐    ┌──────────────────────────────┐   │
│  │   Claude    │    │        MCP Client             │   │
│  │   (o GPT,   │◄───┤                               │   │
│  │    etc.)    │    │  - Descubre las herramientas  │   │
│  └─────────────┘    │  - Llama tools del servidor  │   │
│                     │  - Gestiona la conexión       │   │
│                     └───────────┬──────────────────┘   │
└─────────────────────────────────┼───────────────────────┘
                                  │ JSON-RPC 2.0
                          ┌───────▼──────────────────┐
                          │      MCP Server          │
                          │                          │
                          │  tools:                  │
                          │   - list_issues()        │
                          │   - create_pr()          │
                          │   - search_code()        │
                          │  resources:              │
                          │   - repo_content         │
                          │  prompts:                │
                          │   - code_review_template │
                          └──────────────────────────┘
```

**Tres primitivas MCP:**
- **Tools**: funciones que el modelo puede llamar (equivalente a tool_use)
- **Resources**: datos que el modelo puede leer (archivos, DB, APIs)
- **Prompts**: templates de prompts parametrizables

---

## 8.3 Cómo funciona el protocolo

MCP usa JSON-RPC 2.0 sobre:
- **stdio**: el host lanza el servidor como subprocess y comunica por stdin/stdout
- **HTTP + SSE**: para servidores remotos

```
Client → Server: {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
Server → Client: {"jsonrpc": "2.0", "result": {"tools": [...]}, "id": 1}

Client → Server: {"jsonrpc": "2.0", "method": "tools/call",
                  "params": {"name": "search_code", "arguments": {"query": "payment"}}, "id": 2}
Server → Client: {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": "..."}]}, "id": 2}
```

---

## 8.4 MCP servers que ya existen

Podés usar MCP servers ya construidos en lugar de implementar herramientas desde cero:

```bash
# Instalar MCP SDK
pip install mcp

# Servidores oficiales disponibles
# Ver: https://github.com/modelcontextprotocol/servers
```

| Servidor | Qué hace |
|----------|---------|
| `mcp-server-github` | Issues, PRs, repos, code search |
| `mcp-server-postgres` | Queries SQL a PostgreSQL |
| `mcp-server-filesystem` | Leer/escribir archivos de forma segura |
| `mcp-server-brave-search` | Web search |
| `mcp-server-slack` | Mensajes, canales, usuarios |

---

## 8.5 Cuándo construir vs usar un server existente

**Usá un server existente si:**
- El servidor oficial cubre tu caso de uso
- Querés integrar Claude Code, Cursor o Windsurf con una herramienta estándar

**Construí tu propio server si:**
- Tenés APIs internas que no tienen server oficial
- Necesitás lógica de negocio específica en la capa de herramientas
- Querés exponer capacidades de tu sistema a múltiples clientes AI

---

## 8.6 MCP en Claude Code

Claude Code usa MCP nativo. Podés agregar servidores en `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."}
    },
    "mi-sistema-interno": {
      "command": "python",
      "args": ["/ruta/a/mi_mcp_server.py"]
    }
  }
}
```

Una vez configurado, Claude Code puede usar las herramientas del servidor directamente, sin que vos definas nada extra.

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — MCP Server mínimo](./EXAMPLES.md#ejemplo-1--mcp-server-mínimo) | Server con 3 tools; intercambio JSON-RPC real entre cliente y servidor |
| [02 — MCP Client con Claude](./EXAMPLES.md#ejemplo-2--mcp-client-conectar-claude-con-el-servidor) | Claude descubre las tools del server y las usa sin código extra |
| [03 — Configurar en Claude Code](./EXAMPLES.md#ejemplo-3--configurar-el-servidor-en-claude-code) | settings.json para registrar servers de GitHub, Postgres y código propio |

---

## Ejercicio

Construí un MCP server para el proyecto final del curso que exponga:
1. `list_open_issues(repo)` — lista issues abiertos de un repo
2. `get_file_content(repo, path)` — lee un archivo del repo
3. `search_code(repo, query)` — busca texto en el código
4. `create_pr(repo, branch, title, body)` — crea un PR

Luego conectá ese server con Claude Code para que pueda usarlo directamente desde el chat.

---

Siguiente: [Módulo 9 → Streaming](../module-09-streaming/README.md)
