"""
Módulo 0 — Flujo AI-first completo

Encadena los 4 agentes del ciclo completo de una feature nueva:
  1. context_generator   → entiende el codebase, genera CONTEXT.md
  2. grill_before_code   → aclara la feature con el contexto real del proyecto
  3. scaffold_generator  → genera la estructura del proyecto (solo si no existe)
  4. tdd_agent           → implementa con TDD usando el plan del grill

Este es el flujo que un dev AI-first sigue para la primera feature de un proyecto nuevo.
A partir de la segunda feature, el scaffold ya existe — arrancás directo desde el grill.

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."

    # Flujo completo (interactivo — el grill y el scaffold te hacen preguntas)
    python run_workflow.py

    # Solo ver cómo funciona el encadenamiento (sin input interactivo)
    python run_workflow.py --demo
"""

import sys
from pathlib import Path

# Agregar las carpetas de los otros ejemplos al path
EXAMPLES_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(EXAMPLES_ROOT / "01-context-generator"))
sys.path.insert(0, str(EXAMPLES_ROOT / "02-grill-before-code"))
sys.path.insert(0, str(EXAMPLES_ROOT / "03-scaffold-generator"))
sys.path.insert(0, str(EXAMPLES_ROOT / "04-tdd-agent"))

from context_generator import generate_context
from grill_before_code import run_grill_session
from scaffold_generator import run_scaffold_session, load_project_context
from tdd_agent import run_tdd_session


SHARED_REPO = EXAMPLES_ROOT / "01-context-generator" / "sample-repo"

FEATURE_REQUEST = (
    "Agregar soporte para cupones de descuento en el proceso de checkout: "
    "el cliente puede ingresar un código de cupón al confirmar el Order, "
    "y el precio final refleja el descuento correspondiente."
)


def run_full_workflow(interactive: bool = True):
    print("\n" + "=" * 65)
    print("FLUJO AI-FIRST: Context → Grill → Scaffold → TDD")
    print("=" * 65)
    print(f"\nRepo base: {SHARED_REPO}")
    print(f"Feature:   {FEATURE_REQUEST}\n")

    # ── PASO 1: Generar / refrescar CONTEXT.md ────────────────────────
    print("\n[PASO 1 / 4] Context Generator")
    print("El agente lee el codebase y genera el CONTEXT.md del dominio.")
    print("─" * 50)

    context_path = SHARED_REPO / "CONTEXT.md"
    if context_path.exists():
        print(f"  CONTEXT.md ya existe en {context_path}")
        print("  (Para regenerarlo: borrá el archivo y volvé a correr)")
    else:
        generate_context(str(SHARED_REPO))
        print(f"  CONTEXT.md generado en {context_path}")

    # ── PASO 2: Grill — clarificar la feature con contexto real ──────
    print("\n[PASO 2 / 4] Grill Before Code")
    print("El agente te interroga usando CONTEXT.md + CLAUDE.md + ADRs.")
    print("Las preguntas son específicas del dominio, no genéricas.")
    print("─" * 50)

    grill_session = run_grill_session(
        feature_request=FEATURE_REQUEST,
        project_root=EXAMPLES_ROOT / "02-grill-before-code",
        max_questions=4 if not interactive else 6
    )

    if not grill_session.ready_to_implement:
        print("\n[!] El grill no produjo un plan. Revisá las respuestas.")
        return

    # ── PASO 3: Scaffold — estructura del proyecto ────────────────────
    scaffold_dir = Path(__file__).parent / "output" / "scaffold"
    if scaffold_dir.exists() and any(scaffold_dir.iterdir()):
        print("\n[PASO 3 / 4] Scaffold Generator — OMITIDO")
        print(f"  La estructura ya existe en {scaffold_dir}")
        print("  (Solo se genera UNA VEZ por proyecto)")
    else:
        print("\n[PASO 3 / 4] Scaffold Generator")
        print("Genera la estructura del proyecto desde el plan del grill.")
        print("Solo lógica estructural — sin lógica de negocio.")
        print("─" * 50)

        proj_context = load_project_context()
        run_scaffold_session(
            grill_plan=grill_session.implementation_plan,
            output_dir=str(scaffold_dir),
            context=proj_context
        )

    # ── PASO 4: TDD — implementar con el plan del grill ──────────────
    print("\n[PASO 4 / 4] TDD Agent")
    print("Implementa el plan con el ciclo Red → Green → Refactor.")
    print("El agente tiene criterio de 'listo' explícito: los tests pasan.")
    print("─" * 50)

    output_dir = Path(__file__).parent / "output" / "tdd"

    tdd_session = run_tdd_session(
        spec=grill_session.implementation_plan,
        output_dir=str(output_dir)
    )

    # ── Resumen ───────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("RESUMEN DEL FLUJO")
    print("=" * 65)
    context_status = "generado" if not context_path.exists() else "reutilizado"
    print(f"  1. Context:  CONTEXT.md {context_status}")
    print(f"  2. Grill:    {grill_session.questions_asked} preguntas → plan de {len(grill_session.files_to_touch)} archivos")
    print(f"  3. Scaffold: estructura en {scaffold_dir}")
    print(f"  4. TDD:      fase final = {tdd_session.phase}")
    if tdd_session.tests_file:
        print(f"     Tests:   {tdd_session.tests_file}")
    if tdd_session.impl_file:
        print(f"     Impl:    {tdd_session.impl_file}")

    print("""
Qué aprendiste con este flujo:
  - El AI necesita CONTEXTO para hacer preguntas útiles (paso 1 → 2)
  - El PLAN del grill define tanto la estructura (paso 3) como la lógica (paso 4)
  - El scaffold es un paso ÚNICO — las siguientes features van directo a TDD
  - Cada agente tiene un output concreto que alimenta al siguiente
""")


if __name__ == "__main__":
    interactive = "--demo" not in sys.argv
    if not interactive:
        print("[Modo demo: sin input interactivo — el grill usa max 2 preguntas]")
    run_full_workflow(interactive=interactive)
