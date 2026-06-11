"""
Módulo 3 — Issue Solver Agent

Agente que resuelve un issue de GitHub en un repo local:
1. Analiza el issue (título + descripción)
2. Explora el repo para entender el contexto
3. Escribe el fix
4. Corre los tests
5. Si fallan, itera (máx 3 veces)
6. Retorna un resumen listo para abrir un PR

Usa prompt caching para reducir costos en iteraciones múltiples.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python issue_solver.py
"""

import os
import re
import subprocess
import anthropic
from pathlib import Path
from dataclasses import dataclass, field

client = anthropic.Anthropic()


@dataclass
class IssueContext:
    title: str
    description: str
    repo_path: str


@dataclass
class SolverState:
    issue: IssueContext
    iteration: int = 0
    max_iterations: int = 3
    files_written: list = field(default_factory=list)
    test_output: str = ""
    success: bool = False
    pr_summary: str = ""


# --- Herramientas del agente ---

TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo del repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta relativa al repo"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": (
            "Escribe o modifica un archivo. "
            "Siempre escribí el archivo completo, no solo el fragmento modificado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta relativa al repo"},
                "content": {"type": "string", "description": "Contenido completo del archivo"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "search_code",
        "description": "Busca un patrón en los archivos del repo. Útil para encontrar dónde está definida una función.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Texto o regex a buscar"},
                "file_extension": {
                    "type": "string",
                    "description": "Extensión de archivo (ej: '.py', '.ts'). Por defecto busca en todos.",
                    "default": ""
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "list_files",
        "description": "Lista los archivos de un directorio (recursivo, excluye .git y __pycache__).",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directorio relativo al repo"}
            },
            "required": ["directory"]
        }
    },
    {
        "name": "run_tests",
        "description": (
            "Corre los tests del repo y retorna el resultado. "
            "Usá esto para verificar que tu fix no rompe nada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "test_path": {
                    "type": "string",
                    "description": "Ruta a un test específico o directorio. Vacío para correr todos.",
                    "default": ""
                }
            },
            "required": []
        }
    }
]


def make_tool_executor(repo_path: str, state: SolverState):
    """Crea el executor con el repo_path como closure."""

    def execute(name: str, inputs: dict) -> str:
        base = Path(repo_path)

        if name == "read_file":
            path = base / inputs["path"]
            try:
                return path.read_text()
            except FileNotFoundError:
                return f"ERROR: Archivo no encontrado: {inputs['path']}"
            except Exception as e:
                return f"ERROR: {e}"

        elif name == "write_file":
            path = base / inputs["path"]
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(inputs["content"])
                state.files_written.append(inputs["path"])
                return f"Archivo escrito: {inputs['path']}"
            except Exception as e:
                return f"ERROR: {e}"

        elif name == "search_code":
            pattern = inputs["pattern"]
            ext = inputs.get("file_extension", "")
            results = []
            try:
                glob = f"**/*{ext}" if ext else "**/*"
                for f in base.rglob(glob if not ext else f"**/*{ext}"):
                    if f.is_file() and ".git" not in str(f) and "__pycache__" not in str(f):
                        try:
                            content = f.read_text(errors="ignore")
                            for i, line in enumerate(content.splitlines(), 1):
                                if re.search(pattern, line, re.IGNORECASE):
                                    rel = str(f.relative_to(base))
                                    results.append(f"{rel}:{i}: {line.strip()}")
                        except Exception:
                            continue
            except Exception as e:
                return f"ERROR: {e}"

            if not results:
                return f"Sin resultados para '{pattern}'"
            return "\n".join(results[:40])

        elif name == "list_files":
            directory = base / inputs.get("directory", ".")
            try:
                files = []
                for f in sorted(directory.rglob("*")):
                    if ".git" in str(f) or "__pycache__" in str(f):
                        continue
                    rel = str(f.relative_to(base))
                    kind = "📁" if f.is_dir() else "📄"
                    files.append(f"{kind} {rel}")
                return "\n".join(files[:100]) or "Directorio vacío"
            except Exception as e:
                return f"ERROR: {e}"

        elif name == "run_tests":
            test_path = inputs.get("test_path", "")
            target = str(base / test_path) if test_path else str(base)
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", target, "-v", "--tb=short", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(base)
                )
                output = result.stdout + result.stderr
                state.test_output = output
                return output[-4000:] if len(output) > 4000 else output
            except subprocess.TimeoutExpired:
                return "ERROR: Tests tardaron más de 60s"
            except FileNotFoundError:
                return "ERROR: pytest no encontrado. pip install pytest"
            except Exception as e:
                return f"ERROR: {e}"

        return f"ERROR: herramienta desconocida '{name}'"

    return execute


def build_system_prompt(state: SolverState) -> list:
    """
    Construye el system prompt con caching.
    El contexto estático del issue se cachea para ahorrar tokens en iteraciones.
    """
    static_context = f"""Sos un ingeniero de software senior resolviendo un issue de GitHub.

## Issue a resolver
**Título:** {state.issue.title}
**Descripción:**
{state.issue.description}

## Tu proceso
1. Primero explorá la estructura del repo (list_files)
2. Buscá los archivos relevantes al issue (search_code)
3. Leé los archivos que necesitás entender
4. Escribí el fix (write_file) — siempre el archivo completo
5. Corré los tests (run_tests)
6. Si fallan, analizá el error y corregí

## Reglas
- No inventes código sin leer los archivos primero
- Siempre corré los tests antes de declarar éxito
- Cuando termines, escribí un resumen de los cambios (para el PR)
"""

    return [
        {
            "type": "text",
            "text": static_context,
            "cache_control": {"type": "ephemeral"}  # Se cachea entre iteraciones
        }
    ]


def solve_issue(issue: IssueContext) -> SolverState:
    """Loop principal del agente."""
    state = SolverState(issue=issue)
    execute_tool = make_tool_executor(issue.repo_path, state)

    print(f"\n[Issue Solver] {issue.title}")
    print(f"[Repo] {issue.repo_path}")
    print("=" * 60)

    # Mensaje inicial
    messages = [{
        "role": "user",
        "content": (
            f"Resolvé este issue:\n\n"
            f"**{issue.title}**\n\n{issue.description}\n\n"
            f"El repo está en: {issue.repo_path}"
        )
    }]

    outer_iteration = 0
    while not state.success and outer_iteration < state.max_iterations:
        outer_iteration += 1
        print(f"\n[Ciclo {outer_iteration}/{state.max_iterations}]")

        # Si hay un error de tests previo, agregarlo al contexto
        if state.test_output and "failed" in state.test_output.lower():
            messages.append({
                "role": "user",
                "content": (
                    f"Los tests fallaron. Analizá el error y corregí:\n\n"
                    f"```\n{state.test_output[-2000:]}\n```"
                )
            })

        inner_done = False
        inner_iter = 0

        while not inner_done and inner_iter < 20:
            inner_iter += 1

            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8096,
                tools=TOOLS,
                messages=messages,
                system=build_system_prompt(state)
            )

            if response.stop_reason == "end_turn":
                text = next((b.text for b in response.content if hasattr(b, "text")), "")
                print(f"\n[Agente]\n{text[:500]}")
                state.pr_summary = text
                inner_done = True

                # Verificar si ya corrió tests exitosamente
                if "passed" in state.test_output.lower() and "failed" not in state.test_output.lower():
                    state.success = True

            elif response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        first_val = list(block.input.values())[0][:50] if block.input else ""
                        print(f"  → {block.name}({first_val})")

                        result = execute_tool(block.name, block.input)

                        # Si los tests pasaron, marcar éxito
                        if block.name == "run_tests":
                            if "passed" in result and "failed" not in result and "error" not in result.lower():
                                state.success = True
                                print(f"  [✓] Tests pasaron!")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                messages.append({"role": "user", "content": tool_results})

    # Reporte final
    print("\n" + "=" * 60)
    if state.success:
        print(f"[✓] Issue resuelto en {outer_iteration} ciclo(s)")
        print(f"[Archivos modificados] {state.files_written}")
        print(f"\n[PR Summary]\n{state.pr_summary[:600]}")
    else:
        print(f"[✗] No se pudo resolver después de {outer_iteration} ciclos")
        print(f"[Último error de tests]\n{state.test_output[-500:]}")

    return state


# --- Demo: crear un repo con un bug para que el agente resuelva ---

def create_demo_repo(path: str):
    """Crea un mini-repo con un bug conocido."""
    os.makedirs(f"{path}/src", exist_ok=True)
    os.makedirs(f"{path}/tests", exist_ok=True)

    Path(f"{path}/src/__init__.py").write_text("")
    Path(f"{path}/tests/__init__.py").write_text("")

    # El bug: Stack usa una list pero pop() saca del final, no del frente
    Path(f"{path}/src/stack.py").write_text('''
class Stack:
    """Una pila (LIFO) con operaciones básicas."""

    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        if self.is_empty():
            raise IndexError("Stack is empty")
        # BUG: debería ser pop() sin argumento, no pop(0)
        # pop(0) hace que se comporte como una queue (FIFO), no una stack (LIFO)
        return self._items.pop(0)

    def peek(self):
        if self.is_empty():
            raise IndexError("Stack is empty")
        return self._items[-1]

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def size(self) -> int:
        return len(self._items)
''')

    Path(f"{path}/tests/test_stack.py").write_text('''
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.stack import Stack

def test_lifo_order():
    """Una stack debe retornar elementos en orden LIFO (último en entrar, primero en salir)."""
    s = Stack()
    s.push(1)
    s.push(2)
    s.push(3)
    assert s.pop() == 3, "pop() debe retornar el último elemento pusheado (LIFO)"
    assert s.pop() == 2
    assert s.pop() == 1

def test_pop_empty_raises():
    s = Stack()
    try:
        s.pop()
        assert False, "Debería haber lanzado IndexError"
    except IndexError:
        pass

def test_peek_does_not_remove():
    s = Stack()
    s.push(42)
    assert s.peek() == 42
    assert s.size() == 1, "peek() no debe remover el elemento"

def test_is_empty():
    s = Stack()
    assert s.is_empty()
    s.push(1)
    assert not s.is_empty()
''')


if __name__ == "__main__":
    demo_path = "/tmp/demo_repo"
    create_demo_repo(demo_path)

    result = solve_issue(IssueContext(
        title="Bug: Stack.pop() retorna el primer elemento en lugar del último",
        description=(
            "La implementación de Stack.pop() tiene un bug: "
            "retorna el primer elemento insertado (comportamiento FIFO) "
            "en lugar del último (comportamiento LIFO esperado en una Stack). "
            "\n\n"
            "Pasos para reproducir:\n"
            "1. Crear una Stack\n"
            "2. push(1), push(2), push(3)\n"
            "3. pop() retorna 1 en lugar de 3\n\n"
            "El test test_lifo_order() falla."
        ),
        repo_path=demo_path
    ))
