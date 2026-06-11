"""
Módulo 1 — Ejemplo 2: Tool use avanzado

Un agente de análisis de código con múltiples herramientas:
- Leer archivos
- Buscar en código (grep)
- Ejecutar tests
- Escribir un reporte

Demuestra:
- Cómo diseñar herramientas con buenas descripciones
- Cómo el agente encadena múltiples herramientas
- Manejo de errores en herramientas

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 02_tool_use.py
"""

import os
import re
import subprocess
import anthropic
from pathlib import Path

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Lee el contenido completo de un archivo de código. "
            "Usá esto cuando necesités ver la implementación de una función o clase."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del archivo"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_code",
        "description": (
            "Busca un patrón de texto en todos los archivos Python de un directorio. "
            "Usá esto para encontrar dónde se define o usa una función/clase/variable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Patrón regex o texto a buscar"},
                "directory": {"type": "string", "description": "Directorio donde buscar"}
            },
            "required": ["pattern", "directory"]
        }
    },
    {
        "name": "run_tests",
        "description": (
            "Ejecuta los tests de un archivo o directorio con pytest. "
            "Retorna el output con los tests que pasaron y fallaron."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Archivo o directorio de tests"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_python_files",
        "description": "Lista todos los archivos .py en un directorio (recursivo).",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string"}
            },
            "required": ["directory"]
        }
    }
]


def read_file(path: str) -> str:
    try:
        return Path(path).read_text()
    except Exception as e:
        return f"ERROR: {e}"


def search_code(pattern: str, directory: str) -> str:
    results = []
    try:
        for py_file in Path(directory).rglob("*.py"):
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(pattern, line):
                    results.append(f"{py_file}:{i}: {line.strip()}")
    except Exception as e:
        return f"ERROR: {e}"

    if not results:
        return f"Sin resultados para '{pattern}' en {directory}"
    return "\n".join(results[:50])  # límite de 50 resultados


def run_tests(path: str) -> str:
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout + result.stderr
        return output[-3000:] if len(output) > 3000 else output
    except FileNotFoundError:
        return "ERROR: pytest no encontrado. Instalá con: pip install pytest"
    except subprocess.TimeoutExpired:
        return "ERROR: Tests tardaron más de 30 segundos"
    except Exception as e:
        return f"ERROR: {e}"


def list_python_files(directory: str) -> str:
    try:
        files = list(Path(directory).rglob("*.py"))
        return "\n".join(str(f) for f in files) if files else "No hay archivos .py"
    except Exception as e:
        return f"ERROR: {e}"


def execute_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "read_file": lambda: read_file(inputs["path"]),
        "search_code": lambda: search_code(inputs["pattern"], inputs["directory"]),
        "run_tests": lambda: run_tests(inputs["path"]),
        "list_python_files": lambda: list_python_files(inputs["directory"]),
    }
    handler = dispatch.get(name)
    if not handler:
        return f"ERROR: Herramienta desconocida '{name}'"
    return handler()


def analyze_codebase(task: str, working_dir: str) -> str:
    """Agente de análisis: acepta una tarea y trabaja en un directorio dado."""
    messages = [{"role": "user", "content": f"Directorio de trabajo: {working_dir}\n\nTarea: {task}"}]

    system = (
        "Sos un ingeniero de software senior analizando una codebase. "
        "Antes de responder, explorá el código para entender cómo funciona. "
        "Sé específico: citá archivos y líneas de código cuando sea posible. "
        "Si encontrás bugs, explicá exactamente qué está mal y por qué."
    )

    print(f"\n[Análisis] {task}")
    print("=" * 60)

    iteration = 0
    while iteration < 15:
        iteration += 1

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=TOOLS,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            print(f"\n[Resultado]\n{text}")
            return text

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [{iteration}] {block.name}({list(block.input.values())[0] if block.input else ''})")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

    return "ERROR: Límite de iteraciones alcanzado"


# --- Setup del demo ---

def create_demo_project(base_dir: str):
    """Crea un mini-proyecto con un bug intencional para que el agente encuentre."""
    os.makedirs(f"{base_dir}/src", exist_ok=True)
    os.makedirs(f"{base_dir}/tests", exist_ok=True)

    Path(f"{base_dir}/src/cart.py").write_text('''
class ShoppingCart:
    def __init__(self):
        self.items = []

    def add_item(self, name: str, price: float, quantity: int = 1):
        self.items.append({"name": name, "price": price, "quantity": quantity})

    def get_total(self) -> float:
        # BUG: no multiplica precio por cantidad
        return sum(item["price"] for item in self.items)

    def apply_discount(self, percent: float) -> float:
        if percent < 0 or percent > 100:
            raise ValueError("El descuento debe estar entre 0 y 100")
        return self.get_total() * (1 - percent / 100)
''')

    Path(f"{base_dir}/tests/test_cart.py").write_text('''
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cart import ShoppingCart

def test_total_with_quantity():
    cart = ShoppingCart()
    cart.add_item("Widget", 10.0, quantity=3)
    assert cart.get_total() == 30.0, f"Expected 30.0, got {cart.get_total()}"

def test_discount():
    cart = ShoppingCart()
    cart.add_item("Widget", 100.0, quantity=1)
    assert cart.apply_discount(10) == 90.0

def test_invalid_discount():
    cart = ShoppingCart()
    cart.add_item("Widget", 50.0)
    try:
        cart.apply_discount(150)
        assert False, "Debería haber lanzado ValueError"
    except ValueError:
        pass
''')


if __name__ == "__main__":
    demo_dir = "/tmp/demo_project"
    create_demo_project(demo_dir)

    # El agente debe encontrar el bug en get_total()
    analyze_codebase(
        task=(
            "Analizá el proyecto. Ejecutá los tests y si fallan, "
            "identificá exactamente cuál es el bug, en qué archivo y línea, "
            "y explicá cómo arreglarlo."
        ),
        working_dir=demo_dir
    )
