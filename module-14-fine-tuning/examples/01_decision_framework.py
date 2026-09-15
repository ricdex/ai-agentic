"""
Módulo 14 — Ejemplo 1: Framework de decisión — prompting vs fine-tuning

Antes de considerar entrenar nada, este script mide si Claude con un buen
prompt (few-shot, sin fine-tuning) ya alcanza el umbral de calidad que
necesitás. La mayoría de las veces, sí — y esto se puede confirmar en
minutos en vez de asumirlo.

Tarea de ejemplo: clasificar la urgencia de un ticket de soporte
(low / medium / high / critical), el mismo tipo de tarea "angosta y de
alto volumen" que en 14.4 se plantea como candidata a fine-tuning.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 01_decision_framework.py
"""

import anthropic

client = anthropic.Anthropic()

FEW_SHOT_EXAMPLES = """
Ejemplos:
Ticket: "¿Cuál es el horario de atención?"
Urgencia: low

Ticket: "El sitio está caído, ningún cliente puede pagar, estamos perdiendo ventas ahora mismo."
Urgencia: critical

Ticket: "Mi pedido llegó con una pieza rota, ¿pueden mandarme un reemplazo?"
Urgencia: medium

Ticket: "No puedo actualizar mi método de pago, la tarjeta vieja venció y necesito la suscripción para mañana."
Urgencia: high
"""

TOOL = {
    "name": "classify_urgency",
    "description": "Clasifica la urgencia de un ticket de soporte",
    "input_schema": {
        "type": "object",
        "properties": {"urgency": {"type": "string", "enum": ["low", "medium", "high", "critical"]}},
        "required": ["urgency"],
    },
}

# Dataset de eval etiquetado a mano — el ground truth contra el que se mide todo.
EVAL_SET = [
    ("¿Tienen envío a otras provincias?", "low"),
    ("El servidor de producción está devolviendo 500 en todos los endpoints hace 10 minutos.", "critical"),
    ("Quiero cambiar la talla de una remera que compré ayer, todavía no la usé.", "low"),
    ("Mi tarjeta fue rechazada 3 veces y necesito renovar el plan hoy o pierdo el acceso.", "high"),
    ("El producto llegó abierto y le falta una pieza, necesito el reemplazo para el fin de semana.", "medium"),
    ("Detecté que se filtraron datos de tarjetas de otros usuarios en mi cuenta.", "critical"),
    ("¿El descuento del 10% aplica también a envío?", "low"),
    ("Llevo 3 intentos fallidos de pago y mi evento es en 2 días, necesito ayuda urgente.", "high"),
    ("La app se cierra sola al abrir la sección de pagos, en todos los dispositivos.", "critical"),
    ("¿Puedo cambiar la dirección de envío después de confirmar el pedido?", "low"),
]


def classify(ticket: str) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # el modelo más barato que resuelva la tarea, ver 14.2
        max_tokens=100,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "classify_urgency"},
        messages=[{"role": "user", "content": f"{FEW_SHOT_EXAMPLES}\n\nTicket: \"{ticket}\"\nUrgencia:"}],
    )
    tool_call = next(b for b in response.content if b.type == "tool_use")
    return tool_call.input["urgency"]


def run_eval() -> float:
    correct = 0
    for ticket, expected in EVAL_SET:
        predicted = classify(ticket)
        status = "✓" if predicted == expected else "✗"
        print(f"{status} esperado={expected:8s} predicho={predicted:8s}  {ticket[:60]}")
        correct += predicted == expected
    return correct / len(EVAL_SET)


if __name__ == "__main__":
    accuracy = run_eval()
    print(f"\nAccuracy con prompting + few-shot: {accuracy:.2f} ({int(accuracy * len(EVAL_SET))}/{len(EVAL_SET)})")

    THRESHOLD = 0.85
    if accuracy >= THRESHOLD:
        print(
            f"\n>= {THRESHOLD}: prompting ya alcanza el umbral. No hay caso para fine-tuning "
            "todavía — ver 14.1. Si el volumen es muy alto, la próxima palanca es costo/latencia "
            "(02_lora_classifier.py), no calidad."
        )
    else:
        print(
            f"\n< {THRESHOLD}: identificá si el gap es de conocimiento del dominio (agregá contexto "
            "al prompt / RAG) antes de asumir que hace falta entrenar un modelo."
        )
