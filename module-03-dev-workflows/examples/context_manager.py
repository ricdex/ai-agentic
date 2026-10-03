"""
Módulo 3 — Ejemplo 2: Context engineering para agentes largos

El contexto es un recurso finito: cada token que entra compite por la atención
del modelo y se paga en cada turno. Este ejemplo implementa las cuatro palancas
que más impacto tienen, de la más barata a la más cara:

1. Recortar lo que ENTRA (tool outputs gigantes → cabeza + cola)
2. Ordenar para la atención (lo más relevante al principio y al final)
3. Limpiar resultados viejos de tools (context editing, server-side)
4. Compactar o hacer handoff a una sesión nueva con estado explícito

La lógica de decisión es pura (sin red) y está testeada en tests/.
Las llamadas a Claude reciben el cliente por parámetro para poder testearlas.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python context_manager.py
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import anthropic

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5-5")

# Heurística grosera: ~4 caracteres por token en inglés/código, algo menos en
# español. Sirve para decidir umbrales; para facturación exacta usá
# client.messages.count_tokens(...).
CHARS_PER_TOKEN = 4

# Betas de context management (ver README 3.7)
CONTEXT_EDITING_BETA = "context-management-2025-06-27"
COMPACTION_BETA = "compact-2026-01-12"


# ---------------------------------------------------------------------------
# 1. Recortar lo que entra
# ---------------------------------------------------------------------------

def estimate_tokens(value) -> int:
    """Estima tokens de un string o de una estructura de mensajes."""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, len(text) // CHARS_PER_TOKEN) if text else 0


def truncate_tool_output(text: str, max_chars: int = 8_000) -> str:
    """Conserva cabeza y cola de un output largo.

    Los logs y stack traces tienen la información útil al principio (comando,
    contexto) y al final (el error). El medio suele ser ruido repetido.
    Se aplica ANTES de agregar el tool_result al historial, así el historial
    sigue siendo append-only (no rompe prompt caching).
    """
    if max_chars < 200:
        raise ValueError("max_chars debe ser >= 200 para dejar espacio al marcador")
    if len(text) <= max_chars:
        return text
    marker = f"\n\n[... {len(text) - max_chars} caracteres omitidos ...]\n\n"
    budget = max_chars - len(marker)
    head = budget * 2 // 3
    tail = budget - head
    return text[:head] + marker + text[-tail:]


# ---------------------------------------------------------------------------
# 2. Ordenar para la atención ("lost in the middle")
# ---------------------------------------------------------------------------

def order_for_attention(items_by_relevance: list) -> list:
    """Reordena items (ya ordenados de más a menos relevante) para que los más
    relevantes queden en los extremos del contexto y los menos en el medio.

    [1, 2, 3, 4, 5] -> [1, 3, 5, 4, 2]
    """
    front = items_by_relevance[0::2]
    back = items_by_relevance[1::2]
    return front + back[::-1]


# ---------------------------------------------------------------------------
# 3 y 4. Política: qué hacer según cuánto contexto llevamos usado
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContextPolicy:
    """Umbrales como fracción de la ventana. Configurables por env/config, no hardcode."""

    window_tokens: int = 200_000
    clear_at: float = 0.40     # limpiar tool results viejos
    compact_at: float = 0.70   # resumir el historial
    handoff_at: float = 0.90   # cortar la sesión y arrancar una nueva con estado

    def __post_init__(self):
        if not 0 < self.clear_at < self.compact_at < self.handoff_at <= 1:
            raise ValueError("Se requiere 0 < clear_at < compact_at < handoff_at <= 1")

    def decide(self, used_tokens: int) -> str:
        ratio = used_tokens / self.window_tokens
        if ratio >= self.handoff_at:
            return "handoff"
        if ratio >= self.compact_at:
            return "compact"
        if ratio >= self.clear_at:
            return "clear_tool_results"
        return "ok"


def context_management_for(action: str) -> dict:
    """Traduce la decisión a kwargs del API (server-side context management).

    - clear_tool_results → context editing: el API vacía tool results viejos.
    - compact            → compaction: el API resume el historial temprano.
    Ninguno de los dos edita tu lista `messages`: lo hace el servidor, así que
    el historial local sigue siendo append-only.
    """
    if action == "clear_tool_results":
        return {
            "betas": [CONTEXT_EDITING_BETA],
            "context_management": {"edits": [{"type": "clear_tool_uses_20250919"}]},
        }
    if action == "compact":
        return {
            "betas": [COMPACTION_BETA],
            "context_management": {"edits": [{"type": "compact_20260112"}]},
        }
    return {}


# ---------------------------------------------------------------------------
# Handoff: estado explícito para una sesión nueva
# ---------------------------------------------------------------------------

@dataclass
class TaskState:
    goal: str
    done: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)

    def to_handoff(self) -> str:
        """Nota de progreso que una sesión nueva lee como primer mensaje.

        Un resumen libre pierde detalles; un estado estructurado obliga a
        conservar lo que la siguiente sesión necesita para continuar.
        """
        def section(title: str, items: list[str]) -> str:
            body = "\n".join(f"- {i}" for i in items) if items else "- (nada)"
            return f"## {title}\n{body}"

        return "\n\n".join([
            f"# Handoff\n\n**Objetivo:** {self.goal}",
            section("Hecho", self.done),
            section("Pendiente (en orden)", self.pending),
            section("Decisiones tomadas (no re-discutir)", self.decisions),
            section("Archivos tocados", self.files_touched),
        ])


# ---------------------------------------------------------------------------
# Loop con context management
# ---------------------------------------------------------------------------

def run_turn(client, messages: list, policy: ContextPolicy, tools: list | None = None):
    """Un turno del agente aplicando la política de contexto.

    Devuelve (response, action). Si la acción es "handoff", NO llama al modelo:
    el caller debe arrancar una sesión nueva con TaskState.to_handoff().
    """
    action = policy.decide(estimate_tokens(messages))
    if action == "handoff":
        return None, action

    extra = context_management_for(action)
    kwargs = {"model": MODEL, "max_tokens": 16_000, "messages": messages}
    if tools:
        kwargs["tools"] = tools

    if extra:
        response = client.beta.messages.create(**kwargs, **extra)
    else:
        response = client.messages.create(**kwargs)

    # Agregar el content COMPLETO, no solo el texto: si hubo compaction, el
    # bloque `compaction` tiene que volver en el próximo request.
    messages.append({"role": "assistant", "content": response.content})
    return response, action


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _demo():  # pragma: no cover - llama a la API real
    print("1) Recorte de un log de CI de 50k caracteres")
    log = "PASS test_ok\n" * 3000 + "FAIL test_checkout: AssertionError: total 99 != 100\n"
    short = truncate_tool_output(log, max_chars=2_000)
    print(f"   {estimate_tokens(log)} → {estimate_tokens(short)} tokens estimados")
    print(f"   ¿Conserva el error? {'FAIL test_checkout' in short}\n")

    print("2) Orden para la atención")
    print(f"   {order_for_attention(['doc1', 'doc2', 'doc3', 'doc4', 'doc5'])}\n")

    print("3) Política por uso de contexto (ventana 200k)")
    policy = ContextPolicy()
    for used in (20_000, 90_000, 150_000, 185_000):
        print(f"   {used:>7} tokens → {policy.decide(used)}")
    print()

    print("4) Turno real con Claude")
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": "Resumí en una línea qué es context engineering."}]
    response, action = run_turn(client, messages, policy)
    text = next(b.text for b in response.content if b.type == "text")
    print(f"   acción={action}  →  {text}\n")

    state = TaskState(
        goal="Arreglar el cálculo de descuentos en checkout",
        done=["Reproducido el bug con test_checkout_discount"],
        pending=["Corregir redondeo en apply_discount()", "Correr suite completa"],
        decisions=["Usar Decimal, no float, para montos"],
        files_touched=["src/checkout/discounts.py"],
    )
    print("5) Handoff para una sesión nueva\n")
    print(state.to_handoff())


if __name__ == "__main__":  # pragma: no cover
    _demo()
