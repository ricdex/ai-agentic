# Módulo 7 — Structured Outputs y Confiabilidad

> "Un agente que retorna texto libre es un agente que no podés usar en producción. Los sistemas reales necesitan datos, no prosa."

---

## 7.1 El problema del texto libre

```python
# Lo que querés hacer
response = agent.analyze_issue(issue_text)
if response.severity == "critical":
    page_on_call()

# Lo que tenés sin structured outputs
response = claude.ask(f"Analizá este issue: {issue_text}")
# response es un string: "Este issue parece crítico debido a..."
# ¿Cómo extraés severity? ¿Con regex? ¿Con otro LLM? ¿Esperando?
```

Los modelos de lenguaje producen texto. Tu código necesita datos. La brecha entre ambos es un punto de falla constante en sistemas AI.

---

## 7.2 Tool use como schema enforcement

El mecanismo más robusto con Claude: definir una herramienta cuyo `input_schema` es exactamente la estructura que querés, y forzar al modelo a llamarla.

```python
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
            }
        },
        "required": ["severity", "category", "affected_components", "requires_immediate_action"]
    }
}

# Forzar que use exactamente esta herramienta
response = client.messages.create(
    model="claude-sonnet-4-6",
    tools=[ANALYZE_TOOL],
    tool_choice={"type": "tool", "name": "submit_analysis"},  # ← clave
    messages=[{"role": "user", "content": issue_text}]
)

# El output SIEMPRE es el schema que definiste
analysis = response.content[0].input
print(analysis["severity"])  # "critical" — siempre un string del enum
```

**Por qué `tool_choice` con nombre específico:** sin esto, el modelo puede elegir no llamar la herramienta y responder con texto. Forzarlo garantiza el schema.

---

## 7.3 Pydantic para validación y tipado

Combinar tool use con Pydantic da type safety completo:

```python
from pydantic import BaseModel, validator
from typing import Literal

class IssueAnalysis(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    category: Literal["bug", "performance", "security", "feature"]
    affected_components: list[str]
    estimated_hours: float | None = None
    requires_immediate_action: bool

    @validator("affected_components")
    def components_not_empty(cls, v):
        if not v:
            raise ValueError("Debe haber al menos un componente afectado")
        return v

# Parsear y validar el output del modelo
raw = response.content[0].input
analysis = IssueAnalysis(**raw)  # Pydantic valida y convierte tipos

# Ahora tenés tipos reales
if analysis.severity == "critical" and analysis.requires_immediate_action:
    page_on_call(analysis.affected_components)
```

---

## 7.4 Extracción de información de texto no estructurado

El caso más común en sistemas reales: extraer datos estructurados de texto libre (logs, emails, issues, documentos).

```
Texto libre:
"El sistema empezó a dar timeout en el endpoint /api/checkout
 alrededor de las 14:30 UTC. Los logs muestran 503 errors
 del servicio de pagos. Está afectando al 30% de los usuarios."

↓ Extracción estructurada

{
  "incident_time": "14:30 UTC",
  "affected_endpoint": "/api/checkout",
  "error_type": "503",
  "failing_service": "payment_service",
  "user_impact_percent": 30
}
```

---

## 7.5 Manejo de errores de schema

A veces el modelo produce output que no matchea el schema exacto. Estrategia robusta:

```python
def extract_with_retry(text: str, schema_class, max_retries: int = 2):
    for attempt in range(max_retries + 1):
        raw = call_claude_with_tool(text)
        try:
            return schema_class(**raw)
        except Exception as e:
            if attempt == max_retries:
                raise
            # Darle feedback al modelo sobre el error
            text = f"{text}\n\nTu respuesta anterior falló validación: {e}. Corregila."
```

---

## 7.6 Cuándo NO usar structured outputs

No todo necesita ser estructurado:
- Respuestas de chat — texto libre está bien
- Explicaciones largas — mejor texto
- Análisis abiertos — texto con secciones

**Sí usá structured outputs cuando:**
- El output alimenta código (if/else, DB, API)
- Necesitás extraer campos específicos de texto
- El output es procesado por otro sistema

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Tool use como schema](./EXAMPLES.md#ejemplo-1--tool-use-como-schema-enforcement) | 4 issues → severity/category/components siempre en el tipo correcto; checkout caído dispara alerta |
| [02 — Extracción con Pydantic](./EXAMPLES.md#ejemplo-2--extracción-con-pydantic-validación-y-tipos) | Texto libre de incidentes → struct tipado; DB caída dispara pager automáticamente |

---

## Ejercicio

Creá un agente de triage de issues que:
1. Recibe el título y descripción de un issue de GitHub
2. Extrae: severity, category, affected_components, estimated_effort (XS/S/M/L/XL), needs_clarification (bool)
3. Si needs_clarification es true, genera 2-3 preguntas específicas para el autor
4. Si severity es critical, genera un resumen de una línea para el canal de alertas

Todo el pipeline debe ser tipado — sin parseo manual de strings.

---

Siguiente: [Módulo 8 → MCP (Model Context Protocol)](../module-08-mcp/README.md)
