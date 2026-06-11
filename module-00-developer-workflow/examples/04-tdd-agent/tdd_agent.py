"""
Módulo 0 — TDD Agent: Red → Green → Refactor

El agente más disciplinado para calidad de código.

Flujo:
  1. Recibe una especificación (qué debe hacer la función/clase)
  2. Escribe los tests PRIMERO (todos fallan — RED)
  3. Escribe el código mínimo para que pasen (GREEN)
  4. Refactoriza sin romper tests (REFACTOR)

Por qué es superior a "escribí código y tests":
  - El agente tiene criterio de "listo" explícito
  - No genera código extra (cada línea existe por un test)
  - El diseño emerge de los tests, no al revés
  - La refactorización es segura — los tests la protegen

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python tdd_agent.py
"""

import subprocess
import tempfile
import os
import anthropic
from dataclasses import dataclass, field
from pathlib import Path

client = anthropic.Anthropic()


@dataclass
class TDDSession:
    spec: str
    working_dir: str
    phase: str = "RED"  # RED → GREEN → REFACTOR → DONE
    tests_file: str = ""
    impl_file: str = ""
    iterations: int = 0
    history: list = field(default_factory=list)


def run_tests(tests_file: str, impl_dir: str) -> tuple[bool, str]:
    """Ejecuta pytest y retorna (passed, output)."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", tests_file, "-v", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=30, cwd=impl_dir
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "ERROR: timeout en tests"
    except Exception as e:
        return False, f"ERROR: {e}"


# --- Herramientas por fase ---

RED_TOOLS = [
    {
        "name": "write_tests",
        "description": (
            "Escribe el archivo de tests. Llamá esto cuando tengas listos todos los tests. "
            "Los tests deben cubrir: caso normal, casos borde, casos de error. "
            "NO importes el módulo de implementación todavía — usá una ruta que vas a crear."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Ej: test_calculator.py"},
                "content": {"type": "string", "description": "Contenido completo del archivo de tests"},
                "test_count": {"type": "integer", "description": "Cuántos tests escribiste"}
            },
            "required": ["filename", "content", "test_count"]
        }
    }
]

GREEN_TOOLS = [
    {
        "name": "write_implementation",
        "description": (
            "Escribe el código de implementación. "
            "Tu objetivo: el mínimo código necesario para que los tests pasen. "
            "Sin optimizaciones prematuras, sin features extra."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Ej: calculator.py"},
                "content": {"type": "string", "description": "Código de implementación"}
            },
            "required": ["filename", "content"]
        }
    }
]

REFACTOR_TOOLS = [
    {
        "name": "refactor_implementation",
        "description": (
            "Mejora el código manteniendo los tests en verde. "
            "Enfocate en: legibilidad, eliminar duplicación, nombres claros. "
            "NO agregues features nuevas en este paso."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content": {"type": "string", "description": "Código refactorizado"},
                "changes_summary": {"type": "string", "description": "Qué mejoró y por qué"}
            },
            "required": ["filename", "content", "changes_summary"]
        }
    },
    {
        "name": "done",
        "description": "Declara el ciclo TDD completado. Usá solo cuando los tests pasan y el código es limpio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Resumen del ciclo completo"}
            },
            "required": ["summary"]
        }
    }
]


def run_tdd_session(spec: str, output_dir: str = None) -> TDDSession:
    """
    Corre un ciclo TDD completo para la especificación dada.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="tdd_")

    session = TDDSession(spec=spec, working_dir=output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n[TDD Agent] {spec[:80]}")
    print(f"[Working dir] {output_dir}")
    print("=" * 60)

    # === FASE RED: escribir tests ===
    print("\n--- FASE RED: Escribir tests ---")
    session.phase = "RED"

    messages = [{
        "role": "user",
        "content": (
            f"Especificación:\n{spec}\n\n"
            "Escribí los tests para esta especificación. "
            "Cubrí: caso feliz, casos borde, casos de error. "
            "Los tests deben fallar porque el código no existe todavía — eso es correcto."
        )
    }]

    system_red = (
        "Sos un ingeniero practicando TDD. Estás en la FASE RED. "
        "Tu único objetivo ahora es escribir tests exhaustivos. "
        "NO implementes el código todavía. "
        "Buenos tests = especificación ejecutable del comportamiento esperado."
    )

    tests_written = False
    for _ in range(5):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=RED_TOOLS,
            messages=messages,
            system=system_red
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use" and block.name == "write_tests":
                    tests_content = block.input["content"]
                    tests_filename = block.input["filename"]
                    test_count = block.input.get("test_count", 0)

                    tests_path = Path(output_dir) / tests_filename
                    tests_path.write_text(tests_content)
                    session.tests_file = str(tests_path)

                    # Verificar que los tests FALLAN (como debe ser en RED)
                    passed, output = run_tests(str(tests_path), output_dir)
                    status = "correctamente en RED (fallan)" if not passed else "⚠️ PASAN (no hay implementación?)"
                    print(f"  → Tests escritos: {tests_filename} ({test_count} tests)")
                    print(f"  → Estado: {status}")

                    tests_written = True
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Tests escritos. Estado actual:\n{output[-500:]}"
                    })

            messages.append({"role": "user", "content": tool_results})
            if tests_written:
                break

    if not tests_written:
        print("[!] El agente no escribió tests")
        return session

    # === FASE GREEN: implementar ===
    print("\n--- FASE GREEN: Implementar mínimo ---")
    session.phase = "GREEN"

    tests_content = Path(session.tests_file).read_text()
    messages_green = [{
        "role": "user",
        "content": (
            f"Tests escritos:\n```python\n{tests_content}\n```\n\n"
            "Ahora escribí el código mínimo para que todos los tests pasen. "
            "Solo el código necesario — nada más."
        )
    }]

    system_green = (
        "Sos un ingeniero practicando TDD. Estás en la FASE GREEN. "
        "Tu único objetivo: hacer que los tests pasen con el código MÁS SIMPLE posible. "
        "No optimices todavía. No agregues features extra. Solo hacé que los tests pasen."
    )

    impl_written = False
    for attempt in range(4):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=GREEN_TOOLS,
            messages=messages_green,
            system=system_green
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages_green.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use" and block.name == "write_implementation":
                    impl_path = Path(output_dir) / block.input["filename"]
                    impl_path.write_text(block.input["content"])
                    session.impl_file = str(impl_path)

                    passed, output = run_tests(session.tests_file, output_dir)
                    status = "✓ VERDE" if passed else f"✗ Fallan (intento {attempt + 1})"
                    print(f"  → Implementación: {block.input['filename']}")
                    print(f"  → Tests: {status}")

                    if passed:
                        impl_written = True

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Tests {'PASARON' if passed else 'FALLARON'}:\n{output[-800:]}"
                    })

            messages_green.append({"role": "user", "content": tool_results})
            if impl_written:
                break

    if not impl_written:
        print("[!] No se logró pasar los tests en GREEN")
        session.phase = "FAILED"
        return session

    # === FASE REFACTOR ===
    print("\n--- FASE REFACTOR: Mejorar sin romper ---")
    session.phase = "REFACTOR"

    impl_content = Path(session.impl_file).read_text()
    messages_refactor = [{
        "role": "user",
        "content": (
            f"Implementación actual (tests en verde):\n```python\n{impl_content}\n```\n\n"
            "Refactorizá el código para mejorarlo. "
            "Enfocate en: legibilidad, eliminar duplicación, nombres claros. "
            "Los tests deben seguir pasando."
        )
    }]

    system_refactor = (
        "Sos un ingeniero practicando TDD. Estás en la FASE REFACTOR. "
        "El código funciona. Ahora mejoralo. "
        "Después de cada cambio los tests deben seguir en verde. "
        "Cuando estés satisfecho con la calidad, llamá done()."
    )

    for _ in range(5):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=REFACTOR_TOOLS,
            messages=messages_refactor,
            system=system_refactor
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages_refactor.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "refactor_implementation":
                        impl_path = Path(session.impl_file)
                        impl_path.write_text(block.input["content"])

                        passed, output = run_tests(session.tests_file, output_dir)
                        status = "✓ Tests en verde" if passed else "✗ Tests rotos!"
                        print(f"  → Refactor: {block.input.get('changes_summary', '')[:60]}")
                        print(f"  → {status}")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"{status}\n{output[-400:]}"
                        })

                    elif block.name == "done":
                        print(f"\n  [✓] Refactor completado")
                        print(f"  {block.input.get('summary', '')}")
                        session.phase = "DONE"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Ciclo TDD completado."
                        })

            messages_refactor.append({"role": "user", "content": tool_results})
            if session.phase == "DONE":
                break

    # Reporte final
    print("\n" + "=" * 60)
    print(f"[Ciclo TDD completado]")
    print(f"  Tests:          {session.tests_file}")
    print(f"  Implementación: {session.impl_file}")
    passed, _ = run_tests(session.tests_file, output_dir)
    print(f"  Estado final:   {'✓ VERDE' if passed else '✗ ROJO'}")

    return session


if __name__ == "__main__":
    # Output en ./output/ dentro de esta carpeta.
    # Podés cambiar la spec por cualquiera de las incluidas en specs/.
    output_dir = str(Path(__file__).parent / "output")

    session = run_tdd_session(
        spec="""
        Implementar una clase `BankAccount` con las siguientes reglas:
        - Se inicializa con un balance (default 0)
        - deposit(amount): agrega monto. Lanza ValueError si amount <= 0
        - withdraw(amount): resta monto. Lanza ValueError si amount <= 0 o si excede el balance
        - transfer(amount, target_account): mueve dinero de esta cuenta a otra. Atómico — si falla, ninguna se modifica
        - balance: propiedad de solo lectura
        - El balance nunca puede ser negativo
        """,
        output_dir=output_dir
    )

    print(f"\n[Archivos generados en {output_dir}]")
    for f in Path(output_dir).glob("*.py"):
        lines = f.read_text().count("\n")
        print(f"  {f.name}: {lines} líneas")
