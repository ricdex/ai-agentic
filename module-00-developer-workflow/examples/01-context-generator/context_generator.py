"""
Módulo 0 — Context Generator

Un agente que lee tu codebase y genera un CONTEXT.md borrador.
Lo que tarda horas hacer manualmente lo hace en minutos.

El agente:
1. Explora la estructura del repo
2. Lee los archivos más representativos del dominio
3. Identifica entidades, patrones, convenciones
4. Genera un CONTEXT.md listo para editar

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python context_generator.py /path/to/your/repo
"""

import sys
import re
import anthropic
from pathlib import Path

client = anthropic.Anthropic()

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "dist", "build", ".next", "coverage", "htmlcov"}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".class", ".o", ".lock",
                   ".png", ".jpg", ".svg", ".ico", ".pdf", ".woff"}
MAX_FILE_SIZE_KB = 30
MAX_FILES_TO_READ = 25


TOOLS = [
    {
        "name": "list_files",
        "description": "Lista los archivos del repo para entender su estructura.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "default": "."}
            },
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "search_code",
        "description": "Busca un patrón en el código para encontrar clases, funciones o conceptos clave.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "extension": {"type": "string", "default": ""}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "write_context_md",
        "description": (
            "Escribe el CONTEXT.md generado. Llamá esta herramienta cuando hayas "
            "analizado suficiente código para generar el documento."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "El contenido completo del CONTEXT.md"
                }
            },
            "required": ["content"]
        }
    }
]


def make_executor(repo_path: Path):
    files_read = [0]

    def execute(name: str, inputs: dict) -> str:
        if name == "list_files":
            directory = inputs.get("directory", ".")
            base = (repo_path / directory).resolve()
            items = []
            for f in sorted(base.rglob("*")):
                if any(skip in f.parts for skip in SKIP_DIRS):
                    continue
                if f.suffix in SKIP_EXTENSIONS:
                    continue
                rel = str(f.relative_to(repo_path))
                prefix = "[D]" if f.is_dir() else "[F]"
                items.append(f"{prefix} {rel}")
            return "\n".join(items[:150]) or "Directorio vacío"

        elif name == "read_file":
            if files_read[0] >= MAX_FILES_TO_READ:
                return "LIMIT: ya leí suficientes archivos para generar el contexto"
            path = repo_path / inputs["path"]
            if not path.exists():
                return f"ERROR: {inputs['path']} no encontrado"
            if path.stat().st_size > MAX_FILE_SIZE_KB * 1024:
                # Leer solo las primeras líneas de archivos grandes
                lines = path.read_text(errors="ignore").splitlines()[:80]
                return "\n".join(lines) + "\n... [truncado — archivo grande]"
            files_read[0] += 1
            return path.read_text(errors="ignore")

        elif name == "search_code":
            pattern = inputs["pattern"]
            ext = inputs.get("extension", "")
            results = []
            for f in repo_path.rglob(f"*{ext}" if ext else "*"):
                if not f.is_file():
                    continue
                if any(skip in f.parts for skip in SKIP_DIRS):
                    continue
                if f.suffix in SKIP_EXTENSIONS:
                    continue
                try:
                    text = f.read_text(errors="ignore")
                    for i, line in enumerate(text.splitlines(), 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            results.append(f"{f.relative_to(repo_path)}:{i}: {line.strip()}")
                            if len(results) >= 30:
                                break
                except Exception:
                    continue
                if len(results) >= 30:
                    break
            return "\n".join(results) if results else f"Sin resultados para '{pattern}'"

        elif name == "write_context_md":
            output_path = repo_path / "CONTEXT.md"
            # No sobreescribir si ya existe — crear borrador
            if output_path.exists():
                output_path = repo_path / "CONTEXT.draft.md"
                print(f"[!] CONTEXT.md ya existe — guardando como CONTEXT.draft.md")
            output_path.write_text(inputs["content"])
            return f"CONTEXT.md escrito en: {output_path}"

        return f"ERROR: herramienta desconocida '{name}'"

    return execute


def generate_context(repo_path: str) -> str:
    path = Path(repo_path).resolve()
    if not path.exists():
        print(f"ERROR: {repo_path} no existe")
        sys.exit(1)

    print(f"\n[Context Generator] Analizando: {path}")
    print("=" * 60)

    execute = make_executor(path)

    system = """Sos un arquitecto de software analizando un codebase para generar documentación.

Tu objetivo: generar un CONTEXT.md que explique el dominio del proyecto a un ingeniero nuevo
(o a un agente de AI que va a trabajar en este repo).

Proceso:
1. Listá los archivos para entender la estructura
2. Leé el README si existe
3. Identificá los archivos de dominio más importantes (models, entities, domain, types)
4. Buscá los conceptos clave: clases principales, enums de estado, patrones de código
5. Leé los tests para entender el comportamiento esperado
6. Generá el CONTEXT.md con write_context_md

El CONTEXT.md debe incluir:
- Qué hace el sistema (1-2 oraciones)
- Conceptos clave del dominio con sus definiciones
- Reglas del negocio implícitas que encontraste en el código
- Patrones de código que se repiten
- Lo que NO se hace (si podés inferirlo)
- Estructura de directorios con explicación

Sé específico y usa los nombres exactos del código. No inventes términos que no están en el código."""

    messages = [{"role": "user", "content": f"Analizá el repo en {path} y generá el CONTEXT.md"}]
    context_written = False

    for _ in range(30):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            tools=TOOLS,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            if text:
                print(f"\n[Agente]\n{text}")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    first_val = str(list(block.input.values())[0])[:60] if block.input else ""
                    print(f"  → {block.name}({first_val})")
                    result = execute(block.name, block.input)

                    if block.name == "write_context_md":
                        context_written = True

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

    if context_written:
        print(f"\n[✓] CONTEXT.md generado en {path}")
        print("    Revisá y editá el archivo — el agente generó un borrador, vos lo afinás.")
    else:
        print("\n[!] El agente no generó el archivo. Revisá los logs.")

    return str(path / "CONTEXT.md")


if __name__ == "__main__":
    # Por defecto analiza el sample-repo incluido en esta carpeta.
    # Pasá otro path como argumento para analizar tu propio proyecto.
    default_repo = Path(__file__).parent / "sample-repo"
    repo_path = sys.argv[1] if len(sys.argv) > 1 else str(default_repo)
    generate_context(repo_path)
