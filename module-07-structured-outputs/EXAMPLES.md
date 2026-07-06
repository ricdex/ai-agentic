# Módulo 7 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Tool use como schema enforcement

**Archivo:** `examples/01_tool_as_schema.py`

Forza al modelo a retornar siempre el mismo schema usando `tool_choice`. Sin esto, el modelo puede responder con texto libre.

```python
import anthropic
import json

client = anthropic.Anthropic()

ANALYZE_TOOL = {
    "name": "submit_analysis",
    "description": "Enviá el análisis estructurado del issue",
    "input_schema": {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"]
            },
            "category": {
                "type": "string",
                "enum": ["bug", "performance", "security", "feature"]
            },
            "affected_components": {
                "type": "array",
                "items": {"type": "string"}
            },
            "estimated_hours": {
                "type": "number"
            },
            "requires_immediate_action": {
                "type": "boolean"
            },
            "one_line_summary": {
                "type": "string",
                "description": "Resumen en una línea para alertas"
            }
        },
        "required": ["severity", "category", "affected_components",
                     "requires_immediate_action", "one_line_summary"]
    }
}

def analyze_issue(issue_text: str) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        tools=[ANALYZE_TOOL],
        tool_choice={"type": "tool", "name": "submit_analysis"},  # fuerza el tool
        messages=[{"role": "user", "content": issue_text}]
    )
    return response.content[0].input  # siempre es el schema que definimos

def process(issue: str):
    analysis = analyze_issue(issue)
    print(f"\nIssue: {issue[:80]}...")
    print(f"  severity:           {analysis['severity']}")
    print(f"  category:           {analysis['category']}")
    print(f"  components:         {analysis['affected_components']}")
    print(f"  estimated_hours:    {analysis.get('estimated_hours', 'N/A')}")
    print(f"  immediate_action:   {analysis['requires_immediate_action']}")
    print(f"  summary:            {analysis['one_line_summary']}")

    if analysis["severity"] == "critical" and analysis["requires_immediate_action"]:
        print(f"  🚨 ALERTA: {analysis['one_line_summary']}")

    return analysis

issues = [
    "El endpoint /api/checkout devuelve 500 para todos los usuarios desde las 14:30. Los logs muestran 'NullPointerException in PaymentService.charge()'. El equipo de soporte reporta 200+ tickets en los últimos 30 minutos.",
    "Sería bueno agregar un botón de 'exportar a CSV' en la pantalla de reportes para que los usuarios puedan descargar sus datos.",
    "La página de listado de productos tarda 8 segundos en cargar cuando hay más de 1000 productos. Los usuarios abandonan antes de ver los resultados.",
    "El campo de contraseña en el formulario de registro acepta contraseñas de 1 caracter. Potencial riesgo de seguridad.",
]

for issue in issues:
    process(issue)
    print()
```

**Output esperado:**

```
Issue: El endpoint /api/checkout devuelve 500 para todos los usuarios desde las 14:30...
  severity:           critical
  category:           bug
  components:         ['PaymentService', 'checkout endpoint', 'payment processing']
  estimated_hours:    2
  immediate_action:   True
  summary:            Checkout caído — NullPointerException en PaymentService afecta 100% de usuarios
  🚨 ALERTA: Checkout caído — NullPointerException en PaymentService afecta 100% de usuarios

Issue: Sería bueno agregar un botón de 'exportar a CSV' en la pantalla de reportes...
  severity:           low
  category:           feature
  components:         ['reports', 'UI']
  estimated_hours:    4
  immediate_action:   False
  summary:            Feature request: exportar datos de reportes a CSV

Issue: La página de listado de productos tarda 8 segundos en cargar cuando hay más de 1000...
  severity:           high
  category:           performance
  components:         ['product listing', 'database queries']
  estimated_hours:    8
  immediate_action:   False
  summary:            Product listing con +1000 items carga en 8s — impacto en conversión

Issue: El campo de contraseña en el formulario de registro acepta contraseñas de 1 caracter...
  severity:           high
  category:           security
  components:         ['registration form', 'authentication', 'password validation']
  estimated_hours:    2
  immediate_action:   False
  summary:            Validación débil de contraseña — mínimo de 1 char en registro
```

**Qué muestra:**
- El primer issue (checkout caído) es `critical` + `requires_immediate_action: True` → dispara la alerta
- El feature request es `low` + `requires_immediate_action: False` → no dispara nada
- El schema se respeta siempre: `severity` siempre es uno de los 4 valores del enum
- `affected_components` siempre es un array, nunca un string — el tipado es estricto

---

## Ejemplo 2 — Extracción con Pydantic: validación y tipos

**Archivo:** `examples/02_pydantic_extractor.py`

Pipeline completo de extracción de información de texto no estructurado (logs de incidentes, emails, reportes).

```python
import anthropic
import json
from pydantic import BaseModel, validator
from typing import Literal
from datetime import datetime

client = anthropic.Anthropic()

class IncidentReport(BaseModel):
    incident_time: str
    affected_endpoint: str | None
    error_type: str
    failing_service: str
    user_impact_percent: int | None
    severity: Literal["low", "medium", "high", "critical"]
    is_ongoing: bool
    suggested_action: str

    @validator("user_impact_percent")
    def validate_impact(cls, v):
        if v is not None and not 0 <= v <= 100:
            raise ValueError(f"user_impact_percent debe ser 0-100, recibido: {v}")
        return v

EXTRACT_TOOL = {
    "name": "submit_incident",
    "description": "Extraé información estructurada del reporte de incidente",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_time": {"type": "string", "description": "Hora del incidente si se menciona, sino null"},
            "affected_endpoint": {"type": "string", "description": "Endpoint o URL afectado, sino null"},
            "error_type": {"type": "string", "description": "Tipo de error (500, timeout, etc.)"},
            "failing_service": {"type": "string", "description": "Servicio que falla"},
            "user_impact_percent": {"type": "integer", "description": "Porcentaje de usuarios afectados, null si no se menciona"},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "is_ongoing": {"type": "boolean", "description": "Si el incidente sigue activo"},
            "suggested_action": {"type": "string", "description": "Acción inmediata sugerida"}
        },
        "required": ["error_type", "failing_service", "severity", "is_ongoing", "suggested_action"]
    }
}

def extract_incident(text: str) -> IncidentReport:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "submit_incident"},
        messages=[{"role": "user", "content": f"Extraé la información de este reporte:\n\n{text}"}]
    )
    raw = response.content[0].input
    return IncidentReport(**raw)  # Pydantic valida y castea tipos

incidents = [
    """El sistema empezó a dar timeout en el endpoint /api/checkout
    alrededor de las 14:30 UTC. Los logs muestran 503 errors del servicio de pagos.
    Está afectando al 30% de los usuarios. El equipo de infra está investigando.""",

    """URGENTE: La base de datos de producción no responde desde hace 5 minutos.
    Todos los usuarios están afectados (100%). Error: Connection refused en puerto 5432.
    Necesitamos hacer failover al replica inmediatamente.""",

    """Hay un par de usuarios reportando que el botón de logout no funciona en IE11.
    Parece ser un problema de JavaScript. Afecta quizás al 1-2% de usuarios (usuarios de IE)."""
]

for i, text in enumerate(incidents, 1):
    print(f"\n=== Incidente {i} ===")
    print(f"Texto: {text[:100].strip()}...\n")

    report = extract_incident(text)
    print(f"  service:        {report.failing_service}")
    print(f"  error_type:     {report.error_type}")
    print(f"  severity:       {report.severity}")
    print(f"  impact:         {report.user_impact_percent}% de usuarios")
    print(f"  ongoing:        {report.is_ongoing}")
    print(f"  time:           {report.incident_time}")
    print(f"  action:         {report.suggested_action}")

    # Usando tipos reales (no strings)
    if report.severity == "critical" and report.is_ongoing:
        print(f"  → 🚨 PAGINAR ON-CALL: {report.suggested_action}")
```

**Output esperado:**

```
=== Incidente 1 ===
Texto: El sistema empezó a dar timeout en el endpoint /api/checkout
    alrededor de las 14:30 UTC...

  service:        payment service
  error_type:     503 timeout
  severity:       high
  impact:         30% de usuarios
  ongoing:        True
  time:           14:30 UTC
  action:         Revisar logs del servicio de pagos y verificar conectividad con Stripe

=== Incidente 2 ===
Texto: URGENTE: La base de datos de producción no responde desde hace 5 minutos.
    Todos los usuarios están afectados (100%)...

  service:        PostgreSQL database
  error_type:     Connection refused
  severity:       critical
  impact:         100% de usuarios
  ongoing:        True
  time:           None
  action:         Hacer failover al replica inmediatamente
  → 🚨 PAGINAR ON-CALL: Hacer failover al replica inmediatamente

=== Incidente 3 ===
Texto: Hay un par de usuarios reportando que el botón de logout no funciona en IE11...

  service:        frontend JavaScript
  error_type:     JavaScript compatibility error
  severity:       low
  impact:         2% de usuarios
  ongoing:        True
  time:           None
  action:         Agregar polyfill o fix de compatibilidad para IE11, baja prioridad
```

**Qué muestra:**
- El incidente 2 es `critical` + `is_ongoing: True` → dispara el pager automáticamente
- `user_impact_percent` es un `int` (no un string "30%") — el tipado de Pydantic convierte
- `incident_time` es `None` cuando no se menciona — el schema lo maneja correctamente
- El código puede hacer `if report.severity == "critical"` sin parsear strings

---

## Comparación: texto libre vs structured output

```
Sin structured output:
──────────────────────
response = claude.ask("Analizá este issue: " + text)
# response.text = "Este issue parece crítico debido a que el checkout está caído..."
# Para obtener severity: ¿regex? ¿otro LLM? ¿parseo manual?
# Para saber si page_on_call(): imposible de forma confiable

Con structured output (este módulo):
──────────────────────────────────────
analysis = analyze_issue(text)
# analysis["severity"] = "critical"   ← siempre un string del enum
# analysis["requires_immediate_action"] = True  ← siempre bool
if analysis["severity"] == "critical":
    page_on_call()  # funciona de forma 100% confiable
```

---

Ver el [README principal](./README.md) para cuándo usar structured outputs y cómo manejar errores de schema.
