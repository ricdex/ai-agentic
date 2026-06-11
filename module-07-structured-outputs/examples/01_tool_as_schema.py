"""
Módulo 7 — Ejemplo 1: Tool use como schema enforcement

Demuestra:
- Definir un schema de output via tool definition
- Forzar al modelo a producir ese schema con tool_choice
- Por qué esto es más robusto que pedirle "respondé en JSON"

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 01_tool_as_schema.py
"""

import json
import anthropic

client = anthropic.Anthropic()

TRIAGE_TOOL = {
    "name": "submit_triage",
    "description": "Enviá el triage estructurado del issue de GitHub",
    "input_schema": {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Impacto en el sistema en producción"
            },
            "category": {
                "type": "string",
                "enum": ["bug", "performance", "security", "ux", "feature_request"],
                "description": "Tipo de issue"
            },
            "affected_components": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de componentes afectados (ej: ['auth', 'payments'])"
            },
            "estimated_effort": {
                "type": "string",
                "enum": ["XS", "S", "M", "L", "XL"],
                "description": "Esfuerzo estimado de resolución"
            },
            "needs_clarification": {
                "type": "boolean",
                "description": "Si el issue necesita más información del autor"
            },
            "clarification_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Preguntas para el autor (solo si needs_clarification=true)"
            },
            "one_line_summary": {
                "type": "string",
                "description": "Resumen técnico en una línea, máximo 80 caracteres"
            }
        },
        "required": [
            "severity", "category", "affected_components",
            "estimated_effort", "needs_clarification", "one_line_summary"
        ]
    }
}


def triage_issue(title: str, body: str) -> dict:
    """Retorna un dict estructurado con el triage del issue."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=[TRIAGE_TOOL],
        tool_choice={"type": "tool", "name": "submit_triage"},
        messages=[{
            "role": "user",
            "content": f"Triageá este issue de GitHub:\n\n**{title}**\n\n{body}"
        }]
    )

    # Con tool_choice forzado, siempre es un tool_use block
    tool_block = next(b for b in response.content if b.type == "tool_use")
    return tool_block.input


SAMPLE_ISSUES = [
    {
        "title": "Users can't checkout — 500 errors on /api/payments",
        "body": (
            "Since the deploy 2 hours ago, all checkout attempts return 500. "
            "Logs show: 'NullPointerException in PaymentProcessor.charge()'. "
            "Affecting ~100% of users trying to purchase. Revenue impact: ~$50k/hour."
        )
    },
    {
        "title": "Dashboard loads slowly",
        "body": "The admin dashboard takes like 5-10 seconds to load sometimes. Not sure when it started."
    },
    {
        "title": "Add dark mode to settings page",
        "body": "It would be nice to have a dark mode option. The current white background is harsh at night."
    },
    {
        "title": "JWT tokens not expiring correctly",
        "body": (
            "I noticed that some users remain logged in even after the token should have expired. "
            "Not sure if this is by design or a bug. Using the standard JWT library."
        )
    }
]


if __name__ == "__main__":
    for issue in SAMPLE_ISSUES:
        print(f"\nIssue: {issue['title']}")
        print("-" * 60)

        result = triage_issue(issue["title"], issue["body"])

        print(f"  Severity:    {result['severity'].upper()}")
        print(f"  Category:    {result['category']}")
        print(f"  Components:  {', '.join(result['affected_components'])}")
        print(f"  Effort:      {result['estimated_effort']}")
        print(f"  Summary:     {result['one_line_summary']}")

        if result.get("needs_clarification") and result.get("clarification_questions"):
            print(f"  Preguntas:")
            for q in result["clarification_questions"]:
                print(f"    - {q}")

        # Routing automático basado en datos estructurados
        if result["severity"] == "critical":
            print(f"  ⚠️  ALERTA: Escalar a on-call inmediatamente")
        if result["category"] == "security":
            print(f"  🔒 Notificar al equipo de seguridad")
