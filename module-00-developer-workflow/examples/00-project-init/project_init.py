"""
project_init.py — Generador de archivos de contexto AI-first

Genera un archivo por ejecución:
  - CONTEXT.md   → dominio del sistema (base de todo)
  - CLAUDE.md    → stack y convenciones (requiere CONTEXT.md)
  - ADR          → decisión arquitectural (requiere CONTEXT.md + CLAUDE.md)

Reglas:
  - No se puede generar CLAUDE.md sin CONTEXT.md
  - No se puede generar un ADR sin CONTEXT.md + CLAUDE.md
  - Si CONTEXT.md ya existe, el anterior queda en _backups/ automáticamente
  - Antes de escribir, el agente verifica que el nuevo archivo no contradiga
    los archivos de contexto existentes

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."

    python project_init.py              # busca/escribe en el directorio actual
    python project_init.py --output /ruta/a/mi-proyecto
"""

import argparse
import json
import re
import sys
import anthropic
from datetime import datetime
from pathlib import Path

client = anthropic.Anthropic()


# ─── Estado del proyecto ──────────────────────────────────────────────────────

def get_project_state(base: Path) -> dict:
    """Retorna qué archivos de contexto existen."""
    adr_dir = base / "docs" / "adr"
    adrs = sorted(adr_dir.glob("*.md")) if adr_dir.exists() else []
    return {
        "has_context": (base / "CONTEXT.md").exists(),
        "has_claude": (base / "CLAUDE.md").exists(),
        "adr_count": len(adrs),
        "adr_files": adrs,
        "context_path": base / "CONTEXT.md",
        "claude_path": base / "CLAUDE.md",
        "adr_dir": adr_dir,
        "backups_dir": base / "_backups",
    }


def read_existing_files(state: dict) -> dict:
    """Lee el contenido de los archivos que ya existen."""
    contents = {}
    if state["has_context"]:
        contents["context"] = state["context_path"].read_text()
    if state["has_claude"]:
        contents["claude"] = state["claude_path"].read_text()
    for adr_path in state["adr_files"]:
        contents[f"adr_{adr_path.stem}"] = adr_path.read_text()
    return contents


def backup_file(path: Path, backups_dir: Path) -> Path:
    """Mueve el archivo a _backups/ con timestamp."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"{path.name}.{timestamp}.bak"
    path.rename(backup_path)
    return backup_path


# ─── Menú ─────────────────────────────────────────────────────────────────────

def show_menu(state: dict, base: Path) -> str:
    print("\n" + "=" * 55)
    print("PROJECT INIT — Archivos de contexto AI-first")
    print("=" * 55)
    print(f"\nProyecto: {base.resolve()}\n")
    print("Estado actual:")
    print(f"  {'✓' if state['has_context'] else '✗'} CONTEXT.md")
    print(f"  {'✓' if state['has_claude'] else '✗'} CLAUDE.md")
    if state["adr_count"]:
        print(f"  ✓ docs/adr/   ({state['adr_count']} archivo(s))")
    else:
        print(f"  ✗ docs/adr/   (sin ADRs)")

    print("\n¿Qué querés generar?\n")

    options = []

    label_ctx = "CONTEXT.md — dominio, entidades, reglas de negocio"
    if state["has_context"]:
        label_ctx += "  [sobreescribir — backup automático]"
    print(f"  1. {label_ctx}")
    options.append("1")

    if state["has_context"]:
        label_cl = "CLAUDE.md — stack, convenciones, qué evitar"
        if state["has_claude"]:
            label_cl += "  [sobreescribir — backup automático]"
        print(f"  2. {label_cl}")
        options.append("2")
    else:
        print(f"  2. CLAUDE.md  (requiere CONTEXT.md primero)")

    if state["has_context"] and state["has_claude"]:
        print(f"  3. ADR — decisión arquitectural no obvia")
        options.append("3")
    elif not state["has_context"]:
        print(f"  3. ADR  (requiere CONTEXT.md + CLAUDE.md primero)")
    else:
        print(f"  3. ADR  (requiere CLAUDE.md primero)")

    print(f"\n  q. Salir")
    print()

    while True:
        choice = input("Elegí una opción: ").strip().lower()
        if choice == "q":
            return "q"
        if choice in options:
            return choice
        print(f"  Opción no disponible. Elegí entre: {', '.join(options)}, q")


# ─── Herramientas comunes ─────────────────────────────────────────────────────

def make_ask_tool(max_questions: int = 5) -> dict:
    return {
        "name": "ask_questions",
        "description": (
            "Hace preguntas al desarrollador para reunir información. "
            f"Máximo {max_questions} preguntas por llamada. "
            "Podés llamar esto más de una vez si necesitás profundizar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "Una línea explicando de qué trata esta tanda"
                },
                "questions": {
                    "type": "array",
                    "maxItems": max_questions,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "hint": {
                                "type": "string",
                                "description": "Ejemplo o aclaración opcional"
                            }
                        },
                        "required": ["id", "text"]
                    }
                }
            },
            "required": ["questions"]
        }
    }


REPORT_CONTRADICTION_TOOL = {
    "name": "report_contradiction",
    "description": (
        "Reporta contradicciones encontradas entre el contenido propuesto "
        "y los archivos existentes. Llamar ANTES de write_* si encontrás conflictos. "
        "El usuario decide si continuar igual o ajustar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "contradictions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "Archivo existente donde está el conflicto"
                        },
                        "existing": {
                            "type": "string",
                            "description": "Lo que dice el archivo actual"
                        },
                        "proposed": {
                            "type": "string",
                            "description": "Lo que dice el nuevo contenido"
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["hard", "soft"],
                            "description": "hard=incompatible directo, soft=tension o ambigüedad"
                        }
                    },
                    "required": ["file", "existing", "proposed", "severity"]
                }
            }
        },
        "required": ["contradictions"]
    }
}


# ─── Validación de documentos ─────────────────────────────────────────────────
#
# Las preguntas las decide el LLM (ask_questions es dinámico), así que no hay
# garantía de que cubra todo lo que el estándar de cada doc exige. Estas
# funciones son el chequeo programático que corre DESPUÉS de las respuestas,
# contra el contenido final propuesto — no contra las preguntas en sí.

def validate_context_md(content: str) -> list[str]:
    """CONTEXT.md funcional = dominio + entidades con reglas + invariantes + límites."""
    issues = []
    lower = content.lower()
    if len(content.split()) < 60:
        issues.append("Muy corto para tener entidades y reglas reales (<60 palabras)")
    if not re.search(r"^#{1,3}\s", content, re.MULTILINE) and content.count("\n-") < 2:
        issues.append("Sin estructura (encabezados o listas) — entidades probablemente no están separadas")
    if not any(k in lower for k in ["nunca", "invariante", "no puede", "siempre"]):
        issues.append("Falta al menos un invariante explícito (algo que NUNCA puede pasar)")
    if not any(k in lower for k in ["no hace", "no es", "límite", "limite", "fuera de alcance", "no incluye"]):
        issues.append("Falta la sección 'qué NO hace este sistema'")
    return issues


def validate_claude_md(content: str) -> list[str]:
    """CLAUDE.md funcional = stack con versiones + estructura + cómo probar + qué evitar, ~100 líneas."""
    issues = []
    lower = content.lower()
    lines = content.count("\n") + 1
    if lines > 160:
        issues.append(f"Tiene {lines} líneas — CLAUDE.md debe rondar ~100, no ser una enciclopedia")
    if len(content.split()) < 40:
        issues.append("Muy corto para cubrir stack + convenciones (<40 palabras)")
    if not re.search(r"\d", content):
        issues.append("No se detectan versiones (ej: 'Python 3.12') — sin versión no es reproducible")
    if not any(k in lower for k in ["test", "pytest", "lint", "jest", "vitest"]):
        issues.append("Falta el comando para correr tests/lint — el agente no puede autovalidarse sin esto")
    if not any(k in lower for k in ["evitar", "no usar", "nunca", "restricci"]):
        issues.append("Falta qué evitar / restricciones técnicas explícitas")
    return issues


def validate_adr(content: str) -> list[str]:
    """ADR funcional (formato Nygard) = Contexto + Decisión + Consecuencias con trade-offs."""
    issues = []
    lower = content.lower()
    for key, label in [("contexto", "Contexto"), ("decisi", "Decisión"), ("consecuencias", "Consecuencias")]:
        if key not in lower:
            issues.append(f"Falta la sección '{label}'")
    if not re.search(r"[\(\[]?[+-][\)\]]?\s|\bbeneficio|\btrade-?off", lower):
        issues.append("Consecuencias sin trade-offs explícitos (falta al menos un (+) y un (-))")
    return issues


def confirm_despite_issues(doc_name: str, issues: list[str]) -> bool:
    """Muestra el checklist fallido y pregunta si escribir igual o que el agente corrija."""
    print(f"\n  ⚠  Validación de {doc_name} encontró huecos contra el estándar:\n")
    for issue in issues:
        print(f"    ✗ {issue}")
    ans = input("\n  ¿Escribir igual? (s = sí / n = que el agente lo corrija): ").strip().lower()
    return ans == "s"


# ─── Interacción ──────────────────────────────────────────────────────────────

def run_questions(questions: list, intro: str) -> dict:
    if intro:
        print(f"\n  {intro}")
    print()
    answers = {}
    for q in questions:
        print(f"  {q['text']}")
        if q.get("hint"):
            print(f"  ({q['hint']})")
        answers[q["id"]] = input("  > ").strip()
        print()
    return answers


def handle_contradictions(contradictions: list) -> bool:
    """Muestra las contradicciones y pregunta si continuar. Retorna True si se confirma."""
    print(f"\n  ⚠  Se encontraron {len(contradictions)} contradicción(es) con archivos existentes:\n")
    for i, c in enumerate(contradictions, 1):
        tag = "CONFLICTO" if c["severity"] == "hard" else "TENSIÓN"
        print(f"  [{tag}] {c['file']}")
        print(f"    Existente: {c['existing']}")
        print(f"    Propuesto: {c['proposed']}")
        print()

    ans = input("  ¿Continuar igual? (s = sí / n = cancelar): ").strip().lower()
    return ans == "s"


def run_agent_loop(system: str, tools: list, initial_message: str, write_handler) -> bool:
    """
    Loop principal del agente.
    write_handler(block) es llamado cuando el agente llama a la herramienta de escritura.
    Retorna True si se escribió el archivo.
    """
    messages = [{"role": "user", "content": initial_message}]
    all_answers = {}

    for _ in range(12):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            tools=tools,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text") and block.text.strip():
                    print(f"\n{block.text}")
            break

        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "ask_questions":
                intro = block.input.get("intro", "")
                questions = block.input["questions"]
                answers = run_questions(questions, intro)
                all_answers.update(answers)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(answers, ensure_ascii=False)
                })

            elif block.name == "report_contradiction":
                contradictions = block.input["contradictions"]
                proceed = handle_contradictions(contradictions)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "CONTINUAR" if proceed else "CANCELAR — el usuario eligió no continuar con estas contradicciones"
                })

            else:
                # write_* tool — delegado al handler del modo
                result = write_handler(block)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })
                if result.startswith("OK"):
                    messages.append({"role": "user", "content": tool_results})
                    # Una vuelta más para el resumen final
                    resp2 = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=512,
                        tools=tools,
                        messages=messages,
                        system=system
                    )
                    for b in resp2.content:
                        if hasattr(b, "text") and b.text.strip():
                            print(f"\n{b.text}")
                    return True

        messages.append({"role": "user", "content": tool_results})

    return False


# ─── Modo CONTEXT.md ──────────────────────────────────────────────────────────

def mode_context(state: dict, existing: dict, base: Path):
    write_tool = {
        "name": "write_context_md",
        "description": (
            "Escribe el CONTEXT.md final. Llamar solo cuando tenés toda la información "
            "necesaria. Si CONTEXT.md ya existe, verificá contradicciones con CLAUDE.md "
            "y ADRs existentes antes de llamar esto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "Contenido completo de CONTEXT.md. Debe incluir: "
                        "nombre del dominio, descripción en 1-2 oraciones, "
                        "entidades con sus reglas, invariantes del sistema "
                        "(qué nunca puede pasar), qué NO hace el sistema."
                    )
                }
            },
            "required": ["content"]
        }
    }

    existing_section = ""
    if existing.get("claude"):
        existing_section += f"\n## CLAUDE.md actual\n{existing['claude']}\n"
    for k, v in existing.items():
        if k.startswith("adr_"):
            existing_section += f"\n## ADR existente ({k})\n{v}\n"

    system = f"""Sos un arquitecto de software experto en diseño de dominio.

Tu tarea: entrevistar al desarrollador y generar un CONTEXT.md para su proyecto.

El CONTEXT.md debe incluir:
1. Nombre del dominio y descripción breve (1-2 oraciones)
2. Entidades principales con sus atributos y reglas de negocio
3. Invariantes del sistema (cosas que NUNCA pueden pasar)
4. Qué NO hace este sistema (límites del dominio)

Checklist obligatorio — no llames a write_context_md hasta tener los 4 puntos:
- [ ] Nombre del dominio + qué hace en 1-2 oraciones
- [ ] Al menos 2-3 entidades centrales, cada una con sus reglas de negocio (no solo el nombre)
- [ ] Al menos un invariante explícito ("nunca puede pasar que...")
- [ ] Al menos un límite explícito de lo que el sistema NO hace
Si terminaste las preguntas y falta alguno, hacé una ronda más antes de escribir.

Proceso:
1. Hacé preguntas sobre el dominio con ask_questions (una o dos rondas), cubriendo el checklist
2. Si existen CLAUDE.md o ADRs, verificá que el CONTEXT.md no los contradiga
3. Si encontrás contradicciones, reportalas con report_contradiction antes de escribir
4. Cuando tengas todo, escribí el archivo con write_context_md
5. Si write_context_md devuelve "REVISAR: ...", corregí el contenido (o preguntá lo que falte) y volvé a llamar write_context_md

Reglas:
- Usá la terminología exacta del desarrollador
- Sé específico, no genérico — "El precio se congela al confirmar" no "hay reglas de negocio"
- Primera persona del dominio: "Este sistema gestiona...", "Un Order tiene..."
{existing_section}"""

    def write_handler(block):
        if block.name != "write_context_md":
            return "herramienta no reconocida"
        content = block.input["content"]
        issues = validate_context_md(content)
        if issues and not confirm_despite_issues("CONTEXT.md", issues):
            return "REVISAR: " + " | ".join(issues)
        path = state["context_path"]
        if path.exists():
            backup = backup_file(path, state["backups_dir"])
            print(f"\n  [backup] {backup.name} → _backups/")
        path.write_text(content)
        print(f"  ✓ CONTEXT.md escrito en {path}")
        print(f"  ✓ Validación: {'sin observaciones' if not issues else 'aceptado con observaciones'}")
        return f"OK:{path}"

    run_agent_loop(
        system=system,
        tools=[make_ask_tool(), REPORT_CONTRADICTION_TOOL, write_tool],
        initial_message=(
            "Arrancá con las preguntas sobre el dominio del sistema. "
            "Hacé preguntas concretas y específicas."
        ),
        write_handler=write_handler
    )


# ─── Modo CLAUDE.md ───────────────────────────────────────────────────────────

def mode_claude(state: dict, existing: dict, base: Path):
    write_tool = {
        "name": "write_claude_md",
        "description": (
            "Escribe el CLAUDE.md final. Verificá contradicciones con CONTEXT.md "
            "antes de llamar esto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "Contenido completo de CLAUDE.md. Debe incluir: "
                        "stack (lenguaje, framework, DB, cloud/deploy), "
                        "estructura de carpetas, convenciones de código, "
                        "cómo correr tests, qué evitar."
                    )
                }
            },
            "required": ["content"]
        }
    }

    system = f"""Sos un arquitecto de software experto en convenciones y stack técnico.

Tu tarea: entrevistar al desarrollador y generar un CLAUDE.md para su proyecto.

El CLAUDE.md debe incluir:
1. Stack completo (lenguaje + versión, framework, DB, cloud/deploy)
2. Estructura de carpetas del proyecto
3. Convenciones de código (nombres, patrones, qué evitar)
4. Cómo correr tests y linter
5. Restricciones técnicas no obvias

Checklist obligatorio — no llames a write_claude_md hasta tener los 5 puntos:
- [ ] Lenguaje + versión exacta (ej: "Python 3.12", no solo "Python")
- [ ] Framework/librerías clave + versión si aplica
- [ ] Cómo se persiste y despliega (DB, cloud, contenedor)
- [ ] Estructura de carpetas real del proyecto
- [ ] Comando exacto para correr tests y comando para lint
- [ ] Al menos una restricción explícita ("no usar X", "nunca Y")

Proceso:
1. Hacé preguntas sobre el stack con ask_questions (una o dos rondas), cubriendo el checklist
2. OBLIGATORIO: verificá que el CLAUDE.md propuesto no contradiga el CONTEXT.md
   Ejemplos de contradicción: CONTEXT.md dice "sistema stateless" pero CLAUDE.md dice "usamos sesiones en DB"
3. Si encontrás contradicciones, reportalas con report_contradiction antes de escribir
4. Escribí el archivo con write_claude_md
5. Si write_claude_md devuelve "REVISAR: ...", corregí el contenido y volvé a llamarlo

## CONTEXT.md del proyecto (existente — no contradecir)
{existing['context']}
"""

    def write_handler(block):
        if block.name != "write_claude_md":
            return "herramienta no reconocida"
        content = block.input["content"]
        issues = validate_claude_md(content)
        if issues and not confirm_despite_issues("CLAUDE.md", issues):
            return "REVISAR: " + " | ".join(issues)
        path = state["claude_path"]
        if path.exists():
            backup = backup_file(path, state["backups_dir"])
            print(f"\n  [backup] {backup.name} → _backups/")
        path.write_text(content)
        print(f"  ✓ CLAUDE.md escrito en {path}")
        print(f"  ✓ Validación: {'sin observaciones' if not issues else 'aceptado con observaciones'}")
        return f"OK:{path}"

    run_agent_loop(
        system=system,
        tools=[make_ask_tool(), REPORT_CONTRADICTION_TOOL, write_tool],
        initial_message=(
            "Arrancá con las preguntas sobre el stack y convenciones del proyecto."
        ),
        write_handler=write_handler
    )


# ─── Modo ADR ─────────────────────────────────────────────────────────────────

def mode_adr(state: dict, existing: dict, base: Path):
    next_num = state["adr_count"] + 1
    num_str = str(next_num).zfill(3)

    write_tool = {
        "name": "write_adr",
        "description": (
            "Escribe el ADR final. Verificá contradicciones con CONTEXT.md y CLAUDE.md "
            "antes de llamar esto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": f"Nombre del archivo. Debe empezar con '{num_str}-'. Ej: {num_str}-precio-congelado.md"
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Contenido del ADR con las secciones: "
                        "Contexto (por qué surgió), "
                        "Decisión (qué se decidió exactamente), "
                        "Consecuencias (ventajas y trade-offs aceptados)."
                    )
                }
            },
            "required": ["filename", "content"]
        }
    }

    existing_adrs_section = ""
    for k, v in existing.items():
        if k.startswith("adr_"):
            existing_adrs_section += f"\n## ADR existente ({k})\n{v}\n"

    system = f"""Sos un arquitecto de software experto en decisiones arquitecturales.

Tu tarea: entrevistar al desarrollador para documentar una decisión arquitectural como ADR.

Un ADR es para decisiones NO OBVIAS — si cualquier dev nuevo elegiría lo mismo por defecto,
no es un ADR. Ejemplos válidos: precio congelado al confirmar, CQRS, event sourcing,
notificaciones desacopladas del dominio, usar ULID en vez de UUID.

Estructura del ADR:
- **Contexto**: por qué surgió esta decisión, qué problema resuelve
- **Decisión**: exactamente qué se decidió
- **Consecuencias**: (+) beneficios, (-) trade-offs aceptados

Checklist obligatorio — no llames a write_adr hasta tener los 3 puntos:
- [ ] Contexto: el problema concreto que disparó la decisión (no genérico)
- [ ] Decisión: una frase no ambigua de qué se decidió exactamente
- [ ] Al menos un beneficio (+) y un trade-off aceptado (-) en Consecuencias

Proceso:
1. Preguntá sobre la decisión con ask_questions, cubriendo el checklist
2. OBLIGATORIO: verificá que el ADR no contradiga el CONTEXT.md ni el CLAUDE.md
   Ejemplos de contradicción: CONTEXT.md dice "dominio puro sin infraestructura"
   pero el ADR dice "guardar logs de dominio en Redis directamente"
3. Si encontrás contradicciones, reportalas con report_contradiction
4. Escribí el ADR con write_adr (el filename debe empezar con '{num_str}-')
5. Si write_adr devuelve "REVISAR: ...", corregí el contenido y volvé a llamarlo

## CONTEXT.md del proyecto
{existing['context']}

## CLAUDE.md del proyecto
{existing['claude']}
{existing_adrs_section}"""

    def write_handler(block):
        if block.name != "write_adr":
            return "herramienta no reconocida"
        filename = block.input["filename"]
        content = block.input["content"]

        issues = validate_adr(content)
        if issues and not confirm_despite_issues("el ADR", issues):
            return "REVISAR: " + " | ".join(issues)

        if not filename.startswith(num_str):
            filename = f"{num_str}-{filename.lstrip('0123456789-')}"

        state["adr_dir"].mkdir(parents=True, exist_ok=True)
        adr_path = state["adr_dir"] / filename
        adr_path.write_text(content)
        print(f"  ✓ docs/adr/{filename} escrito")
        print(f"  ✓ Validación: {'sin observaciones' if not issues else 'aceptado con observaciones'}")
        return f"OK:{adr_path}"

    run_agent_loop(
        system=system,
        tools=[make_ask_tool(), REPORT_CONTRADICTION_TOOL, write_tool],
        initial_message=(
            "Arrancá preguntando sobre qué decisión arquitectural no obvia "
            "quiere documentar el desarrollador."
        ),
        write_handler=write_handler
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Genera CONTEXT.md, CLAUDE.md o ADRs para un proyecto AI-first"
    )
    parser.add_argument(
        "--output", "-o",
        default=".",
        help="Directorio del proyecto (default: directorio actual)"
    )
    args = parser.parse_args()
    base = Path(args.output).resolve()

    state = get_project_state(base)
    choice = show_menu(state, base)

    if choice == "q":
        print("Saliendo.\n")
        sys.exit(0)

    existing = read_existing_files(state)
    print()

    if choice == "1":
        mode_context(state, existing, base)
    elif choice == "2":
        mode_claude(state, existing, base)
    elif choice == "3":
        mode_adr(state, existing, base)

    print(f"\n[Siguiente paso]")
    if choice == "1" and not state["has_claude"]:
        print(f"  Generá CLAUDE.md: python project_init.py --output {args.output}")
    elif choice in ("1", "2") and not (state["has_context"] and state["has_claude"]):
        print(f"  Completá los archivos restantes antes de generar ADRs")
    else:
        print(f"  Arrancá con el grill para la primera feature:")
        print(f"  python ../02-grill-before-code/grill_before_code.py \"descripción\"")
    print()


if __name__ == "__main__":
    main()
