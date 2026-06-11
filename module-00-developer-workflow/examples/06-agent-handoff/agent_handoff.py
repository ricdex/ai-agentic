"""
Módulo 0 — Agent Handoff: Contexto comprimido entre agentes

El problema del handoff malo:
  - Volcar todo el historial de conversación (200k tokens) al siguiente agente
  - Resultado: lento, caro, mucho ruido

La solución:
  - El agente que termina genera un handoff estructurado (~500 tokens)
  - El siguiente agente empieza con contexto exacto sin grasa

Cuándo usarlo:
  - Workflows multi-agente (Módulo 2)
  - Cuando un agente alcanzó su context window y necesita continuación
  - Para separar fases: análisis → implementación → review

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python agent_handoff.py
"""

import json
import anthropic
from dataclasses import dataclass, field
from pathlib import Path

client = anthropic.Anthropic()


@dataclass
class HandoffDocument:
    """
    El contrato de información entre agentes.
    Diseñado para ser mínimo pero completo.
    """
    task_description: str
    phase_completed: str
    files_changed: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    current_state: str = ""
    next_phase: str = ""
    next_agent_instructions: str = ""
    warnings: list[str] = field(default_factory=list)
    tests_status: str = ""

    def to_context_string(self) -> str:
        """Formatea el handoff como contexto para el siguiente agente."""
        sections = [
            f"## Contexto recibido del agente anterior\n",
            f"**Tarea original:** {self.task_description}",
            f"**Fase completada:** {self.phase_completed}",
        ]

        if self.files_changed:
            sections.append(f"\n**Archivos modificados:**")
            for f in self.files_changed:
                sections.append(f"  - {f}")

        if self.decisions_made:
            sections.append(f"\n**Decisiones tomadas:**")
            for d in self.decisions_made:
                sections.append(f"  - {d}")

        if self.current_state:
            sections.append(f"\n**Estado actual:** {self.current_state}")

        if self.tests_status:
            sections.append(f"\n**Tests:** {self.tests_status}")

        if self.warnings:
            sections.append(f"\n**⚠ Advertencias:**")
            for w in self.warnings:
                sections.append(f"  - {w}")

        sections.append(f"\n**Tu tarea:** {self.next_agent_instructions}")

        return "\n".join(sections)

    def token_estimate(self) -> int:
        """Estimación aproximada de tokens."""
        return len(self.to_context_string()) // 4


# --- Herramientas para generar el handoff ---

HANDOFF_TOOL = {
    "name": "generate_handoff",
    "description": (
        "Generá el documento de handoff al terminar tu fase. "
        "Incluí solo la información que el siguiente agente necesita — sé conciso."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "phase_completed": {
                "type": "string",
                "description": "Qué fase completaste (ej: 'análisis del bug', 'implementación del fix')"
            },
            "files_changed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Archivos que modificaste"
            },
            "decisions_made": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Decisiones importantes que tomaste y por qué"
            },
            "current_state": {
                "type": "string",
                "description": "Estado actual del sistema/código (ej: 'tests fallan en test_auth.py')"
            },
            "tests_status": {
                "type": "string",
                "description": "Estado de los tests (ej: '5 passing, 2 failing')"
            },
            "next_agent_instructions": {
                "type": "string",
                "description": "Instrucciones específicas para el siguiente agente"
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Cosas que el siguiente agente debe saber o tener cuidado"
            }
        },
        "required": [
            "phase_completed",
            "files_changed",
            "decisions_made",
            "current_state",
            "next_agent_instructions"
        ]
    }
}


def run_agent_with_handoff_output(
    task: str,
    phase: str,
    next_phase: str,
    repo_path: str,
    incoming_handoff: HandoffDocument = None
) -> HandoffDocument:
    """
    Corre un agente que al terminar genera un handoff estructurado.

    Args:
        task: La tarea original
        phase: Qué hace este agente (ej: "análisis")
        next_phase: Qué hará el siguiente agente (ej: "implementación")
        repo_path: Directorio del repo
        incoming_handoff: Contexto del agente anterior (None si es el primero)
    """
    tools = [
        {
            "name": "read_file",
            "description": "Lee un archivo.",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
        },
        {
            "name": "list_files",
            "description": "Lista archivos del repo.",
            "input_schema": {"type": "object", "properties": {}, "required": []}
        },
        HANDOFF_TOOL
    ]

    def execute(name: str, inputs: dict) -> str:
        base = Path(repo_path)
        if name == "read_file":
            try:
                return (base / inputs["path"]).read_text()
            except Exception as e:
                return f"ERROR: {e}"
        elif name == "list_files":
            files = [str(f.relative_to(base)) for f in base.rglob("*")
                     if f.is_file() and ".git" not in str(f) and "__pycache__" not in str(f)]
            return "\n".join(files[:50])
        return f"ERROR: {name}"

    # Construir contexto: si hay handoff entrante, incluirlo
    user_content = f"Tarea: {task}\n\nTu fase: {phase}\n\nCuando termines, generá el handoff para la fase siguiente: {next_phase}"
    if incoming_handoff:
        user_content = incoming_handoff.to_context_string() + "\n\n---\n\n" + user_content

    system = (
        f"Sos un agente especializado en la fase de {phase}. "
        f"Al terminar, usá generate_handoff() para pasar el contexto al siguiente agente ({next_phase}). "
        "El handoff debe ser mínimo y preciso — solo lo que el siguiente agente necesita."
    )

    messages = [{"role": "user", "content": user_content}]
    handoff_result = None

    print(f"\n[Agente: {phase}]")

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=tools,
            messages=messages,
            system=system
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"  → {block.name}")
                    if block.name == "generate_handoff":
                        inp = block.input
                        handoff_result = HandoffDocument(
                            task_description=task,
                            phase_completed=inp["phase_completed"],
                            next_phase=next_phase,
                            files_changed=inp.get("files_changed", []),
                            decisions_made=inp.get("decisions_made", []),
                            current_state=inp.get("current_state", ""),
                            tests_status=inp.get("tests_status", ""),
                            next_agent_instructions=inp["next_agent_instructions"],
                            warnings=inp.get("warnings", [])
                        )
                        print(f"  [Handoff generado: ~{handoff_result.token_estimate()} tokens]")
                        result_text = "Handoff generado exitosamente."
                    else:
                        result_text = execute(block.name, block.input)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text
                    })

            messages.append({"role": "user", "content": tool_results})
            if handoff_result:
                break

    return handoff_result


def demo_pipeline(repo_path: str):
    """
    Demo de un pipeline 3 fases:
    1. Análisis → 2. Plan → 3. Review plan
    """
    task = "Refactorizar el módulo de autenticación para soportar OAuth2 además del login con password"

    print(f"\n[Pipeline Multi-Agente con Handoffs]")
    print(f"Tarea: {task}")
    print("=" * 60)

    # Agente 1: Análisis
    handoff_1 = run_agent_with_handoff_output(
        task=task,
        phase="análisis del código existente",
        next_phase="diseño del plan de implementación",
        repo_path=repo_path,
        incoming_handoff=None
    )

    if not handoff_1:
        print("[!] Agente 1 no generó handoff")
        return

    print(f"\n[Handoff 1 → 2]\n{handoff_1.to_context_string()[:400]}...")

    # Agente 2: Diseño (recibe el handoff del agente 1)
    handoff_2 = run_agent_with_handoff_output(
        task=task,
        phase="diseño del plan de implementación",
        next_phase="revisión de calidad del plan",
        repo_path=repo_path,
        incoming_handoff=handoff_1
    )

    if not handoff_2:
        print("[!] Agente 2 no generó handoff")
        return

    print(f"\n[Resumen del pipeline]")
    print(f"  Agente 1 (análisis): {len(handoff_1.decisions_made)} decisiones")
    print(f"  Agente 2 (diseño):   {len(handoff_2.decisions_made)} decisiones")
    print(f"\n[Instrucciones para el siguiente agente (review)]:")
    print(f"  {handoff_2.next_agent_instructions}")

    # Guardar el handoff final
    handoff_path = Path(repo_path) / "handoff.json"
    handoff_data = {
        "task": task,
        "phase": handoff_2.phase_completed,
        "files_changed": handoff_2.files_changed,
        "decisions": handoff_2.decisions_made,
        "next": handoff_2.next_agent_instructions
    }
    handoff_path.write_text(json.dumps(handoff_data, indent=2, ensure_ascii=False))
    print(f"\n[Handoff guardado en {handoff_path}]")


if __name__ == "__main__":
    # Usa el sample-repo incluido (src/auth.py con AuthService básico password-only).
    # El pipeline simula: análisis del auth actual → diseño del plan para agregar OAuth2.
    demo_path = str(Path(__file__).parent / "sample-repo")
    demo_pipeline(demo_path)
