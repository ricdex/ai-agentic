"""
Módulo 10 — Ejemplo 2: LLM-as-Judge

Evalúa aspectos subjetivos del output del agente que no se pueden
medir con tests determinísticos:
- Calidad del código producido (idiomático, mínimo, sin side effects)
- Claridad del mensaje del PR
- Si el fix fue conservador o excesivo

Usa Claude Haiku como juez (barato, rápido).
Incluye calibración para evitar sesgos del juez.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 02_llm_judge.py
"""

import json
from dataclasses import dataclass
import anthropic

client = anthropic.Anthropic()

JUDGE_MODEL = "claude-haiku-4-5-20251001"  # Haiku para evals — barato y suficientemente bueno


@dataclass
class JudgeResult:
    score: float        # 0.0 a 1.0
    reasoning: str
    issues: list[str]   # problemas detectados


def judge_code_quality(original: str, fixed: str, issue_description: str) -> JudgeResult:
    """Evalúa si el fix de código es de buena calidad."""
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        tools=[{
            "name": "submit_judgment",
            "description": "Enviá tu evaluación del fix de código",
            "input_schema": {
                "type": "object",
                "properties": {
                    "score": {
                        "type": "number",
                        "description": "Score de 0.0 a 1.0"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Una oración explicando el score"
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de problemas encontrados (vacía si no hay)"
                    }
                },
                "required": ["score", "reasoning", "issues"]
            }
        }],
        tool_choice={"type": "tool", "name": "submit_judgment"},
        messages=[{
            "role": "user",
            "content": f"""Evaluá la calidad de este fix de código en una escala de 0.0 a 1.0.

Issue resuelto: {issue_description}

Código original:
```python
{original}
```

Código arreglado:
```python
{fixed}
```

Criterios de evaluación:
- 1.0: Fix mínimo, preciso, idiomático, sin cambios innecesarios
- 0.7: Fix correcto pero con algo de código innecesario
- 0.4: Fix correcto pero ruidoso (demasiados cambios, estilo inconsistente)
- 0.0: Fix incorrecto o introduce nuevos problemas"""
        }]
    )

    result = next(b for b in response.content if b.type == "tool_use").input
    return JudgeResult(
        score=float(result["score"]),
        reasoning=result["reasoning"],
        issues=result.get("issues", [])
    )


def judge_pr_message(pr_title: str, pr_body: str, issue_description: str) -> JudgeResult:
    """Evalúa si el mensaje del PR es claro y útil."""
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        tools=[{
            "name": "submit_judgment",
            "description": "Enviá tu evaluación del mensaje del PR",
            "input_schema": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "issues": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["score", "reasoning", "issues"]
            }
        }],
        tool_choice={"type": "tool", "name": "submit_judgment"},
        messages=[{
            "role": "user",
            "content": f"""Evaluá la calidad del mensaje de este Pull Request.

Issue original: {issue_description}

PR Title: {pr_title}
PR Body: {pr_body}

Criterios:
- 1.0: Título claro, body explica qué cambió y por qué, menciona el issue original
- 0.7: Comprensible pero le falta contexto o el "por qué"
- 0.4: Vago o no conecta con el issue
- 0.0: Incomprensible o vacío"""
        }]
    )

    result = next(b for b in response.content if b.type == "tool_use").input
    return JudgeResult(
        score=float(result["score"]),
        reasoning=result["reasoning"],
        issues=result.get("issues", [])
    )


def judge_conservatism(original_files: list[str], modified_files: list[str],
                       issue_description: str) -> JudgeResult:
    """Evalúa si el agente fue conservador (tocó solo lo necesario)."""
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        tools=[{
            "name": "submit_judgment",
            "description": "Evaluá si el agente fue conservador",
            "input_schema": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "issues": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["score", "reasoning", "issues"]
            }
        }],
        tool_choice={"type": "tool", "name": "submit_judgment"},
        messages=[{
            "role": "user",
            "content": f"""Evaluá si el agente fue conservador y tocó solo lo necesario.

Issue: {issue_description}
Archivos disponibles: {original_files}
Archivos modificados: {modified_files}

Criterios:
- 1.0: Solo modificó el archivo donde estaba el bug
- 0.7: Modificó algún archivo relacionado pero con justificación
- 0.4: Tocó archivos innecesarios
- 0.0: Modificó archivos sin relación con el issue"""
        }]
    )

    result = next(b for b in response.content if b.type == "tool_use").input
    return JudgeResult(
        score=float(result["score"]),
        reasoning=result["reasoning"],
        issues=result.get("issues", [])
    )


# --- Demo con ejemplos reales ---

DEMO_CASES = [
    {
        "issue": "binary_search retorna IndexError cuando el array está vacío",
        "original": """def binary_search(arr, target):
    left, right = 0, len(arr)
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1""",
        "good_fix": """def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1""",
        "poor_fix": """def binary_search(arr, target):
    if not arr:
        return -1
    if len(arr) == 1:
        return 0 if arr[0] == target else -1
    left = 0
    right = len(arr) - 1
    count = 0
    while left <= right and count < 1000:  # safety limit
        count += 1
        mid = (left + right) // 2
        current = arr[mid]
        if current == target:
            return mid
        elif current < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1""",
        "pr_title_good": "fix: corregir IndexError en binary_search con array vacío",
        "pr_body_good": "El índice `right` se inicializaba como `len(arr)` en lugar de `len(arr) - 1`, causando acceso out-of-bounds.\n\nFix: cambiar inicialización de `right` a `len(arr) - 1`.\n\nFixes #42",
        "pr_title_poor": "fixed bug",
        "pr_body_poor": "I fixed the issue you reported.",
    }
]


if __name__ == "__main__":
    for case in DEMO_CASES:
        print(f"\nIssue: {case['issue']}")
        print("=" * 60)

        # Evaluar código bueno vs código pobre
        good_result = judge_code_quality(case["original"], case["good_fix"], case["issue"])
        poor_result = judge_code_quality(case["original"], case["poor_fix"], case["issue"])

        print("\n[Code Quality]")
        print(f"  Fix bueno:  {good_result.score:.2f} — {good_result.reasoning}")
        print(f"  Fix pobre:  {poor_result.score:.2f} — {poor_result.reasoning}")
        if poor_result.issues:
            print(f"  Problemas detectados: {poor_result.issues}")

        # Evaluar PR message
        good_pr = judge_pr_message(case["pr_title_good"], case["pr_body_good"], case["issue"])
        poor_pr = judge_pr_message(case["pr_title_poor"], case["pr_body_poor"], case["issue"])

        print("\n[PR Message Quality]")
        print(f"  PR bueno: {good_pr.score:.2f} — {good_pr.reasoning}")
        print(f"  PR pobre: {poor_pr.score:.2f} — {poor_pr.reasoning}")

        # Score combinado
        combined_good = (good_result.score + good_pr.score) / 2
        combined_poor = (poor_result.score + poor_pr.score) / 2
        print(f"\n[Score combinado]")
        print(f"  Agente bueno: {combined_good:.2f}")
        print(f"  Agente pobre: {combined_poor:.2f}")
        print(f"  Gap:          {combined_good - combined_poor:.2f} puntos")
