"""
Módulo 2 — Ejemplo 2: Coordinación multi-agente (Orquestador + Ejecutores)

Patrón: un agente orquestador que planifica y delega a agentes especializados.

Caso real: code review automatizado
- Orquestador: recibe un PR diff, decide qué aspectos revisar
- Ejecutor A: revisa seguridad
- Ejecutor B: revisa performance
- Ejecutor C: revisa tests

Cada ejecutor usa un modelo diferente según la complejidad de su tarea.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python multi_agent.py
"""

import anthropic
from dataclasses import dataclass

client = anthropic.Anthropic()


@dataclass
class ReviewResult:
    reviewer: str
    model_used: str
    findings: list[str]
    severity: str  # critical | warning | info | ok
    summary: str


# --- Agentes especializados ---

def security_reviewer(diff: str) -> ReviewResult:
    """
    Agente especializado en seguridad.
    Usa Opus para razonamiento profundo en problemas de seguridad.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",  # Sonnet es suficiente para este análisis
        max_tokens=2048,
        system=(
            "Sos un experto en seguridad de aplicaciones. "
            "Analizás cambios de código buscando vulnerabilidades. "
            "Respondé con JSON: {findings: [...], severity: 'critical|warning|info|ok', summary: '...'}"
        ),
        messages=[{
            "role": "user",
            "content": f"Revisá este diff por vulnerabilidades de seguridad:\n\n```diff\n{diff}\n```"
        }]
    )

    text = response.content[0].text
    try:
        import json
        # Extraer JSON de la respuesta (puede estar en un bloque de código)
        start = text.find("{")
        end = text.rfind("}") + 1
        data = json.loads(text[start:end])
        return ReviewResult(
            reviewer="security",
            model_used="claude-sonnet-4-6",
            findings=data.get("findings", []),
            severity=data.get("severity", "info"),
            summary=data.get("summary", text)
        )
    except Exception:
        return ReviewResult(
            reviewer="security",
            model_used="claude-sonnet-4-6",
            findings=[text],
            severity="info",
            summary=text[:200]
        )


def performance_reviewer(diff: str) -> ReviewResult:
    """
    Agente especializado en performance.
    Usa Haiku para análisis rápido de patrones conocidos.
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku es suficiente para patrones de perf
        max_tokens=1024,
        system=(
            "Sos un experto en performance. Buscás: N+1 queries, loops ineficientes, "
            "falta de índices, operaciones O(n²) evitables, falta de caching. "
            "Respondé con JSON: {findings: [...], severity: 'critical|warning|info|ok', summary: '...'}"
        ),
        messages=[{
            "role": "user",
            "content": f"Revisá este diff por problemas de performance:\n\n```diff\n{diff}\n```"
        }]
    )

    text = response.content[0].text
    try:
        import json
        start = text.find("{")
        end = text.rfind("}") + 1
        data = json.loads(text[start:end])
        return ReviewResult(
            reviewer="performance",
            model_used="claude-haiku-4-5-20251001",
            findings=data.get("findings", []),
            severity=data.get("severity", "info"),
            summary=data.get("summary", text)
        )
    except Exception:
        return ReviewResult(
            reviewer="performance",
            model_used="claude-haiku-4-5-20251001",
            findings=[text],
            severity="info",
            summary=text[:200]
        )


def test_coverage_reviewer(diff: str) -> ReviewResult:
    """
    Agente que verifica si el código nuevo tiene tests.
    Usa Haiku — es una tarea mecánica.
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=(
            "Revisás si los cambios de código incluyen tests adecuados. "
            "Buscás: funciones nuevas sin tests, casos borde no testeados, "
            "código de error no testeado. "
            "Respondé con JSON: {findings: [...], severity: 'critical|warning|info|ok', summary: '...'}"
        ),
        messages=[{
            "role": "user",
            "content": f"¿Este diff tiene tests adecuados?\n\n```diff\n{diff}\n```"
        }]
    )

    text = response.content[0].text
    try:
        import json
        start = text.find("{")
        end = text.rfind("}") + 1
        data = json.loads(text[start:end])
        return ReviewResult(
            reviewer="test_coverage",
            model_used="claude-haiku-4-5-20251001",
            findings=data.get("findings", []),
            severity=data.get("severity", "info"),
            summary=data.get("summary", text)
        )
    except Exception:
        return ReviewResult(
            reviewer="test_coverage",
            model_used="claude-haiku-4-5-20251001",
            findings=[text],
            severity="info",
            summary=text[:200]
        )


# --- Orquestador ---

ORCHESTRATOR_TOOLS = [
    {
        "name": "run_security_review",
        "description": "Ejecuta el agente de revisión de seguridad sobre el diff.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Áreas específicas a revisar: ['auth', 'sql', 'xss', 'secrets']"
                }
            },
            "required": []
        }
    },
    {
        "name": "run_performance_review",
        "description": "Ejecuta el agente de revisión de performance sobre el diff.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "run_test_coverage_review",
        "description": "Verifica si el diff incluye tests adecuados.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "submit_final_review",
        "description": "Envía el resultado consolidado del code review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["approve", "request_changes", "comment"],
                    "description": "Decisión del review"
                },
                "summary": {
                    "type": "string",
                    "description": "Resumen ejecutivo del review (2-3 oraciones)"
                },
                "blocking_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Issues que bloquean el merge"
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sugerencias no bloqueantes"
                }
            },
            "required": ["decision", "summary", "blocking_issues", "suggestions"]
        }
    }
]


def orchestrate_review(diff: str, pr_title: str, pr_description: str) -> dict:
    """
    Orquestador que decide qué reviews correr y consolida resultados.
    """
    review_results: dict[str, ReviewResult] = {}

    def execute_orchestrator_tool(name: str, inputs: dict) -> str:
        nonlocal review_results

        if name == "run_security_review":
            print("  [Ejecutor] Corriendo security review...")
            result = security_reviewer(diff)
            review_results["security"] = result
            return f"Security review completado. Severity: {result.severity}. Findings: {len(result.findings)}. Summary: {result.summary}"

        elif name == "run_performance_review":
            print("  [Ejecutor] Corriendo performance review...")
            result = performance_reviewer(diff)
            review_results["performance"] = result
            return f"Performance review completado. Severity: {result.severity}. Summary: {result.summary}"

        elif name == "run_test_coverage_review":
            print("  [Ejecutor] Verificando cobertura de tests...")
            result = test_coverage_reviewer(diff)
            review_results["tests"] = result
            return f"Test coverage review completado. Severity: {result.severity}. Summary: {result.summary}"

        elif name == "submit_final_review":
            return "Review consolidado y enviado."

        return f"ERROR: herramienta desconocida {name}"

    system = (
        "Sos un tech lead que hace code review. "
        "Tenés agentes especializados para seguridad, performance y tests. "
        "Decidí cuáles ejecutar basándote en el PR, luego consolidá los resultados "
        "en un review final con decisión clara: approve, request_changes, o comment."
    )

    user_content = f"""PR: {pr_title}
Descripción: {pr_description}

Diff:
```diff
{diff}
```

Analizá este PR y usá los agentes especializados según consideres necesario."""

    messages = [{"role": "user", "content": user_content}]
    final_review = {}

    print(f"\n[Orquestador] Revisando PR: {pr_title}")
    print("=" * 60)

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=ORCHESTRATOR_TOOLS,
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
                    result_text = execute_orchestrator_tool(block.name, block.input)

                    if block.name == "submit_final_review":
                        final_review = block.input

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text
                    })

            messages.append({"role": "user", "content": tool_results})

    return {
        "final_review": final_review,
        "individual_results": {k: v.__dict__ for k, v in review_results.items()}
    }


# --- Demo ---

if __name__ == "__main__":
    sample_diff = """
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,15 @@ class AuthService:
     def __init__(self, db):
         self.db = db

+    def login(self, username: str, password: str) -> dict:
+        # Verificar credenciales
+        query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
+        user = self.db.execute(query).fetchone()
+        if not user:
+            raise ValueError("Credenciales inválidas")
+        token = str(user['id']) + '_token'
+        return {"token": token, "user_id": user['id']}
+
     def logout(self, token: str):
         self.db.execute("DELETE FROM sessions WHERE token=?", [token])
"""

    result = orchestrate_review(
        diff=sample_diff,
        pr_title="feat: agregar endpoint de login",
        pr_description="Agrega autenticación básica con username/password"
    )

    print("\n[Resultado del Review]")
    print("=" * 60)
    if result["final_review"]:
        print(f"Decisión: {result['final_review'].get('decision', 'N/A')}")
        print(f"Resumen: {result['final_review'].get('summary', 'N/A')}")
        print(f"Issues bloqueantes: {result['final_review'].get('blocking_issues', [])}")
        print(f"Sugerencias: {result['final_review'].get('suggestions', [])}")
