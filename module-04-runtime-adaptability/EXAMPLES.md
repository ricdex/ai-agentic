# Módulo 4 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Stage-aware agent: mismo agente, comportamiento diferente

**Archivo:** `examples/stage_aware.py`

El mismo agente recibe distintos contextos de runtime y cambia su nivel de conservadurismo. El ejemplo muestra el contraste entre modo `dev` y modo `production`.

```python
import anthropic
from dataclasses import dataclass

client = anthropic.Anthropic()

@dataclass
class RuntimeContext:
    stage: str               # "dev" | "staging" | "production"
    branch: str
    test_failures: int
    files_touched: list[str]
    is_critical_path: bool
    has_schema_changes: bool
    budget_tokens_used: int
    budget_tokens_max: int = 50_000

def should_escalate(ctx: RuntimeContext) -> tuple[bool, str]:
    if ctx.stage == "production" and ctx.is_critical_path:
        return True, "Archivo crítico en producción — requiere revisión humana"
    if ctx.test_failures >= 3:
        return True, f"{ctx.test_failures} intentos fallidos — escalar para debugging manual"
    if ctx.has_schema_changes:
        return True, "Cambio de schema de DB — requiere revisión humana"
    if ctx.budget_tokens_used >= ctx.budget_tokens_max * 0.9:
        return True, "Presupuesto de tokens casi agotado (90%+)"
    return False, ""

def get_model(ctx: RuntimeContext) -> str:
    if ctx.is_critical_path or ctx.stage == "production":
        return "claude-opus-4-8"
    if ctx.test_failures > 0:
        return "claude-sonnet-4-6"
    return "claude-haiku-4-5-20251001"

def get_behavior_instructions(ctx: RuntimeContext) -> str:
    if ctx.stage == "production":
        return (
            "⚠ Estás en PRODUCCIÓN. Modo ultra-conservador activado.\n"
            "- Hacé el cambio mínimo posible\n"
            "- Si tenés duda entre dos enfoques, elegí el más conservador\n"
            "- Si el cambio toca más de 2 archivos, escalá al humano\n"
            "- Documentá cada cambio con comentario inline"
        )
    if ctx.test_failures > 1:
        return (
            f"⚠ Ya fallaste {ctx.test_failures} veces. Cambiá completamente el approach.\n"
            "- No reutilices la lógica de los intentos anteriores\n"
            "- Analizá el error desde cero, asumí que tu hipótesis inicial era incorrecta\n"
            "- Si el bug no es obvio, instrumentá con logs antes de modificar código"
        )
    if ctx.stage == "dev":
        return "Modo desarrollo. Podés iterar libremente. Prioriza velocidad sobre cautela."
    return "Modo staging. Balance entre velocidad y seguridad."

def run_stage_aware_agent(task: str, ctx: RuntimeContext):
    escalate, reason = should_escalate(ctx)
    model = get_model(ctx)
    behavior = get_behavior_instructions(ctx)

    print(f"\n{'='*50}")
    print(f"Stage: {ctx.stage} | Branch: {ctx.branch}")
    print(f"Archivos: {ctx.files_touched} | Crítico: {ctx.is_critical_path}")
    print(f"Fallos previos: {ctx.test_failures} | Schema changes: {ctx.has_schema_changes}")
    print(f"{'='*50}")

    if escalate:
        print(f"\n🚨 ESCALANDO AL HUMANO: {reason}")
        print(f"Tarea pendiente: {task}")
        return

    print(f"\nModelo seleccionado: {model}")
    print(f"Instrucciones de comportamiento:\n{behavior}\n")

    response = client.messages.create(
        model=model,
        max_tokens=500,
        system=f"{behavior}\n\nResponde qué harías para resolver la tarea. Sé específico sobre tu approach.",
        messages=[{"role": "user", "content": task}]
    )
    print(f"Respuesta del agente:\n{response.content[0].text}")

# Caso 1: branch de dev, cambio no crítico
run_stage_aware_agent(
    task="Agregar validación de email en el registro de usuario",
    ctx=RuntimeContext(
        stage="dev", branch="feature/email-validation",
        test_failures=0, files_touched=["src/users.py"],
        is_critical_path=False, has_schema_changes=False,
        budget_tokens_used=1000
    )
)

# Caso 2: producción, archivo crítico
run_stage_aware_agent(
    task="Fix urgente: login falla para usuarios con caracteres especiales en el email",
    ctx=RuntimeContext(
        stage="production", branch="hotfix/login-special-chars",
        test_failures=0, files_touched=["src/auth.py"],
        is_critical_path=True, has_schema_changes=False,
        budget_tokens_used=5000
    )
)

# Caso 3: dev, pero ya falló 3 veces
run_stage_aware_agent(
    task="El test test_calculate_compound_interest sigue fallando",
    ctx=RuntimeContext(
        stage="dev", branch="feature/interest-calc",
        test_failures=3, files_touched=["src/finance.py"],
        is_critical_path=False, has_schema_changes=False,
        budget_tokens_used=12000
    )
)

# Caso 4: staging, cambio de schema
run_stage_aware_agent(
    task="Agregar columna 'last_login' a la tabla users",
    ctx=RuntimeContext(
        stage="staging", branch="feature/track-logins",
        test_failures=0, files_touched=["migrations/004_add_last_login.py"],
        is_critical_path=False, has_schema_changes=True,
        budget_tokens_used=2000
    )
)
```

**Output esperado:**

```
==================================================
Stage: dev | Branch: feature/email-validation
Archivos: ['src/users.py'] | Crítico: False
Fallos previos: 0 | Schema changes: False
==================================================

Modelo seleccionado: claude-haiku-4-5-20251001
Instrucciones de comportamiento:
Modo desarrollo. Podés iterar libremente. Prioriza velocidad sobre cautela.

Respuesta del agente:
Agregaría validación de email en `src/users.py` usando regex estándar o la librería `email-validator`.
Modificaría el método `create_user()` para validar antes de guardar en DB.
Añadiría un test para emails inválidos y un test para el formato correcto.

==================================================
Stage: production | Branch: hotfix/login-special-chars
Archivos: ['src/auth.py'] | Crítico: True
Fallos previos: 0 | Schema changes: False
==================================================

🚨 ESCALANDO AL HUMANO: Archivo crítico en producción — requiere revisión humana
Tarea pendiente: Fix urgente: login falla para usuarios con caracteres especiales en el email

==================================================
Stage: dev | Branch: feature/interest-calc
Archivos: ['src/finance.py'] | Crítico: False
Fallos previos: 3 | Schema changes: False
==================================================

Modelo seleccionado: claude-sonnet-4-6
Instrucciones de comportamiento:
⚠ Ya fallaste 3 veces. Cambiá completamente el approach.
- No reutilices la lógica de los intentos anteriores
- Analizá el error desde cero, asumí que tu hipótesis inicial era incorrecta
- Si el bug no es obvio, instrumentá con logs antes de modificar código

Respuesta del agente:
Dado que fallé 3 veces, no voy a asumir que el bug está en la fórmula de interés compuesto.
Primero voy a agregar logs para ver los valores exactos que entran y salen de cada cálculo.
Después compararé contra el resultado esperado del test para identificar exactamente dónde
diverge. Solo entonces modificaré la implementación.

==================================================
Stage: staging | Branch: feature/track-logins
Archivos: ['migrations/004_add_last_login.py'] | Crítico: False
Fallos previos: 0 | Schema changes: True
==================================================

🚨 ESCALANDO AL HUMANO: Cambio de schema de DB — requiere revisión humana
Tarea pendiente: Agregar columna 'last_login' a la tabla users
```

**Qué muestra:**
- Caso 1 (dev): usa el modelo más barato (Haiku), comportamiento libre
- Caso 2 (prod + crítico): escala inmediatamente, sin intentar el cambio
- Caso 3 (3 fallos): cambia a Sonnet y cambia el approach completamente
- Caso 4 (schema): siempre escala, sin importar el stage

---

## Ejemplo 2 — Extended thinking para bugs complejos

**Archivo:** `examples/extended_thinking.py`

Cuando el agente falla 2+ veces, activa extended thinking para razonar en profundidad antes de actuar.

```python
import anthropic

client = anthropic.Anthropic()

BUG_REPORT = """
Bug difícil: race condition en el sistema de inventario.

El test test_concurrent_checkout falla ~30% de las veces:
  AssertionError: Expected stock=0, got stock=1

El código usa Redis para el conteo de stock y tiene locking.
Ya probamos 2 fixes que no funcionaron:
  - Fix 1: Aumentar timeout del lock → sigue fallando
  - Fix 2: Usar WATCH/MULTI/EXEC en Redis → sigue fallando

Código relevante:
```python
def checkout(product_id: str, quantity: int) -> bool:
    lock_key = f"lock:{product_id}"
    with redis.lock(lock_key, timeout=5):
        stock = int(redis.get(f"stock:{product_id}") or 0)
        if stock < quantity:
            return False
        redis.decrby(f"stock:{product_id}", quantity)
        return True
```

Test que falla:
```python
def test_concurrent_checkout():
    redis.set("stock:product-1", 1)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(checkout, "product-1", 1) for _ in range(5)]
        results = [f.result() for f in futures]
    assert results.count(True) == 1  # solo uno debe poder comprar
    assert int(redis.get("stock:product-1")) == 0
```
"""

print("Activando extended thinking para bug complejo...\n")

response = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=8000,
    thinking={
        "type": "enabled",
        "budget_tokens": 5000
    },
    messages=[{
        "role": "user",
        "content": f"Analizá en profundidad este bug. Los fixes anteriores no funcionaron:\n\n{BUG_REPORT}"
    }]
)

for block in response.content:
    if block.type == "thinking":
        lines = block.thinking.split('\n')
        print(f"[Razonamiento interno — {len(lines)} líneas]")
        print(f"Primeras 5 líneas del thinking:")
        for line in lines[:5]:
            print(f"  {line}")
        print("  ...")
        print()
    elif block.type == "text":
        print(f"[Diagnóstico final]\n{block.text}")

print(f"\nTokens usados: {response.usage.input_tokens} input, {response.usage.output_tokens} output")
```

**Output esperado:**

```
Activando extended thinking para bug complejo...

[Razonamiento interno — 47 líneas]
Primeras 5 líneas del thinking:
  Voy a analizar la race condition en el sistema de inventario...
  El lock de Redis debería prevenir acceso concurrente, pero el bug persiste.
  Los fixes anteriores sugieren que el problema no está en el lock en sí...
  Pensando en el ciclo de vida del lock en Redis...
  La clave está en cómo Redis maneja las conexiones concurrentes desde Python threads...
  ...

[Diagnóstico final]
**Causa raíz identificada:** El problema no está en el lock de Redis sino en el cliente de Redis.

`redis-py` por defecto usa un `ConnectionPool` compartido entre threads. Cuando múltiples
threads intentan adquirir el lock simultáneamente, pueden obtener la misma conexión del pool,
lo que hace que el contexto del lock no esté correctamente aislado por thread.

**Por qué los fixes anteriores no funcionaron:**
- Fix 1 (timeout): el problema no es de timing sino de conexiones compartidas
- Fix 2 (WATCH/MULTI/EXEC): correcto en principio, pero el pool sigue compartiendo conexiones

**Fix real:**
```python
# Opción A: una conexión por thread
from threading import local
_thread_local = local()

def get_redis():
    if not hasattr(_thread_local, 'client'):
        _thread_local.client = redis.Redis(...)
    return _thread_local.client

# Opción B (más simple): usar Lua script en Redis (atómico por diseño)
CHECKOUT_SCRIPT = """
local stock = tonumber(redis.call('GET', KEYS[1]) or 0)
if stock < tonumber(ARGV[1]) then return 0 end
redis.call('DECRBY', KEYS[1], ARGV[1])
return 1
"""
result = redis.eval(CHECKOUT_SCRIPT, 1, f"stock:{product_id}", quantity)
```

Recomiendo Opción B: el Lua script es atómico en Redis, elimina la necesidad del lock
y es más eficiente.

Tokens usados: 2847 input, 612 output
```

**Qué muestra:**
- El thinking interno es visible (47 líneas de razonamiento)
- El diagnóstico llega a la causa raíz real (pool de conexiones compartido)
- Explica por qué los dos fixes anteriores no funcionaron
- Propone dos soluciones concretas con código
- El extended thinking cuesta más tokens pero resuelve el bug en un solo intento vs seguir fallando

---

## Ejemplo 3 — Confidence threshold: el agente sabe cuándo no sabe

**Archivo:** `examples/confidence_threshold.py`

El agente reporta su nivel de confianza antes de cada cambio importante. Si la confianza es baja en contextos críticos, escala automáticamente.

```python
import anthropic
import json

client = anthropic.Anthropic()

CONFIDENCE_TOOL = {
    "name": "report_confidence",
    "description": "Reportá tu confianza antes de hacer un cambio. Si es < 0.7 en contexto crítico, el sistema escala.",
    "input_schema": {
        "type": "object",
        "properties": {
            "confidence": {"type": "number", "description": "0.0 a 1.0"},
            "reason": {"type": "string"},
            "what_would_increase_confidence": {"type": "string"},
            "proposed_action": {"type": "string"}
        },
        "required": ["confidence", "reason", "proposed_action"]
    }
}

APPLY_FIX_TOOL = {
    "name": "apply_fix",
    "description": "Aplica el fix al archivo. Solo llamar después de reportar confianza.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file": {"type": "string"},
            "change_description": {"type": "string"}
        },
        "required": ["file", "change_description"]
    }
}

def process_agent_action(block, is_critical: bool):
    if block.name == "report_confidence":
        conf = block.input["confidence"]
        reason = block.input["reason"]
        action = block.input["proposed_action"]

        print(f"\n  📊 Confianza reportada: {conf:.0%}")
        print(f"  Razón: {reason}")
        print(f"  Acción propuesta: {action}")

        if is_critical and conf < 0.7:
            print(f"  🚨 Confianza baja en contexto crítico → ESCALANDO")
            print(f"  Para mejorar la confianza: {block.input.get('what_would_increase_confidence', 'N/A')}")
            return "escalated"
        elif conf < 0.5:
            print(f"  ⚠ Confianza muy baja → solicitando más contexto")
            return "needs_context"
        else:
            print(f"  ✓ Confianza aceptable → procediendo")
            return "proceed"

    elif block.name == "apply_fix":
        print(f"\n  ✓ Fix aplicado en {block.input['file']}")
        print(f"  Cambio: {block.input['change_description']}")
        return "done"

def run_with_confidence(task: str, code_context: str, is_critical: bool = False):
    context_label = "CRÍTICO" if is_critical else "normal"
    print(f"\n{'='*50}")
    print(f"Tarea [{context_label}]: {task[:60]}...")
    print(f"{'='*50}")

    messages = [{"role": "user", "content": f"Contexto de código:\n{code_context}\n\nTarea: {task}"}]

    for _ in range(5):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=f"""Antes de modificar cualquier código, usá report_confidence para indicar tu nivel de seguridad.
Si {'es un contexto crítico y ' if is_critical else ''}tu confianza es alta (>0.7), procedé con apply_fix.
Si no, explicá qué información adicional necesitás.""",
            tools=[CONFIDENCE_TOOL, APPLY_FIX_TOOL],
            messages=messages
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            outcome = None
            for block in response.content:
                if block.type == "tool_use":
                    outcome = process_agent_action(block, is_critical)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"status": outcome or "ok"})
                    })

            if outcome in ("escalated", "done"):
                break
            messages.append({"role": "user", "content": results})

# Caso 1: contexto claro → confianza alta → procede
run_with_confidence(
    task="Cambiar el mensaje de error de 'User not found' a 'Invalid credentials' para no revelar si el usuario existe",
    code_context="def login(email, password):\n    user = db.find_by_email(email)\n    if not user:\n        raise AuthError('User not found')\n    ...",
    is_critical=False
)

# Caso 2: contexto ambiguo + crítico → confianza baja → escala
run_with_confidence(
    task="Optimizar la query de pagos que está causando timeouts",
    code_context="# payments.py tiene 800 líneas. Solo tenés el stack trace:\nTimeoutError en payments.py:342",
    is_critical=True
)
```

**Output esperado:**

```
==================================================
Tarea [normal]: Cambiar el mensaje de error de 'User not found' a...
==================================================

  📊 Confianza reportada: 95%
  Razón: El cambio es minimal y claro: una línea de string. No hay ambigüedad sobre qué modificar.
  Acción propuesta: Cambiar 'User not found' por 'Invalid credentials' en línea 3 de login()
  ✓ Confianza aceptable → procediendo

  ✓ Fix aplicado en auth.py
  Cambio: Mensaje de error cambiado a 'Invalid credentials' para evitar user enumeration

==================================================
Tarea [CRÍTICO]: Optimizar la query de pagos que está causando timeouts
==================================================

  📊 Confianza reportada: 25%
  Razón: Solo tengo el stack trace con el número de línea. No vi el código de payments.py:342,
         no sé qué query está corriendo, no tengo EXPLAIN del query plan, ni los índices existentes.
  Acción propuesta: Leer payments.py:342 y el schema de la tabla payments antes de proponer cambios
  Para mejorar la confianza: Ver el código completo de la función en línea 342, el schema de la
                              tabla payments, y el output de EXPLAIN ANALYZE de la query lenta
  🚨 Confianza baja en contexto crítico → ESCALANDO
  Para mejorar la confianza: Ver el código completo de la función en línea 342...
```

**Qué muestra:**
- Caso 1: el agente tiene contexto suficiente → confianza 95% → procede directamente
- Caso 2: el agente sabe que no sabe → confianza 25% → escala y explica exactamente qué información falta
- El escalamiento no es un fallo — es el comportamiento correcto cuando el riesgo supera el conocimiento disponible

---

Ver el [README principal](./README.md) para las variables de runtime y los criterios de decisión dinámicos.
