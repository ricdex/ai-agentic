"""
Módulo 0 — TDD Agent: ciclos verticales RED → GREEN, REFACTOR al final

El agente más disciplinado para calidad de código.

Flujo (tracer bullets — un comportamiento por ciclo):
  1. PLAN:  de la spec extrae la lista de comportamientos observables,
            ordenados del más simple al más complejo
  2. Por cada comportamiento, UN ciclo completo:
       RED:   escribe UN test para ese comportamiento (debe fallar)
       GREEN: escribe el mínimo código para que TODOS los tests pasen
  3. REFACTOR: al final, con todo en verde, mejora el código sin romperlo

Por qué ciclos verticales y no "todos los tests primero":
  - Escribir todos los tests de una vez testea comportamiento IMAGINADO,
    no real — terminás testeando la forma de las cosas (firmas, estructuras)
    en vez del comportamiento observable
  - En ciclos verticales cada test se escribe sabiendo lo que el ciclo
    anterior enseñó — el diseño emerge de a un paso
  - El primer ciclo es el "tracer bullet": el caso más simple que prueba
    el camino completo de punta a punta

Por qué es superior a "escribí código y tests":
  - El agente tiene criterio de "listo" explícito (los tests pasan)
  - No genera código extra (cada línea existe por un test)
  - La refactorización es segura — los tests la protegen

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python tdd_agent.py
"""

import subprocess
import tempfile
import anthropic
from dataclasses import dataclass, field
from pathlib import Path

client = anthropic.Anthropic()

MODEL = "claude-sonnet-4-6"


@dataclass
class TDDSession:
    spec: str
    working_dir: str
    phase: str = "PLAN"  # PLAN → CYCLES → REFACTOR → DONE / FAILED
    tests_file: str = ""
    impl_file: str = ""
    behaviors: list = field(default_factory=list)
    cycles_completed: int = 0
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

PLAN_TOOLS = [
    {
        "name": "list_behaviors",
        "description": (
            "Listá los comportamientos observables que la spec exige, en orden de "
            "implementación. El PRIMERO es el tracer bullet: el caso más simple que "
            "prueba el camino completo. Cada comportamiento se convierte en UN ciclo "
            "RED→GREEN. Describí comportamiento observable ('depositar incrementa el "
            "balance'), no pasos de implementación ('crear el método deposit')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "behaviors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entre 3 y 8 comportamientos, del más simple al más complejo"
                }
            },
            "required": ["behaviors"]
        }
    }
]

RED_TOOLS = [
    {
        "name": "write_test",
        "description": (
            "Escribe UN test nuevo para el comportamiento actual — solo uno. "
            "Entregá el archivo de tests COMPLETO (los tests anteriores intactos + el nuevo). "
            "El test nuevo debe FALLAR porque el comportamiento no está implementado todavía. "
            "Testeá comportamiento observable vía la interfaz pública, no detalles internos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Ej: test_calculator.py (mantener el mismo entre ciclos)"},
                "content": {"type": "string", "description": "Contenido completo del archivo de tests, acumulado"},
                "new_test_name": {"type": "string", "description": "Nombre de la función de test agregada en este ciclo"}
            },
            "required": ["filename", "content", "new_test_name"]
        }
    }
]

GREEN_TOOLS = [
    {
        "name": "write_implementation",
        "description": (
            "Escribe el código de implementación (archivo completo). "
            "Tu objetivo: el mínimo código para que TODOS los tests pasen — "
            "los anteriores y el nuevo. Sin optimizaciones prematuras, "
            "sin anticipar comportamientos de ciclos futuros."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Ej: calculator.py (mantener el mismo entre ciclos)"},
                "content": {"type": "string", "description": "Código de implementación completo"}
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


# --- Fases ---

def plan_behaviors(spec: str) -> list[str]:
    """FASE PLAN: extrae de la spec la lista ordenada de comportamientos."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=PLAN_TOOLS,
        tool_choice={"type": "tool", "name": "list_behaviors"},
        system=(
            "Sos un ingeniero practicando TDD con tracer bullets. "
            "Antes de escribir tests, descomponés la spec en comportamientos "
            "observables — cada uno será un ciclo RED→GREEN independiente."
        ),
        messages=[{
            "role": "user",
            "content": f"Especificación:\n{spec}\n\nListá los comportamientos a implementar, en orden."
        }]
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "list_behaviors":
            return block.input["behaviors"]
    return []


def red_phase(session: TDDSession, behavior: str, cycle_num: int) -> bool:
    """
    FASE RED del ciclo: escribir UN test para el comportamiento, verificar que falla.
    Retorna True si hay un test nuevo en rojo; False si el comportamiento ya
    estaba cubierto (el archivo queda como estaba) o el agente no escribió test.
    """
    tests_content = Path(session.tests_file).read_text() if session.tests_file else ""
    impl_content = Path(session.impl_file).read_text() if session.impl_file else ""

    context_parts = [f"Especificación general:\n{session.spec}"]
    if tests_content:
        context_parts.append(f"Tests existentes (NO los modifiques):\n```python\n{tests_content}\n```")
    if impl_content:
        context_parts.append(f"Implementación actual:\n```python\n{impl_content}\n```")
    context_parts.append(
        f"Comportamiento de ESTE ciclo: {behavior}\n\n"
        "Escribí UN test para este comportamiento. Debe fallar contra la implementación actual."
    )

    messages = [{"role": "user", "content": "\n\n".join(context_parts)}]
    system_red = (
        "Sos un ingeniero practicando TDD en ciclos verticales. Estás en la FASE RED "
        f"del ciclo {cycle_num}. Escribí UN solo test para el comportamiento indicado. "
        "El test describe comportamiento observable vía la interfaz pública — debe "
        "sobrevivir a un refactor interno. NO implementes código de producción."
    )

    for attempt in range(3):
        response = client.messages.create(
            model=MODEL, max_tokens=4096, tools=RED_TOOLS,
            messages=messages, system=system_red
        )
        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type == "tool_use" and block.name == "write_test":
                tests_path = Path(session.working_dir) / block.input["filename"]
                previous_content = tests_path.read_text() if tests_path.exists() else None
                tests_path.write_text(block.input["content"])
                session.tests_file = str(tests_path)

                passed, output = run_tests(str(tests_path), session.working_dir)
                test_name = block.input.get("new_test_name", "?")

                if not passed:
                    print(f"  RED:   {test_name} → falla ✓")
                    return True

                # El test nuevo pasa: el comportamiento ya está cubierto.
                # Restaurar el archivo anterior y saltar el ciclo.
                if previous_content is not None:
                    tests_path.write_text(previous_content)
                print(f"  RED:   {test_name} → ⚠ pasa sin implementar (comportamiento ya cubierto, ciclo omitido)")
                return False

        messages.append({"role": "user", "content": tool_results})

    print("  RED:   [!] el agente no escribió un test")
    return False


def green_phase(session: TDDSession, behavior: str, cycle_num: int) -> bool:
    """
    FASE GREEN del ciclo: mínimo código para que TODOS los tests pasen.
    Retorna True si la suite quedó en verde.
    """
    tests_content = Path(session.tests_file).read_text()
    impl_content = Path(session.impl_file).read_text() if session.impl_file else ""
    impl_note = (
        f"Implementación actual (extendela, no la rompas):\n```python\n{impl_content}\n```"
        if impl_content else "Todavía no hay implementación — este es el primer ciclo."
    )

    messages = [{
        "role": "user",
        "content": (
            f"Tests (el último es el nuevo de este ciclo):\n```python\n{tests_content}\n```\n\n"
            f"{impl_note}\n\n"
            f"Comportamiento de este ciclo: {behavior}\n\n"
            "Escribí el mínimo código para que TODOS los tests pasen."
        )
    }]
    system_green = (
        "Sos un ingeniero practicando TDD en ciclos verticales. Estás en la FASE GREEN "
        f"del ciclo {cycle_num}. Hacé pasar todos los tests con el código MÁS SIMPLE posible. "
        "No optimices. No anticipes comportamientos que todavía no tienen test."
    )

    for attempt in range(4):
        response = client.messages.create(
            model=MODEL, max_tokens=4096, tools=GREEN_TOOLS,
            messages=messages, system=system_green
        )
        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type == "tool_use" and block.name == "write_implementation":
                impl_path = Path(session.working_dir) / block.input["filename"]
                impl_path.write_text(block.input["content"])
                session.impl_file = str(impl_path)

                passed, output = run_tests(session.tests_file, session.working_dir)
                if passed:
                    print(f"  GREEN: {block.input['filename']} → todos los tests pasan ✓")
                    return True

                print(f"  GREEN: ✗ tests fallan (intento {attempt + 1})")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Tests FALLARON:\n{output[-800:]}"
                })

        messages.append({"role": "user", "content": tool_results})

    return False


def refactor_phase(session: TDDSession) -> None:
    """FASE REFACTOR final: mejorar el código con toda la suite en verde."""
    impl_content = Path(session.impl_file).read_text()
    messages = [{
        "role": "user",
        "content": (
            f"Implementación actual (tests en verde):\n```python\n{impl_content}\n```\n\n"
            "Refactorizá el código para mejorarlo. "
            "Enfocate en: legibilidad, eliminar duplicación, nombres claros. "
            "Los tests deben seguir pasando."
        )
    }]
    system_refactor = (
        "Sos un ingeniero practicando TDD. Estás en la FASE REFACTOR — única y final, "
        "con toda la suite en verde. El código funciona. Ahora mejoralo. "
        "Después de cada cambio los tests deben seguir en verde. "
        "Cuando estés satisfecho con la calidad, llamá done()."
    )

    for _ in range(5):
        response = client.messages.create(
            model=MODEL, max_tokens=4096, tools=REFACTOR_TOOLS,
            messages=messages, system=system_refactor
        )
        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "refactor_implementation":
                impl_path = Path(session.impl_file)
                previous_content = impl_path.read_text()
                impl_path.write_text(block.input["content"])

                passed, output = run_tests(session.tests_file, session.working_dir)
                if not passed:
                    # Nunca quedarse en rojo por un refactor: revertir
                    impl_path.write_text(previous_content)
                status = "✓ tests en verde" if passed else "✗ tests rotos — revertido"
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

        messages.append({"role": "user", "content": tool_results})
        if session.phase == "DONE":
            break


def run_tdd_session(spec: str, output_dir: str = None) -> TDDSession:
    """
    Corre la sesión TDD completa: PLAN → ciclos RED→GREEN → REFACTOR.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="tdd_")

    session = TDDSession(spec=spec, working_dir=output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n[TDD Agent] {spec[:80]}")
    print(f"[Working dir] {output_dir}")
    print("=" * 60)

    # === FASE PLAN: descomponer la spec en comportamientos ===
    print("\n--- FASE PLAN: comportamientos a implementar ---")
    session.behaviors = plan_behaviors(spec)
    if not session.behaviors:
        print("[!] El agente no produjo la lista de comportamientos")
        session.phase = "FAILED"
        return session

    for i, b in enumerate(session.behaviors, 1):
        marker = " ← tracer bullet" if i == 1 else ""
        print(f"  {i}. {b}{marker}")

    # === CICLOS VERTICALES: un comportamiento por ciclo ===
    session.phase = "CYCLES"
    total = len(session.behaviors)

    for i, behavior in enumerate(session.behaviors, 1):
        print(f"\n--- CICLO {i}/{total}: {behavior} ---")
        session.iterations += 1

        if not red_phase(session, behavior, i):
            continue  # comportamiento ya cubierto u sin test — siguiente ciclo

        if not green_phase(session, behavior, i):
            print(f"[!] No se logró el verde en el ciclo {i} — sesión abortada")
            session.phase = "FAILED"
            return session

        session.cycles_completed += 1
        session.history.append({"cycle": i, "behavior": behavior})

    if not session.impl_file:
        print("[!] Ningún ciclo produjo implementación")
        session.phase = "FAILED"
        return session

    # === FASE REFACTOR: única, al final, con todo en verde ===
    print("\n--- FASE REFACTOR: mejorar sin romper ---")
    session.phase = "REFACTOR"
    refactor_phase(session)

    # Reporte final
    print("\n" + "=" * 60)
    print(f"[Sesión TDD completada]")
    print(f"  Ciclos:         {session.cycles_completed}/{total} comportamientos implementados")
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
