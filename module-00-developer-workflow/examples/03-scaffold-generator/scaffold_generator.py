"""
Módulo 0 — Scaffold Generator: arquitectura inicial AI-first

Genera el esqueleto del proyecto ANTES del primer ciclo TDD.
Este es el único momento donde el AI crea estructura sin lógica de negocio.

Inputs (los lee automáticamente desde el directorio actual o padres):
  - CONTEXT.md   → entidades y reglas del dominio
  - CLAUDE.md    → stack, convenciones, qué evitar
  - docs/adr/*.md → decisiones de arquitectura

Puede hacer hasta 3 preguntas de ESTRUCTURA (no de dominio — el grill ya lo hizo).

Output:
  - Carpeta de proyecto con esqueleto listo para TDD

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."

    # Con el plan del grill como archivo:
    python scaffold_generator.py --plan grill_plan.txt --output ./mi-proyecto

    # Interactivo (pedirá el plan si no se pasa --plan):
    python scaffold_generator.py --output ./mi-proyecto
"""

import argparse
import json
import anthropic
from pathlib import Path
from dataclasses import dataclass, field

client = anthropic.Anthropic()


@dataclass
class ScaffoldResult:
    files_created: list = field(default_factory=list)
    output_dir: str = ""
    tree: str = ""


def load_project_context() -> dict:
    """Walk up to 4 levels looking for CONTEXT.md, CLAUDE.md, and ADRs."""
    context = {}
    search_dir = Path.cwd()

    for _ in range(4):
        context_path = search_dir / "CONTEXT.md"
        claude_path = search_dir / "CLAUDE.md"

        if context_path.exists() and "context" not in context:
            context["context"] = context_path.read_text()
            context["context_path"] = str(context_path)

        if claude_path.exists() and "claude" not in context:
            context["claude"] = claude_path.read_text()
            context["claude_path"] = str(claude_path)

        if "adrs" not in context:
            for adr_dir in ["docs/adr", "docs/adrs", "adr", "decisions"]:
                adr_path = search_dir / adr_dir
                if adr_path.exists() and adr_path.is_dir():
                    adrs = [
                        {"file": str(f), "content": f.read_text()}
                        for f in sorted(adr_path.glob("*.md"))
                    ]
                    if adrs:
                        context["adrs"] = adrs
                    break

        if "context" in context and "claude" in context:
            break
        search_dir = search_dir.parent

    return context


SCAFFOLD_TOOLS = [
    {
        "name": "ask_clarification",
        "description": (
            "Hace preguntas de ESTRUCTURA al desarrollador. "
            "Solo preguntas sobre la arquitectura física: carpetas, monorepo, "
            "ORM, framework web, etc. "
            "El dominio ya fue aclarado en el grill — no repetir esas preguntas. "
            "Máximo 3 preguntas. Llamar UNA SOLA VEZ con todas las preguntas juntas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Opciones sugeridas — el dev puede elegir otra"
                            }
                        },
                        "required": ["id", "text"]
                    }
                }
            },
            "required": ["questions"]
        }
    },
    {
        "name": "create_scaffold",
        "description": (
            "Crea el esqueleto completo del proyecto. "
            "Incluir: carpetas, pyproject.toml o requirements.txt, __init__.py, "
            "interfaces/protocolos base (sin lógica), conftest.py, .gitignore. "
            "NO incluir lógica de negocio — eso va en TDD. "
            "Cada archivo debe tener contenido real (no TODO vacíos)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Ruta relativa al output_dir"
                            },
                            "content": {"type": "string"},
                            "description": {
                                "type": "string",
                                "description": "Qué hace este archivo"
                            }
                        },
                        "required": ["path", "content", "description"]
                    }
                },
                "tree": {
                    "type": "string",
                    "description": "Árbol de directorios en formato ASCII"
                },
                "summary": {
                    "type": "string",
                    "description": "Qué se creó y por qué esa estructura"
                }
            },
            "required": ["files", "tree", "summary"]
        }
    }
]


def run_scaffold_session(grill_plan: str, output_dir: str, context: dict) -> ScaffoldResult:
    result = ScaffoldResult(output_dir=output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Build context section for the system prompt
    ctx_section = ""
    if "context" in context:
        ctx_section += f"\n## CONTEXT.md\n{context['context']}\n"
    if "claude" in context:
        ctx_section += f"\n## CLAUDE.md\n{context['claude']}\n"
    if "adrs" in context:
        for adr in context["adrs"]:
            ctx_section += f"\n## ADR: {Path(adr['file']).name}\n{adr['content']}\n"

    system_prompt = f"""Sos un arquitecto de software experto en AI-first development.

Tu tarea: generar el ESQUELETO inicial de un proyecto Python.

Reglas:
1. El esqueleto NO contiene lógica de negocio — esa la produce TDD
2. Seguís ESTRICTAMENTE las convenciones de CLAUDE.md
3. Las interfaces y tipos base reflejan las entidades de CONTEXT.md
4. Serverless-first si CLAUDE.md no especifica otra cosa
5. Podés hacer hasta 3 preguntas de ESTRUCTURA (no de dominio) con ask_clarification
6. Luego generás el scaffold completo con create_scaffold

{ctx_section}"""

    messages = [{
        "role": "user",
        "content": (
            f"Plan del grill (feature a implementar):\n\n{grill_plan}\n\n"
            "Generá el esqueleto del proyecto para este sistema. "
            "Si necesitás clarificar algo sobre la ESTRUCTURA física (no el dominio), "
            "preguntá primero. Sino, creá el scaffold directamente."
        )
    }]

    print(f"\n[Scaffold Generator] Contexto cargado:")
    if "context" in context:
        print(f"  ✓ CONTEXT.md  ({context.get('context_path', '')})")
    else:
        print(f"  ✗ CONTEXT.md  no encontrado — el scaffold será genérico")
    if "claude" in context:
        print(f"  ✓ CLAUDE.md   ({context.get('claude_path', '')})")
    else:
        print(f"  ✗ CLAUDE.md   no encontrado — se usarán convenciones por defecto")
    if "adrs" in context:
        print(f"  ✓ ADRs        ({len(context['adrs'])} archivos)")
    print(f"\n[Output] {output_dir}")
    print("=" * 60)

    scaffold_created = False

    for _ in range(6):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            tools=SCAFFOLD_TOOLS,
            messages=messages,
            system=system_prompt
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "ask_clarification":
                questions = block.input["questions"]
                print(f"\n[Preguntas de estructura]")
                answers = {}

                for q in questions:
                    print(f"\n  {q['text']}")
                    options = q.get("options", [])
                    if options:
                        for i, opt in enumerate(options, 1):
                            print(f"    {i}. {opt}")

                    answer = input("  > ").strip()
                    if options and answer.isdigit():
                        idx = int(answer) - 1
                        if 0 <= idx < len(options):
                            answer = options[idx]
                    answers[q["id"]] = answer

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(answers, ensure_ascii=False)
                })

            elif block.name == "create_scaffold":
                files = block.input["files"]
                tree = block.input.get("tree", "")
                summary = block.input.get("summary", "")

                print(f"\n[Creando scaffold]\n{tree}")

                for file_info in files:
                    file_path = Path(output_dir) / file_info["path"]
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(file_info["content"])
                    result.files_created.append(file_info["path"])
                    desc = file_info.get("description", "")
                    print(f"  ✓ {file_info['path']}" + (f"  ← {desc}" if desc else ""))

                result.tree = tree
                scaffold_created = True

                print(f"\n[Resumen]\n{summary}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Scaffold creado: {len(files)} archivos en {output_dir}"
                })

        messages.append({"role": "user", "content": tool_results})
        if scaffold_created:
            break

    if not scaffold_created:
        print("[!] El agente no generó el scaffold.")
    else:
        print(f"\n{'=' * 60}")
        print(f"[✓] Scaffold listo — {len(result.files_created)} archivos en {output_dir}")
        print(f"    Siguiente paso: corré el TDD con el plan del grill como spec")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera la arquitectura inicial del proyecto desde CONTEXT.md + CLAUDE.md + ADRs"
    )
    parser.add_argument(
        "--plan", "-p",
        help="Archivo con el plan del grill (.txt). Si no se pasa, usa grill_plan.txt del directorio."
    )
    parser.add_argument(
        "--output", "-o",
        default="./output/project-scaffold",
        help="Directorio donde crear el scaffold (default: ./output/project-scaffold)"
    )
    args = parser.parse_args()

    context = load_project_context()

    if not context.get("context") and not context.get("claude"):
        print("[!] No se encontró CONTEXT.md ni CLAUDE.md en este directorio ni en los padres.")
        print("    El scaffold funcionará pero será genérico.")
        print("    Para un scaffold ajustado a tu proyecto, creá estos archivos primero.")
        print("    Ver: módulo README.md sección 'Flujo paso a paso'\n")

    # Resolve grill plan
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"[!] No se encontró el archivo de plan: {args.plan}")
            exit(1)
        grill_plan = plan_path.read_text()
    else:
        sample_plan = Path(__file__).parent / "grill_plan.txt"
        if sample_plan.exists():
            print(f"[Usando plan de ejemplo: {sample_plan.name}]")
            grill_plan = sample_plan.read_text()
        else:
            print("Pegá el plan del grill (línea vacía para terminar):")
            lines = []
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)
            grill_plan = "\n".join(lines)

        if not grill_plan.strip():
            print("[!] Plan vacío — abortando.")
            exit(1)

    run_scaffold_session(
        grill_plan=grill_plan,
        output_dir=args.output,
        context=context
    )
