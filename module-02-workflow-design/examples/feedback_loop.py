"""
Módulo 2 — Ejemplo 1: Feedback loop de código

Un agente que escribe código Python para resolver un requerimiento,
lo ejecuta, y si falla itera hasta que funciona o alcanza el límite.

Demuestra:
- Loop con condición de salida
- Análisis del error para mejorar el intento siguiente
- Estado explícito del loop (iteration, last_error, approach)

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python feedback_loop.py
"""

import subprocess
import tempfile
import os
import anthropic
from dataclasses import dataclass, field

client = anthropic.Anthropic()


@dataclass
class LoopState:
    task: str
    iteration: int = 0
    max_iterations: int = 5
    last_code: str = ""
    last_error: str = ""
    last_output: str = ""
    success: bool = False
    history: list = field(default_factory=list)


def execute_python_code(code: str) -> tuple[bool, str, str]:
    """
    Ejecuta código Python en un proceso aislado.
    Retorna (success, stdout, stderr).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["python", tmp_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        success = result.returncode == 0
        return success, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "TIMEOUT: El código tardó más de 10 segundos"
    finally:
        os.unlink(tmp_path)


TOOLS = [
    {
        "name": "submit_code",
        "description": (
            "Envía código Python para ser ejecutado. "
            "El código debe ser completo y ejecutable. "
            "Verás el output y cualquier error. "
            "Usá esta herramienta cuando tengas una solución lista para probar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Código Python completo y ejecutable"
                },
                "explanation": {
                    "type": "string",
                    "description": "Breve explicación de qué hace el código y qué cambió respecto al intento anterior"
                }
            },
            "required": ["code", "explanation"]
        }
    }
]


def build_system_prompt(state: LoopState) -> str:
    history_text = ""
    if state.history:
        history_text = "\n## Intentos anteriores\n"
        for i, attempt in enumerate(state.history, 1):
            history_text += f"\n### Intento {i}\n"
            history_text += f"**Código:**\n```python\n{attempt['code'][:500]}\n```\n"
            history_text += f"**Error:** {attempt['error'][:200]}\n"

    return f"""Sos un ingeniero Python senior resolviendo un problema de código.

Tu tarea: {state.task}

Iteración actual: {state.iteration + 1} de {state.max_iterations}
{history_text}

Instrucciones:
- Escribí código Python completo y ejecutable
- Si hubo errores antes, analizalos y corregí el approach
- No repitas el mismo código que ya falló
- Usá la herramienta submit_code cuando tengas una solución lista
- El código debe terminar imprimiendo el resultado o ejecutando los assertions
"""


def run_feedback_loop(task: str, max_iterations: int = 5) -> LoopState:
    """
    Corre el agente en un loop de feedback hasta que el código funciona
    o se alcanza el límite de iteraciones.
    """
    state = LoopState(task=task, max_iterations=max_iterations)

    print(f"\n[Feedback Loop] Tarea: {task}")
    print("=" * 60)

    while not state.success and state.iteration < state.max_iterations:
        state.iteration += 1
        print(f"\n--- Iteración {state.iteration}/{state.max_iterations} ---")

        # Construir el prompt con el contexto del estado actual
        user_content = task
        if state.last_error:
            user_content = (
                f"Tarea: {task}\n\n"
                f"Tu último intento falló con este error:\n```\n{state.last_error}\n```\n\n"
                f"Analizá el error y corregilo."
            )

        messages = [{"role": "user", "content": user_content}]

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=TOOLS,
            messages=messages,
            system=build_system_prompt(state)
        )

        # Procesar la respuesta
        code_submitted = False
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_code":
                code = block.input["code"]
                explanation = block.input.get("explanation", "")

                print(f"[Submitting] {explanation}")
                print(f"[Code preview] {code[:100]}...")

                success, stdout, stderr = execute_python_code(code)

                if success:
                    print(f"[✓] Código ejecutado exitosamente")
                    print(f"[Output] {stdout[:200]}")
                    state.success = True
                    state.last_code = code
                    state.last_output = stdout
                else:
                    print(f"[✗] Falló: {stderr[:200]}")
                    state.history.append({
                        "code": code,
                        "error": stderr or stdout
                    })
                    state.last_error = stderr or stdout
                    state.last_code = code

                code_submitted = True
                break

        if not code_submitted:
            print("[!] El agente no sometió código — terminando")
            break

    # Reporte final
    print("\n" + "=" * 60)
    if state.success:
        print(f"[✓] ÉXITO en iteración {state.iteration}/{state.max_iterations}")
        print(f"[Output final]\n{state.last_output}")
    else:
        print(f"[✗] FALLÓ después de {state.iteration} iteraciones")
        print(f"[Último error] {state.last_error[:300]}")

    return state


if __name__ == "__main__":
    # Tarea 1: algo relativamente simple
    state1 = run_feedback_loop(
        task=(
            "Escribí una función merge_sorted_lists(a, b) que une dos listas "
            "ya ordenadas en una sola lista ordenada, sin usar sorted(). "
            "Incluí assertions que verifiquen que funciona con casos borde: "
            "listas vacías, un elemento, elementos duplicados."
        )
    )

    print("\n\n")

    # Tarea 2: algo con un error de diseño que requiere iterar
    state2 = run_feedback_loop(
        task=(
            "Escribí código que calcule el número de Fibonacci n=40 usando "
            "memoización con functools.lru_cache, y que NO tarde más de 1 segundo. "
            "Imprimí el resultado con un assert que verifique que fib(40) == 102334155."
        )
    )
