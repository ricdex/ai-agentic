"""
Módulo 10 — Ejemplo 1: Suite de evals determinísticas

Implementa un framework de evaluación para el agente del módulo 3.
Evals determinísticas: resultados objetivos sin ambigüedad.

Métricas evaluadas:
- ¿Los tests pasan después del fix?
- ¿Cuántas iteraciones necesitó?
- ¿Cuántos archivos tocó?
- ¿Cuál fue el costo en USD?

El script también genera un reporte de comparación si se le da
un baseline previo (para detectar regresiones).

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 01_basic_eval.py
    python 01_basic_eval.py --save-baseline  # guarda resultados como baseline
    python 01_basic_eval.py --compare        # compara con baseline guardado
"""

import sys
import json
import time
import subprocess
import tempfile
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
import anthropic

client = anthropic.Anthropic()
BASELINE_PATH = Path("/tmp/agent_eval_baseline.json")


@dataclass
class EvalCase:
    id: str
    description: str
    buggy_code: str          # código con el bug
    test_code: str           # tests que deben pasar
    expected_fix_hint: str   # descripción del fix correcto (para referencia)


@dataclass
class EvalResult:
    case_id: str
    tests_passed: bool
    iterations: int
    files_changed: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None = None

    @property
    def score(self) -> float:
        if not self.tests_passed:
            return 0.0
        # Penalizar iteraciones excesivas
        iter_penalty = max(0.0, (self.iterations - 1) * 0.1)
        # Penalizar cambios excesivos de archivos
        file_penalty = max(0.0, (self.files_changed - 1) * 0.15)
        return max(0.0, 1.0 - iter_penalty - file_penalty)


@dataclass
class EvalReport:
    results: list[EvalResult]
    total_cost_usd: float
    elapsed_seconds: float

    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.tests_passed) / len(self.results)

    def print_summary(self, label: str = ""):
        print(f"\n{'=' * 50}")
        print(f"EVAL REPORT {label}")
        print(f"{'=' * 50}")
        print(f"  Pass rate:   {self.pass_rate():.0%} ({sum(1 for r in self.results if r.tests_passed)}/{len(self.results)})")
        print(f"  Avg score:   {self.avg_score():.3f}")
        print(f"  Total cost:  ${self.total_cost_usd:.4f}")
        print(f"  Time:        {self.elapsed_seconds:.1f}s")
        print()

        for r in self.results:
            status = "✓" if r.tests_passed else "✗"
            print(f"  {status} [{r.case_id}] score={r.score:.2f} "
                  f"iter={r.iterations} cost=${r.cost_usd:.4f}"
                  + (f" ERROR: {r.error}" if r.error else ""))


# --- Casos de eval ---

EVAL_CASES = [
    EvalCase(
        id="off-by-one",
        description="Bug off-by-one en búsqueda binaria",
        buggy_code="""
def binary_search(arr, target):
    left, right = 0, len(arr)  # bug: debería ser len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
""",
        test_code="""
def test_binary_search():
    assert binary_search([1, 3, 5, 7, 9], 5) == 2
    assert binary_search([1, 3, 5, 7, 9], 1) == 0
    assert binary_search([1, 3, 5, 7, 9], 9) == 4
    assert binary_search([1, 3, 5, 7, 9], 4) == -1
    assert binary_search([], 1) == -1
""",
        expected_fix_hint="Cambiar len(arr) a len(arr) - 1 en la inicialización de right"
    ),
    EvalCase(
        id="none-check",
        description="Falta validación de None en función de procesamiento",
        buggy_code="""
def calculate_discount(price, discount_pct):
    # discount_pct puede ser None si el producto no tiene descuento
    discounted = price * (1 - discount_pct / 100)
    return round(discounted, 2)
""",
        test_code="""
def test_calculate_discount():
    assert calculate_discount(100.0, 20) == 80.0
    assert calculate_discount(50.0, 0) == 50.0
    assert calculate_discount(100.0, None) == 100.0  # sin descuento = precio original
    assert calculate_discount(200.0, 50) == 100.0
""",
        expected_fix_hint="Agregar: if discount_pct is None: return round(price, 2)"
    ),
    EvalCase(
        id="dict-mutation",
        description="Mutación inesperada de diccionario compartido",
        buggy_code="""
DEFAULT_CONFIG = {"timeout": 30, "retries": 3, "debug": False}

def get_config(overrides={}):
    config = DEFAULT_CONFIG  # bug: referencia, no copia
    config.update(overrides)
    return config
""",
        test_code="""
def test_get_config():
    c1 = get_config({"debug": True})
    c2 = get_config({})
    assert c2["debug"] == False  # no debe verse afectado por c1
    assert c1["timeout"] == 30
    assert c2["retries"] == 3
""",
        expected_fix_hint="Cambiar config = DEFAULT_CONFIG a config = DEFAULT_CONFIG.copy()"
    ),
]


# --- Runner simplificado ---

def run_agent_on_case(case: EvalCase) -> EvalResult:
    """Corre el agente en un caso de eval usando un workspace temporal."""
    workspace = Path(tempfile.mkdtemp())

    try:
        # Escribir el código con el bug
        target_file = workspace / "solution.py"
        target_file.write_text(case.buggy_code)

        # Escribir los tests
        test_file = workspace / "test_solution.py"
        test_file.write_text(f"from solution import *\n{case.test_code}")

        input_tokens = output_tokens = 0
        iterations = 0
        files_changed = 0
        tests_passed = False

        messages = [{
            "role": "user",
            "content": (
                f"Hay un bug en `solution.py`. Los tests en `test_solution.py` están fallando.\n\n"
                f"El archivo está en: {workspace}\n\n"
                f"Arreglá el bug para que todos los tests pasen."
            )
        }]

        tools = [
            {
                "name": "read_file",
                "description": "Lee un archivo",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Escribe contenido a un archivo (siempre completo)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "run_tests",
                "description": "Ejecuta los tests y retorna el resultado",
                "input_schema": {"type": "object", "properties": {}}
            }
        ]

        for _ in range(5):
            iterations += 1
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                tools=tools,
                messages=messages,
                system="Arreglá el bug con el cambio mínimo necesario. Corré los tests después de cada cambio."
            )

            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    if block.name == "read_file":
                        try:
                            result = Path(block.input["path"]).read_text()
                        except Exception as e:
                            result = f"ERROR: {e}"

                    elif block.name == "write_file":
                        try:
                            p = Path(block.input["path"])
                            p.write_text(block.input["content"])
                            files_changed += 1
                            result = "OK"
                        except Exception as e:
                            result = f"ERROR: {e}"

                    elif block.name == "run_tests":
                        proc = subprocess.run(
                            ["python", "-m", "pytest", str(test_file), "-v", "--tb=short"],
                            capture_output=True, text=True, cwd=str(workspace)
                        )
                        result = proc.stdout + proc.stderr
                        if "passed" in result and "failed" not in result:
                            tests_passed = True

                    else:
                        result = f"ERROR: herramienta desconocida"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

                messages.append({"role": "user", "content": tool_results})

                if tests_passed:
                    break

        # Verificación final independiente
        proc = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-q"],
            capture_output=True, text=True, cwd=str(workspace)
        )
        tests_passed = proc.returncode == 0

        cost = (input_tokens * 3 + output_tokens * 15) / 1_000_000

        return EvalResult(
            case_id=case.id,
            tests_passed=tests_passed,
            iterations=iterations,
            files_changed=files_changed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost
        )

    except Exception as e:
        return EvalResult(
            case_id=case.id,
            tests_passed=False,
            iterations=0,
            files_changed=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=str(e)
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_eval_suite() -> EvalReport:
    start = time.time()
    results = []
    total_cost = 0.0

    for case in EVAL_CASES:
        print(f"  Evaluando [{case.id}]: {case.description}...", end=" ", flush=True)
        result = run_agent_on_case(case)
        results.append(result)
        total_cost += result.cost_usd
        status = "✓" if result.tests_passed else "✗"
        print(f"{status} (iter={result.iterations}, ${result.cost_usd:.4f})")

    return EvalReport(
        results=results,
        total_cost_usd=total_cost,
        elapsed_seconds=time.time() - start
    )


def compare_with_baseline(current: EvalReport):
    if not BASELINE_PATH.exists():
        print("No hay baseline guardado. Usá --save-baseline primero.")
        return

    baseline_data = json.loads(BASELINE_PATH.read_text())
    baseline = EvalReport(
        results=[EvalResult(**r) for r in baseline_data["results"]],
        total_cost_usd=baseline_data["total_cost_usd"],
        elapsed_seconds=baseline_data["elapsed_seconds"]
    )

    print("\n=== COMPARACIÓN CON BASELINE ===")
    delta_pass = current.pass_rate() - baseline.pass_rate()
    delta_score = current.avg_score() - baseline.avg_score()
    delta_cost = current.total_cost_usd - baseline.total_cost_usd

    arrow = lambda d: ("↑" if d > 0 else "↓" if d < 0 else "→")
    print(f"  Pass rate:  {arrow(delta_pass)} {delta_pass:+.1%}  ({baseline.pass_rate():.0%} → {current.pass_rate():.0%})")
    print(f"  Avg score:  {arrow(delta_score)} {delta_score:+.3f}  ({baseline.avg_score():.3f} → {current.avg_score():.3f})")
    print(f"  Cost:       {arrow(-delta_cost)} ${delta_cost:+.4f}")

    if delta_pass < -0.1:
        print("\n  ⚠️  REGRESIÓN DETECTADA: pass rate bajó más de 10%")


if __name__ == "__main__":
    print("Corriendo suite de evaluación...")
    report = run_eval_suite()
    report.print_summary()

    if "--save-baseline" in sys.argv:
        data = {
            "results": [asdict(r) for r in report.results],
            "total_cost_usd": report.total_cost_usd,
            "elapsed_seconds": report.elapsed_seconds
        }
        BASELINE_PATH.write_text(json.dumps(data, indent=2))
        print(f"Baseline guardado en {BASELINE_PATH}")

    if "--compare" in sys.argv:
        compare_with_baseline(report)
