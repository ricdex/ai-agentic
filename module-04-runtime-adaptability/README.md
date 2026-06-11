# Módulo 4 — Runtime Adaptability

> "Un agente de producción no es uno que siempre hace lo mismo. Es uno que sabe cuándo ser agresivo, cuándo ser conservador, y cuándo llamar a un humano."

---

## 4.1 El problema del agente estático

Un agente que siempre opera igual tiene un problema fundamental: el costo de error varía enormemente según el contexto.

**Mismo error, diferente impacto:**

| Contexto | Agente modifica auth.py sin tests | Consecuencia |
|---|---|---|
| Branch local, dev | Falla el build local | Bajo impacto |
| PR en staging | Falla el pipeline | Medio impacto |
| Hotfix en producción | Caída del servicio | Crítico |

El agente necesita **saber en qué contexto está** y **ajustar su comportamiento**.

---

## 4.2 Variables de runtime que importan

```python
@dataclass
class RuntimeContext:
    # Ambiente
    stage: str              # "dev" | "staging" | "production"
    branch: str             # "feature/xyz" | "main" | "hotfix/..."

    # Estado actual
    test_failures: int      # cuántos ciclos fallaron ya
    budget_tokens_used: int # tokens gastados hasta ahora
    budget_tokens_max: int  # presupuesto total
    elapsed_seconds: float  # tiempo transcurrido

    # Riesgo del cambio
    files_touched: list[str]      # qué archivos se modificaron
    is_critical_path: bool        # ¿toca auth, payments, data migration?
    has_schema_changes: bool      # ¿modifica la DB?

    # Historial
    past_failures_this_week: int  # tendencia de fallas recientes
```

---

## 4.3 Decision criteria dinámicos

Con este contexto, el agente puede tomar decisiones distintas:

```python
def should_escalate_to_human(ctx: RuntimeContext) -> tuple[bool, str]:
    # Regla 1: en producción, cualquier toque a archivos críticos requiere humano
    if ctx.stage == "production" and ctx.is_critical_path:
        return True, "Archivo crítico en producción — requiere revisión humana"

    # Regla 2: si ya falló 3 veces, escalar
    if ctx.test_failures >= 3:
        return True, f"3 intentos fallidos — escalar para debugging manual"

    # Regla 3: si hay cambios de schema, siempre humano
    if ctx.has_schema_changes:
        return True, "Cambio de schema de DB — requiere revisión humana"

    # Regla 4: si se acabó el presupuesto
    if ctx.budget_tokens_used >= ctx.budget_tokens_max * 0.9:
        return True, "Presupuesto de tokens casi agotado"

    return False, ""

def get_model_for_context(ctx: RuntimeContext) -> str:
    # Problema complejo o contexto crítico → modelo más capaz
    if ctx.is_critical_path or ctx.stage == "production":
        return "claude-opus-4-7"

    # Iteración después de fallo → más razonamiento
    if ctx.test_failures > 0:
        return "claude-sonnet-4-6"

    # Caso estándar
    return "claude-sonnet-4-6"

def get_agent_temperature_guidance(ctx: RuntimeContext) -> str:
    """Instrucciones que hacen al agente más o menos conservador."""
    if ctx.stage == "production":
        return (
            "Estás en PRODUCCIÓN. Sé extremadamente conservador. "
            "Hacé el cambio mínimo necesario. "
            "Si tenés duda, escalá al humano en lugar de adivinar."
        )
    elif ctx.test_failures > 1:
        return (
            f"Ya fallaste {ctx.test_failures} veces. "
            "Cambiá completamente tu approach. "
            "Analizá el error desde cero antes de escribir código."
        )
    else:
        return "Procedé normalmente. Iterá si es necesario."
```

---

## 4.4 Extended Thinking para decisiones complejas

Cuando el agente necesita razonar profundamente antes de actuar (diagnóstico de un bug difícil, planificación de un refactor grande), Claude tiene **extended thinking**.

```python
response = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=16000,
    thinking={
        "type": "enabled",
        "budget_tokens": 10000  # tokens para razonamiento interno
    },
    messages=[{
        "role": "user",
        "content": "Este bug lleva 3 iteraciones sin resolver: [contexto complejo]"
    }]
)

# El agente "piensa" antes de responder
# El thinking es visible en response.content si querés auditarlo
for block in response.content:
    if block.type == "thinking":
        print(f"[Razonamiento interno]\n{block.thinking[:500]}...")
    elif block.type == "text":
        print(f"[Respuesta]\n{block.text}")
```

**Cuándo usar extended thinking:**
- Bugs complejos que no cedieron en 2+ iteraciones
- Planificación de refactors con muchas dependencias
- Análisis de seguridad profundo

**Referencia:** [Extended Thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)

---

## 4.5 Confidence thresholds

Un agente bien diseñado sabe cuándo no está seguro:

```python
CONFIDENCE_CHECK_TOOL = {
    "name": "report_confidence",
    "description": (
        "Reportá tu nivel de confianza antes de hacer un cambio importante. "
        "Si tu confianza es baja, el sistema escalará a un humano."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "confidence": {
                "type": "number",
                "description": "Confianza de 0.0 a 1.0"
            },
            "reason": {
                "type": "string",
                "description": "Por qué tu confianza es ese nivel"
            },
            "what_would_increase_confidence": {
                "type": "string",
                "description": "Qué información adicional necesitarías para estar más seguro"
            }
        },
        "required": ["confidence", "reason"]
    }
}
```

Si el agente reporta confianza < 0.7 en un contexto crítico, el sistema escala automáticamente.

---

## Ejemplos de código

- [`stage_aware.py`](./examples/stage_aware.py) — Agente completo con decisiones runtime según stage y riesgo

---

## Ejercicio

Tomá el `issue_solver.py` del módulo anterior y agregale:

1. **Detección de archivos críticos:** si el issue toca `auth.py`, `payments.py`, o `migrations/`, activar modo conservador
2. **Budget de tokens:** si se gastaron más de X tokens, el agente reporta lo que hizo y espera confirmación
3. **Escalamiento automático:** si falló 3 veces, generar un reporte y "enviar" al humano (imprimir el resumen)

Bonus: agregá un flag `--aggressive` que desactiva las salvaguardas (para branch de dev).

---

Siguiente: [Módulo 5 → Producción y Observabilidad](../module-05-production/README.md)
