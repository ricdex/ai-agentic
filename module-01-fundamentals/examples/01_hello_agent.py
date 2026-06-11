"""
Módulo 1 — Ejemplo 1: El agente más simple posible

Un agente que puede leer archivos y responder preguntas sobre código.
Demuestra el loop básico: tool_use → ejecutar herramienta → continuar.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 01_hello_agent.py
"""

import os
import json
import anthropic

client = anthropic.Anthropic()

# --- Herramientas disponibles para el agente ---

TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo. Usá esta herramienta cuando necesités ver el código de un archivo específico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a leer (relativa al directorio actual)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_files",
        "description": "Lista los archivos en un directorio. Usá esta herramienta para explorar la estructura del proyecto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directorio a listar. Usá '.' para el directorio actual."
                }
            },
            "required": ["directory"]
        }
    }
]


def read_file(path: str) -> str:
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return f"ERROR: Archivo '{path}' no encontrado"
    except Exception as e:
        return f"ERROR: {e}"


def list_files(directory: str) -> str:
    try:
        files = []
        for entry in os.scandir(directory):
            kind = "dir" if entry.is_dir() else "file"
            files.append(f"{kind}: {entry.name}")
        return "\n".join(files) if files else "Directorio vacío"
    except Exception as e:
        return f"ERROR: {e}"


def execute_tool(name: str, inputs: dict) -> str:
    """Despacha la herramienta correcta según el nombre."""
    if name == "read_file":
        return read_file(inputs["path"])
    elif name == "list_files":
        return list_files(inputs["directory"])
    else:
        return f"ERROR: Herramienta desconocida '{name}'"


# --- El loop del agente ---

def run_agent(question: str, max_iterations: int = 10) -> str:
    """
    Corre el agente hasta que responde o alcanza el límite de iteraciones.

    El loop es simple:
    1. Enviar mensajes a Claude con las herramientas disponibles
    2. Si Claude quiere usar una herramienta → ejecutarla y continuar
    3. Si Claude termina (end_turn) → retornar la respuesta
    """
    messages = [
        {"role": "user", "content": question}
    ]

    print(f"\n[Agente] Pregunta: {question}")
    print("-" * 50)

    for iteration in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=TOOLS,
            messages=messages,
            system=(
                "Sos un asistente que responde preguntas sobre código. "
                "Usá las herramientas disponibles para explorar archivos antes de responder. "
                "Si no encontrás lo que buscás, decí explícitamente qué buscaste y que no lo encontraste. "
                "Nunca inventes código que no leíste."
            )
        )

        # Claude terminó — tenemos la respuesta final
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n[Agente] Respuesta final:\n{block.text}")
                    return block.text
            return "Sin respuesta de texto"

        # Claude quiere usar herramientas
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"  → Usando herramienta: {block.name}({json.dumps(block.input)})")
                    result = execute_tool(block.name, block.input)
                    print(f"  ← Resultado: {result[:100]}{'...' if len(result) > 100 else ''}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            # Agregar la respuesta del asistente y los resultados al historial
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    return "ERROR: Alcancé el límite de iteraciones sin respuesta"


# --- Demo ---

if __name__ == "__main__":
    # Creamos un archivo de ejemplo para que el agente lo analice
    demo_code = '''
def calculate_tax(income: float, rate: float = 0.21) -> float:
    """Calcula el impuesto sobre el ingreso."""
    if income < 0:
        raise ValueError("El ingreso no puede ser negativo")
    return income * rate

def calculate_net_income(gross: float) -> float:
    """Calcula el ingreso neto después de impuestos."""
    tax = calculate_tax(gross)
    return gross - tax
'''

    with open("/tmp/finance.py", "w") as f:
        f.write(demo_code)

    # Pregunta 1: función que existe
    run_agent("¿Qué hace la función calculate_tax en /tmp/finance.py? ¿Qué parámetros acepta?")

    # Pregunta 2: función que NO existe (debe decir que no la encontró)
    run_agent("¿Existe una función llamada send_invoice en /tmp/finance.py?")
