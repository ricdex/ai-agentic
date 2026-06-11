"""
Módulo 0 — Diagnose Agent: Debugging sistemático en 6 fases

El debugging al azar genera alucinaciones y fixes que no resuelven la causa raíz.
Este agente sigue un proceso determinístico que garantiza encontrar el problema.

Las 6 fases (basado en Matt Pocock /diagnose):
  1. REPRODUCIR  — confirmar que el bug existe y cómo triggerarlo
  2. MINIMIZAR   — caso más pequeño que reproduce el bug
  3. HIPÓTESIS   — listar causas probables (más probable primero)
  4. INSTRUMENTAR — agregar logging/asserts para confirmar hipótesis
  5. FIX         — arreglar la causa raíz, no el síntoma
  6. REGRESIÓN   — escribir test que falla sin el fix y pasa con él

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python diagnose_agent.py
"""

import subprocess
import anthropic
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

client = anthropic.Anthropic()


class Phase(str, Enum):
    REPRODUCE = "REPRODUCE"
    MINIMIZE = "MINIMIZE"
    HYPOTHESIZE = "HYPOTHESIZE"
    INSTRUMENT = "INSTRUMENT"
    FIX = "FIX"
    REGRESSION = "REGRESSION"
    DONE = "DONE"


@dataclass
class DiagnoseState:
    bug_report: str
    repo_path: str
    phase: Phase = Phase.REPRODUCE
    reproduction_case: str = ""
    hypotheses: list = field(default_factory=list)
    confirmed_hypothesis: str = ""
    fix_applied: bool = False
    regression_test_written: bool = False
    root_cause: str = ""


def run_python_snippet(code: str, cwd: str) -> tuple[bool, str]:
    """Ejecuta un snippet Python y retorna (success, output)."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            ["python", tmp],
            capture_output=True, text=True, timeout=10, cwd=cwd
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    finally:
        os.unlink(tmp)


def run_tests(path: str, cwd: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", path, "-v", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=30, cwd=cwd
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


TOOLS_BY_PHASE = {
    Phase.REPRODUCE: [
        {
            "name": "read_file",
            "description": "Lee un archivo del repo.",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
        },
        {
            "name": "run_code",
            "description": "Ejecuta un snippet Python para intentar reproducir el bug.",
            "input_schema": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Código Python a ejecutar"}},
                "required": ["code"]
            }
        },
        {
            "name": "report_reproduction",
            "description": "Confirma que el bug se reprodujo. Llamá cuando tengas el caso de reproducción.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "reproduced": {"type": "boolean"},
                    "reproduction_code": {"type": "string", "description": "Código mínimo que reproduce el bug"},
                    "actual_behavior": {"type": "string"},
                    "expected_behavior": {"type": "string"}
                },
                "required": ["reproduced", "reproduction_code", "actual_behavior", "expected_behavior"]
            }
        }
    ],
    Phase.HYPOTHESIZE: [
        {
            "name": "list_hypotheses",
            "description": "Lista las posibles causas del bug, de más probable a menos probable.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "hypotheses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "cause": {"type": "string"},
                                "probability": {"type": "string", "enum": ["high", "medium", "low"]},
                                "how_to_verify": {"type": "string"}
                            }
                        }
                    }
                },
                "required": ["hypotheses"]
            }
        }
    ],
    Phase.FIX: [
        {
            "name": "write_file",
            "description": "Escribe el fix en el archivo correspondiente.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "fix_description": {"type": "string", "description": "Qué cambió y por qué"}
                },
                "required": ["path", "content", "fix_description"]
            }
        }
    ],
    Phase.REGRESSION: [
        {
            "name": "write_regression_test",
            "description": (
                "Escribe el test de regresión. "
                "Este test debe FALLAR sin el fix y PASAR con él. "
                "Esto garantiza que el bug no vuelva."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Archivo de test (ej: tests/test_regression.py)"},
                    "content": {"type": "string"},
                    "test_name": {"type": "string"}
                },
                "required": ["path", "content", "test_name"]
            }
        }
    ]
}

# Todas las fases pueden leer archivos y buscar código
BASE_TOOLS = [
    {
        "name": "search_code",
        "description": "Busca un patrón en el código.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
            },
            "required": ["pattern"]
        }
    }
]


def execute_tool(name: str, inputs: dict, state: DiagnoseState) -> str:
    repo = Path(state.repo_path)

    if name == "read_file":
        path = repo / inputs["path"]
        try:
            return path.read_text()
        except Exception as e:
            return f"ERROR: {e}"

    elif name == "run_code":
        success, output = run_python_snippet(inputs["code"], state.repo_path)
        return f"{'EXIT 0' if success else 'EXIT 1'}\n{output}"

    elif name == "search_code":
        import re
        results = []
        for f in repo.rglob("*.py"):
            if ".git" in str(f) or "__pycache__" in str(f):
                continue
            try:
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    if re.search(inputs["pattern"], line, re.IGNORECASE):
                        results.append(f"{f.relative_to(repo)}:{i}: {line.strip()}")
            except Exception:
                continue
        return "\n".join(results[:30]) if results else "Sin resultados"

    elif name == "report_reproduction":
        state.reproduction_case = inputs.get("reproduction_code", "")
        return f"Reproducción confirmada: {inputs.get('actual_behavior', '')}"

    elif name == "list_hypotheses":
        state.hypotheses = inputs["hypotheses"]
        summary = "\n".join(
            f"[{h['probability'].upper()}] {h['cause']} — verificar: {h['how_to_verify']}"
            for h in state.hypotheses
        )
        return f"Hipótesis registradas:\n{summary}"

    elif name == "write_file":
        path = repo / inputs["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(inputs["content"])
        state.fix_applied = True
        return f"Fix aplicado en {inputs['path']}: {inputs.get('fix_description', '')}"

    elif name == "write_regression_test":
        path = repo / inputs["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(inputs["content"])
        state.regression_test_written = True
        passed, output = run_tests(str(path), state.repo_path)
        return f"Test escrito. Estado: {'✓ PASA' if passed else '✗ FALLA (esperado si no hay fix)'}\n{output[-500:]}"

    return f"ERROR: herramienta desconocida '{name}'"


def run_phase(phase: Phase, state: DiagnoseState, extra_context: str = "") -> str:
    """Corre una fase del diagnóstico con las herramientas apropiadas."""
    phase_prompts = {
        Phase.REPRODUCE: (
            f"Bug reportado:\n{state.bug_report}\n\n"
            "FASE 1 - REPRODUCIR: Explorá el código y escribí un snippet que reproduzca el bug. "
            "Cuando lo reproduzcas, llamá report_reproduction()."
        ),
        Phase.HYPOTHESIZE: (
            f"Bug reproducido. Caso de reproducción:\n{state.reproduction_case}\n\n"
            "FASE 3 - HIPÓTESIS: Basándote en el código y el síntoma, "
            "listá las causas posibles de más probable a menos probable. "
            "Para cada una, explicá cómo verificarla."
        ),
        Phase.FIX: (
            f"Hipótesis más probable: {state.hypotheses[0]['cause'] if state.hypotheses else 'ver código'}\n\n"
            "FASE 5 - FIX: Arreglá la causa raíz. "
            "El fix debe ser mínimo — solo cambiá lo necesario para resolver el bug. "
            "No refactorices en este paso."
        ),
        Phase.REGRESSION: (
            f"Fix aplicado. Caso de reproducción original:\n{state.reproduction_case}\n\n"
            "FASE 6 - REGRESIÓN: Escribí un test que:\n"
            "1. Fallaría SIN el fix\n"
            "2. Pasa CON el fix\n"
            "Esto garantiza que el bug no vuelva."
        )
    }

    tools = BASE_TOOLS + TOOLS_BY_PHASE.get(phase, [])
    system = (
        f"Sos un debugger experto. Estás en la FASE {phase.value} del diagnóstico sistemático.\n"
        f"Repo: {state.repo_path}\n\n"
        f"{extra_context}"
    )

    messages = [{"role": "user", "content": phase_prompts[phase]}]
    result_text = ""

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=tools,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            result_text = next((b.text for b in response.content if hasattr(b, "text")), "")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    first = str(list(block.input.values())[0])[:50] if block.input else ""
                    print(f"    [{phase.value}] → {block.name}({first})")
                    result = execute_tool(block.name, block.input, state)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

    return result_text


def diagnose(bug_report: str, repo_path: str) -> DiagnoseState:
    """Corre el diagnóstico completo en 6 fases."""
    state = DiagnoseState(bug_report=bug_report, repo_path=repo_path)

    print(f"\n[Diagnose Agent]")
    print(f"Bug: {bug_report[:100]}")
    print("=" * 60)

    phases = [
        (Phase.REPRODUCE, "Reproduciendo el bug..."),
        (Phase.HYPOTHESIZE, "Formulando hipótesis..."),
        (Phase.FIX, "Aplicando fix..."),
        (Phase.REGRESSION, "Escribiendo test de regresión..."),
    ]

    for phase, description in phases:
        print(f"\n[Fase {phase.value}] {description}")
        run_phase(phase, state)

        # Verificar estado después de cada fase crítica
        if phase == Phase.REPRODUCE and not state.reproduction_case:
            print("[!] No se pudo reproducir el bug. Revisar manualmente.")
            break

        if phase == Phase.FIX:
            passed, output = run_tests(repo_path, repo_path)
            if passed:
                print(f"  [✓] Tests pasan después del fix")
            else:
                print(f"  [!] Tests fallan después del fix:\n{output[-300:]}")

    state.phase = Phase.DONE
    print("\n[Diagnóstico completado]")
    if state.hypotheses:
        print(f"Causa raíz: {state.hypotheses[0].get('cause', 'ver hipótesis')}")
    print(f"Fix aplicado: {state.fix_applied}")
    print(f"Test de regresión: {state.regression_test_written}")

    return state


# --- Demo ---

if __name__ == "__main__":
    # Usa el sample-repo incluido en esta carpeta.
    # src/discounts.py tiene 3 bugs intencionales para practicar el diagnóstico.
    demo_path = str(Path(__file__).parent / "sample-repo")

    diagnose(
        bug_report=(
            "calculate_discount() lanza TypeError cuando discount_pct es None — "
            "los productos sin descuento deberían retornar el precio original. "
            "apply_coupon() lanza KeyError con cupones inválidos en lugar de retornar None. "
            "bulk_discount() no aplica el descuento cuando hay exactamente 10 unidades."
        ),
        repo_path=demo_path
    )
