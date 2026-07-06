"""
Módulo 0 — Grill Before Code

El patrón que más ahorra tiempo en desarrollo con AI.

Antes de escribir una línea de código, el agente te interroga hasta
que el plan es sólido. Lo hace usando el contexto real del proyecto:
CONTEXT.md, CLAUDE.md y los ADRs — así las preguntas son específicas
al dominio y las decisiones ya tomadas, no genéricas.

Cada pregunta viene con la respuesta recomendada por el agente
(justificada con el contexto) — Enter para aceptarla, o escribí
tu propia respuesta para corregirlo.

Inspirado en Matt Pocock /grill-me y /grill-with-docs.

Uso (corré desde la raíz del proyecto):
    export ANTHROPIC_API_KEY="sk-ant-..."
    python path/to/grill_before_code.py "descripción de la feature"

    # O interactivo (te pide la feature):
    python path/to/grill_before_code.py
"""

import sys
import anthropic
from dataclasses import dataclass, field
from pathlib import Path


client = anthropic.Anthropic()


# --- Carga de contexto del proyecto ---

def _read_if_exists(path: Path) -> str | None:
    if path.exists() and path.is_file():
        content = path.read_text(errors="replace").strip()
        return content if content else None
    return None


def load_project_context(project_root: Path) -> dict[str, str]:
    """
    Lee CONTEXT.md, CLAUDE.md y todos los ADRs del proyecto.
    Busca en la raíz dada y también sube hasta encontrar los archivos
    (útil si corrés el script desde un subdirectorio).
    """
    # Subir hasta 4 niveles buscando los archivos de contexto
    search_root = project_root
    for _ in range(4):
        if (_read_if_exists(search_root / "CONTEXT.md") or
                _read_if_exists(search_root / "CLAUDE.md")):
            project_root = search_root
            break
        search_root = search_root.parent

    context = {}

    context_md = _read_if_exists(project_root / "CONTEXT.md")
    if context_md:
        context["CONTEXT.md"] = context_md

    claude_md = _read_if_exists(project_root / "CLAUDE.md")
    if claude_md:
        context["CLAUDE.md"] = claude_md

    # ADRs: buscar en docs/adr/, docs/adrs/, adr/, decisions/
    adr_dirs = ["docs/adr", "docs/adrs", "adr", "decisions", "docs/decisions"]
    for adr_dir in adr_dirs:
        adr_path = project_root / adr_dir
        if adr_path.is_dir():
            adrs = sorted(adr_path.glob("*.md"))
            for adr_file in adrs:
                content = _read_if_exists(adr_file)
                if content:
                    context[f"ADR/{adr_file.name}"] = content
            break  # usar el primer directorio que exista

    return context


def format_project_context(context: dict[str, str]) -> str:
    if not context:
        return ""

    sections = []
    for filename, content in context.items():
        # Truncar ADRs muy largos para no inflar el system prompt
        max_len = 3000 if filename.startswith("ADR/") else 6000
        truncated = content[:max_len] + ("\n[...truncado]" if len(content) > max_len else "")
        sections.append(f"### {filename}\n{truncated}")

    return "\n\n".join(sections)


# --- Sesión de grilling ---

@dataclass
class GrillSession:
    feature_request: str
    project_root: Path
    context_files: dict[str, str] = field(default_factory=dict)
    questions_asked: int = 0
    answers: list = field(default_factory=list)
    implementation_plan: str = ""
    files_to_touch: list[str] = field(default_factory=list)
    tests_to_write: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    ready_to_implement: bool = False


TOOLS = [
    {
        "name": "ask_question",
        "description": (
            "Hacé UNA pregunta de clarificación al desarrollador. "
            "Empezá por la más crítica para el diseño. "
            "Las preguntas deben referenciar el contexto real del proyecto "
            "(conceptos de CONTEXT.md, decisiones de ADRs, convenciones de CLAUDE.md)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "La pregunta clara y específica al dominio del proyecto"
                },
                "why_it_matters": {
                    "type": "string",
                    "description": "Por qué esta decisión afecta la implementación, referenciando el contexto del proyecto si aplica"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Opciones posibles, preferiblemente basadas en patrones ya usados en el proyecto"
                },
                "recommended_answer": {
                    "type": "string",
                    "description": (
                        "Tu respuesta recomendada, justificada con el contexto del proyecto "
                        "(ADRs, patrones existentes). El desarrollador puede aceptarla con Enter."
                    )
                }
            },
            "required": ["question", "why_it_matters", "recommended_answer"]
        }
    },
    {
        "name": "submit_implementation_plan",
        "description": (
            "Cuando tenés suficiente información, generá el plan de implementación. "
            "El plan debe ser consistente con CONTEXT.md, CLAUDE.md y los ADRs del proyecto. "
            "Si la feature requiere una nueva decisión de arquitectura, indicalo como ADR pendiente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": "Plan detallado usando el lenguaje del dominio del proyecto (de CONTEXT.md)"
                },
                "files_to_create_or_modify": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Rutas de archivos, consistentes con la estructura del proyecto"
                },
                "tests_to_write": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Casos de test según las convenciones del proyecto (de CLAUDE.md)"
                },
                "adr_needed": {
                    "type": "string",
                    "description": "Si la feature introduce una decisión de arquitectura nueva, describí el ADR a crear. Vacío si no aplica.",
                    "default": ""
                },
                "open_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Decisiones que quedaron abiertas para resolver durante la implementación"
                }
            },
            "required": ["plan", "files_to_create_or_modify", "tests_to_write"]
        }
    }
]


def run_grill_session(feature_request: str, project_root: Path, max_questions: int = 6) -> GrillSession:
    context_files = load_project_context(project_root)
    session = GrillSession(
        feature_request=feature_request,
        project_root=project_root,
        context_files=context_files
    )

    formatted_context = format_project_context(context_files)

    print(f"\n[Grill Session]")
    print(f"Feature: {feature_request[:100]}")
    print(f"Proyecto: {project_root}")
    if context_files:
        print(f"Contexto cargado: {list(context_files.keys())}")
    else:
        print("⚠  No se encontró CONTEXT.md, CLAUDE.md ni ADRs — las preguntas serán más genéricas")
    print("=" * 60)
    print("Respondé cada pregunta con detalle. Más contexto = mejor plan.\n")

    context_section = (
        f"## Contexto del proyecto\n\n{formatted_context}"
        if formatted_context
        else "## Contexto del proyecto\n\nNo se encontraron archivos de contexto en el proyecto."
    )

    system = f"""Sos un tech lead experimentado haciendo design review de una feature antes de implementarla.

{context_section}

## Tu rol

Identificar ambigüedades, casos borde y decisiones de diseño implícitas que generarán
retrabajo si no se resuelven ahora.

Reglas críticas:
- Usá el lenguaje del dominio de CONTEXT.md (no inventes términos nuevos)
- Referenciá ADRs existentes cuando una pregunta toca una decisión ya tomada
  ("Según ADR-003 usamos event sourcing en pagos — ¿esta feature debe seguir ese patrón?")
- Si CLAUDE.md define convenciones de tests o estructura, preguntá si la feature las sigue
- Hacé UNA pregunta a la vez, la más crítica primero
- Para CADA pregunta proponé tu respuesta recomendada, justificada con el contexto
  del proyecto (el desarrollador puede aceptarla o corregirte)
- Máximo {max_questions} preguntas — después generá el plan igual con lo que tenés
- NO preguntes sobre preferencias de estilo ni implementación obvia

Tipos de preguntas valiosas (usando el contexto del proyecto):
- Consistencia con el dominio: "¿Esto es un nuevo concepto o extiende [entidad de CONTEXT.md]?"
- Consistencia con ADRs: "¿Debería seguir el patrón de [ADR existente]?"
- Edge cases del dominio: "¿Qué pasa cuando [estado/entidad del dominio] está en [estado edge]?"
- Seguridad/permisos: "¿Quién puede [acción] según las reglas del dominio?"
- Reversibilidad: "¿Esta operación debe ser reversible?"
- Impacto en otros bounded contexts del proyecto"""

    messages = [{"role": "user", "content": f"Quiero implementar: {feature_request}"}]

    for _ in range(max_questions + 3):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=TOOLS,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            if text:
                print(f"\n{text}")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "ask_question":
                    session.questions_asked += 1
                    question = block.input["question"]
                    why = block.input["why_it_matters"]
                    options = block.input.get("options", [])
                    recommended = block.input.get("recommended_answer", "")

                    print(f"\n[Q{session.questions_asked}] {question}")
                    print(f"    Por qué importa: {why}")
                    if options:
                        print(f"    Opciones: {' / '.join(options)}")
                    if recommended:
                        print(f"    Recomendación: {recommended}")
                    print()

                    prompt = "Tu respuesta (Enter = aceptar recomendación): " if recommended else "Tu respuesta: "
                    answer = input(prompt).strip()
                    if not answer and recommended:
                        answer = recommended
                        print(f"    → aceptada: {recommended[:80]}")
                    session.answers.append({"question": question, "answer": answer})

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": answer if answer else "(sin respuesta)"
                    })

                elif block.name == "submit_implementation_plan":
                    data = block.input
                    session.implementation_plan = data["plan"]
                    session.files_to_touch = data.get("files_to_create_or_modify", [])
                    session.tests_to_write = data.get("tests_to_write", [])
                    session.open_questions = data.get("open_questions", [])
                    session.ready_to_implement = True

                    print(f"\n{'=' * 60}")
                    print("PLAN DE IMPLEMENTACIÓN")
                    print("=" * 60)
                    print(f"\n{data['plan']}")

                    if session.files_to_touch:
                        print("\nArchivos a crear/modificar:")
                        for f in session.files_to_touch:
                            print(f"  - {f}")

                    if session.tests_to_write:
                        print("\nTests a escribir:")
                        for t in session.tests_to_write:
                            print(f"  - {t}")

                    if data.get("adr_needed"):
                        print(f"\n⚠  ADR pendiente a crear:\n  {data['adr_needed']}")

                    if session.open_questions:
                        print("\nDecisiones abiertas para la implementación:")
                        for q in session.open_questions:
                            print(f"  ? {q}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Plan registrado."
                    })

            messages.append({"role": "user", "content": tool_results})

            if session.ready_to_implement:
                break

    print(f"\n[Sesión completada: {session.questions_asked} preguntas | {len(context_files)} archivos de contexto usados]")
    return session


def main():
    # Feature desde argumento o input interactivo
    if len(sys.argv) > 1:
        feature_request = " ".join(sys.argv[1:])
    else:
        print("Describí la feature a implementar:")
        feature_request = input("> ").strip()
        if not feature_request:
            print("ERROR: Se necesita una descripción de la feature")
            sys.exit(1)

    # Buscar el proyecto desde el directorio actual
    project_root = Path.cwd()

    session = run_grill_session(feature_request, project_root)

    if not session.ready_to_implement:
        print("\n[El plan no fue generado — el agente no tuvo suficiente información]")
        sys.exit(1)

    print(f"\nListo para implementar. Usá el plan de arriba como contexto para tu sesión de Claude Code.")


if __name__ == "__main__":
    main()
