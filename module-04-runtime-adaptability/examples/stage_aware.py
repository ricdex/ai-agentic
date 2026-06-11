"""
Módulo 4 — Agente Stage-Aware

Demuestra cómo un agente cambia su comportamiento en runtime
según el stage (dev/staging/production), el riesgo del cambio,
y el historial de fallas.

También muestra extended thinking para casos complejos.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python stage_aware.py
"""

import time
import anthropic
from dataclasses import dataclass, field
from pathlib import Path

client = anthropic.Anthropic()

CRITICAL_FILES = {"auth.py", "payments.py", "security.py", "migrations"}
CRITICAL_PATTERNS = ["password", "token", "secret", "api_key", "credit_card", "ssn"]


@dataclass
class RuntimeContext:
    stage: str = "dev"          # dev | staging | production
    branch: str = "feature/x"
    test_failures: int = 0
    budget_tokens_used: int = 0
    budget_tokens_max: int = 50_000
    elapsed_seconds: float = 0.0
    files_touched: list = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    @property
    def is_critical_path(self) -> bool:
        for f in self.files_touched:
            if any(critical in f for critical in CRITICAL_FILES):
                return True
        return False

    @property
    def budget_percent_used(self) -> float:
        return self.budget_tokens_used / self.budget_tokens_max

    def update_elapsed(self):
        self.elapsed_seconds = time.time() - self.start_time


@dataclass
class AdaptiveDecision:
    should_escalate: bool
    escalation_reason: str
    model_to_use: str
    use_extended_thinking: bool
    behavior_guidance: str
    confidence_required: float


def compute_decision(ctx: RuntimeContext, task_description: str) -> AdaptiveDecision:
    """
    Calcula cómo debe comportarse el agente dado el contexto actual.
    Esta lógica corre ANTES de llamar a Claude — es determinística.
    """
    # Detectar si la tarea menciona archivos/patrones críticos
    task_lower = task_description.lower()
    mentions_critical = any(p in task_lower for p in CRITICAL_PATTERNS)

    # Reglas de escalamiento
    if ctx.stage == "production" and (ctx.is_critical_path or mentions_critical):
        return AdaptiveDecision(
            should_escalate=True,
            escalation_reason="Cambio crítico en producción",
            model_to_use="claude-opus-4-7",
            use_extended_thinking=True,
            behavior_guidance="",
            confidence_required=0.95
        )

    if ctx.test_failures >= 3:
        return AdaptiveDecision(
            should_escalate=True,
            escalation_reason=f"3 fallas consecutivas — debugging manual requerido",
            model_to_use="claude-opus-4-7",
            use_extended_thinking=True,
            behavior_guidance="",
            confidence_required=0.90
        )

    if ctx.budget_percent_used >= 0.85:
        return AdaptiveDecision(
            should_escalate=True,
            escalation_reason="Presupuesto de tokens casi agotado (>85%)",
            model_to_use="claude-haiku-4-5-20251001",
            use_extended_thinking=False,
            behavior_guidance="",
            confidence_required=0.80
        )

    # Selección de modelo y comportamiento
    if ctx.stage == "production":
        model = "claude-sonnet-4-6"
        thinking = False
        guidance = (
            "Estás en PRODUCCIÓN. Sé conservador. "
            "Hacé el cambio mínimo. Reportá tu confianza antes de cada cambio."
        )
        confidence = 0.85

    elif ctx.test_failures > 0:
        model = "claude-sonnet-4-6"
        thinking = ctx.test_failures >= 2  # extended thinking si falló 2+ veces
        guidance = (
            f"Fallaste {ctx.test_failures} vez/veces. "
            "Analizá el error desde cero. Cambiá el approach, no solo el código."
        )
        confidence = 0.75

    else:
        model = "claude-sonnet-4-6"
        thinking = False
        guidance = "Procedé normalmente. Iterá si es necesario."
        confidence = 0.70

    return AdaptiveDecision(
        should_escalate=False,
        escalation_reason="",
        model_to_use=model,
        use_extended_thinking=thinking,
        behavior_guidance=guidance,
        confidence_required=confidence
    )


# --- Herramientas ---

TOOLS = [
    {
        "name": "report_confidence",
        "description": (
            "Reportá tu nivel de confianza ANTES de hacer cambios importantes. "
            "El sistema puede escalar al humano si tu confianza es muy baja."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "confidence": {
                    "type": "number",
                    "description": "Nivel de confianza de 0.0 (incertidumbre total) a 1.0 (certeza total)"
                },
                "reason": {
                    "type": "string",
                    "description": "Por qué tu confianza es ese nivel"
                },
                "missing_info": {
                    "type": "string",
                    "description": "Qué información necesitarías para estar más seguro"
                }
            },
            "required": ["confidence", "reason"]
        }
    },
    {
        "name": "propose_change",
        "description": "Propone un cambio de código para revisión.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "description": {"type": "string", "description": "Qué cambia y por qué"},
                "code_snippet": {"type": "string", "description": "El cambio propuesto"}
            },
            "required": ["file", "description", "code_snippet"]
        }
    }
]


def run_adaptive_agent(task: str, ctx: RuntimeContext) -> dict:
    """
    Ejecuta el agente con comportamiento adaptado al contexto runtime.
    """
    ctx.update_elapsed()
    decision = compute_decision(ctx, task)

    print(f"\n[Stage-Aware Agent]")
    print(f"  Stage: {ctx.stage} | Branch: {ctx.branch}")
    print(f"  Failures: {ctx.test_failures} | Budget: {ctx.budget_percent_used:.0%}")
    print(f"  Files: {ctx.files_touched}")
    print(f"\n[Decision]")
    print(f"  Model: {decision.model_to_use}")
    print(f"  Extended Thinking: {decision.use_extended_thinking}")
    print(f"  Confidence required: {decision.confidence_required}")

    # Escalamiento automático
    if decision.should_escalate:
        print(f"\n[⚠️ ESCALANDO A HUMANO]")
        print(f"  Razón: {decision.escalation_reason}")
        return {
            "escalated": True,
            "reason": decision.escalation_reason,
            "context": ctx.__dict__
        }

    print(f"  Guidance: {decision.behavior_guidance}")
    print("=" * 60)

    system = f"""Sos un agente de desarrollo con conciencia de contexto.

## Contexto actual
- Stage: {ctx.stage}
- Branch: {ctx.branch}
- Intentos previos fallidos: {ctx.test_failures}
- Archivos modificados hasta ahora: {ctx.files_touched}
- Budget usado: {ctx.budget_percent_used:.0%}

## Comportamiento requerido
{decision.behavior_guidance}

## Confianza mínima requerida
Antes de proponer cambios, reportá tu confianza. Si es menor a {decision.confidence_required:.0%}, explicá qué necesitarías para aumentarla.
"""

    messages = [{"role": "user", "content": task}]

    # Parámetros según la decisión
    create_params = {
        "model": decision.model_to_use,
        "max_tokens": 8000 if decision.use_extended_thinking else 4096,
        "tools": TOOLS,
        "messages": messages,
        "system": system
    }

    if decision.use_extended_thinking:
        create_params["thinking"] = {
            "type": "enabled",
            "budget_tokens": 5000
        }
        print("[Extended Thinking activado — analizando en profundidad...]")

    result = {"escalated": False, "changes_proposed": [], "confidence": None}

    for _ in range(10):
        response = client.messages.create(**create_params)

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "thinking"):
                    print(f"\n[Razonamiento interno - primeras líneas]\n{block.thinking[:300]}...")
                elif hasattr(block, "text"):
                    print(f"\n[Respuesta]\n{block.text}")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "report_confidence":
                        conf = block.input.get("confidence", 0)
                        reason = block.input.get("reason", "")
                        result["confidence"] = conf
                        print(f"\n[Confianza reportada: {conf:.0%}]")
                        print(f"  Razón: {reason}")

                        if conf < decision.confidence_required:
                            print(f"\n[⚠️ CONFIANZA INSUFICIENTE — escalando]")
                            result["escalated"] = True
                            result["escalation_reason"] = f"Confianza {conf:.0%} < requerida {decision.confidence_required:.0%}"
                            return result

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Confianza {conf:.0%} aceptada. Podés proceder."
                        })

                    elif block.name == "propose_change":
                        change = block.input
                        result["changes_proposed"].append(change)
                        print(f"\n[Cambio propuesto en {change.get('file')}]")
                        print(f"  {change.get('description', '')[:100]}")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Cambio registrado para revisión."
                        })

            messages.append({"role": "user", "content": tool_results})

    return result


# --- Demo ---

if __name__ == "__main__":
    task = "Necesito cambiar la lógica de validación de contraseñas en auth.py para soportar contraseñas de hasta 128 caracteres"

    print("\n" + "=" * 70)
    print("ESCENARIO 1: Branch de feature en dev — modo normal")
    print("=" * 70)
    result1 = run_adaptive_agent(
        task=task,
        ctx=RuntimeContext(stage="dev", branch="feature/password-length", files_touched=["auth.py"])
    )

    print("\n\n" + "=" * 70)
    print("ESCENARIO 2: Mismo cambio en producción — modo conservador")
    print("=" * 70)
    result2 = run_adaptive_agent(
        task=task,
        ctx=RuntimeContext(stage="production", branch="hotfix/password-length", files_touched=["auth.py"])
    )

    print("\n\n" + "=" * 70)
    print("ESCENARIO 3: Tercer intento fallido — escalamiento automático")
    print("=" * 70)
    result3 = run_adaptive_agent(
        task="Arreglar el bug de autenticación que lleva 3 ciclos sin solución",
        ctx=RuntimeContext(
            stage="staging",
            branch="fix/auth-bug",
            test_failures=3,
            files_touched=["auth.py", "sessions.py"]
        )
    )

    print("\n\n[Resumen de resultados]")
    print(f"Escenario 1 — Escalado: {result1.get('escalated', False)}")
    print(f"Escenario 2 — Escalado: {result2.get('escalated', False)}")
    print(f"Escenario 3 — Escalado: {result3.get('escalated', False)}, Razón: {result3.get('reason', 'N/A')}")
