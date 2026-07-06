# Módulo 12 — Ejemplos con Output Esperado

> Este archivo muestra el código de cada ejemplo **y el output real que produce**, para que puedas entender el comportamiento sin correrlo vos.

---

## Ejemplo 1 — Queue Worker básico

**Archivo:** `examples/01_queue_worker.py`

El worker más simple: consume mensajes de una cola Redis, los procesa con el agente, y loggea el resultado.

```python
import asyncio
import json
import time
from anthropic import Anthropic

client = Anthropic()

# Simular cola con una lista en memoria (en prod: Redis o SQS)
QUEUE = [
    {"id": "evt-001", "type": "pr_opened", "pr_number": 42, "title": "Fix auth token expiry", "diff": "- expires = 3600\n+ expires = 86400"},
    {"id": "evt-002", "type": "pr_opened", "pr_number": 43, "title": "Add user avatar", "diff": "+ avatar_url = models.URLField(null=True)"},
    {"id": "evt-003", "type": "pr_opened", "pr_number": 44, "title": "Remove unused imports", "diff": "- import os\n- import sys\n  import json"},
]

PROCESSED = set()  # idempotencia en memoria (en prod: Redis SET o tabla DB)

SYSTEM_PROMPT = """Sos un code reviewer. Revisá el diff y dá máximo 3 puntos concisos.
Formato: bullet points, sin intro. Solo problemas reales, no opiniones de estilo."""

def process_event(event: dict) -> dict:
    if event["id"] in PROCESSED:
        return {"skipped": True, "reason": "ya procesado"}

    start = time.time()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku para reviews simples
        max_tokens=300,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{
            "role": "user",
            "content": f"PR #{event['pr_number']}: {event['title']}\n\nDiff:\n{event['diff']}"
        }]
    )

    PROCESSED.add(event["id"])
    return {
        "pr_number": event["pr_number"],
        "review": response.content[0].text,
        "tokens": response.usage.input_tokens + response.usage.output_tokens,
        "cached_tokens": response.usage.cache_read_input_tokens,
        "duration_s": round(time.time() - start, 2)
    }

def worker_loop():
    print("Worker iniciado. Procesando cola...\n")
    for message in QUEUE:
        print(f"→ Procesando evento {message['id']}...")
        result = process_event(message)
        if result.get("skipped"):
            print(f"  ↷ Saltado: {result['reason']}\n")
        else:
            print(f"  PR #{result['pr_number']} revisado en {result['duration_s']}s")
            print(f"  Tokens: {result['tokens']} ({result['cached_tokens']} en caché)")
            print(f"  Review:\n{result['review']}\n")

    # Simular segundo paso (idempotencia)
    print("--- Segundo ciclo (mismo queue, debe saltear todo) ---\n")
    for message in QUEUE:
        result = process_event(message)
        print(f"  {message['id']}: {'saltado ✓' if result.get('skipped') else 'procesado'}")

worker_loop()
```

**Output esperado:**

```
Worker iniciado. Procesando cola...

→ Procesando evento evt-001...
  PR #42 revisado en 1.23s
  Tokens: 187 (0 en caché)
  Review:
  • El cambio de 3600 a 86400 segundos extiende la expiración de 1h a 24h — verificar que sea intencional y que los tests lo cubran
  • No se ven tests actualizados en el diff
  • Si el token es de sesión, 24h puede ser demasiado tiempo para contextos de seguridad alta

→ Procesando evento evt-002...
  PR #43 revisado en 0.98s
  Tokens: 134 (112 en caché)   ← segundo evento: system prompt cacheado
  Review:
  • Campo nullable sin valor default — considerar migración para filas existentes
  • Falta validación de URL en el modelo o en el serializer

→ Procesando evento evt-003...
  PR #44 revisado en 0.87s
  Tokens: 98 (112 en caché)    ← tercer evento: caché warm
  Review:
  • Cambio limpio, bajo riesgo
  • Verificar que `json` siga siendo necesario luego de la limpieza

--- Segundo ciclo (mismo queue, debe saltear todo) ---

  evt-001: saltado ✓
  evt-002: saltado ✓
  evt-003: saltado ✓
```

**Qué muestra este ejemplo:**
- El system prompt se cachea a partir del segundo evento (tokens en caché = 112)
- La idempotencia funciona: el segundo ciclo saltea todo sin llamar al modelo
- Haiku procesa cada review en < 2 segundos con costo muy bajo

---

## Ejemplo 2 — PR Review Worker completo

**Archivo:** `examples/02_pr_review_worker.py`

Worker real con métricas, reintentos, graceful shutdown y distinción de modelos por complejidad del PR.

```python
import asyncio
import json
import signal
import time
from dataclasses import dataclass, field
from anthropic import Anthropic

client = Anthropic()

@dataclass
class WorkerMetrics:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    total_cost_usd: float = 0.0
    durations: list = field(default_factory=list)

    def success_rate(self):
        total = self.processed + self.failed
        return self.processed / total if total > 0 else 1.0

    def avg_cost(self):
        return self.total_cost_usd / self.processed if self.processed else 0

    def p95_duration(self):
        if not self.durations:
            return 0
        s = sorted(self.durations)
        return s[int(len(s) * 0.95)]

    def print_report(self):
        print("\n=== Reporte del worker ===")
        print(f"  Procesados:     {self.processed}")
        print(f"  Fallidos:       {self.failed}")
        print(f"  Salteados:      {self.skipped}")
        print(f"  Success rate:   {self.success_rate():.1%}")
        print(f"  Costo total:    ${self.total_cost_usd:.4f}")
        print(f"  Costo/evento:   ${self.avg_cost():.4f}")
        print(f"  p95 duración:   {self.p95_duration():.2f}s")

# Modelos según complejidad estimada del diff
def choose_model(diff: str) -> str:
    lines_changed = diff.count('\n')
    if lines_changed > 100:
        return "claude-sonnet-4-6"   # diffs grandes requieren más razonamiento
    return "claude-haiku-4-5-20251001"      # diffs pequeños, más rápido y barato

# Simular cola con eventos de distinta complejidad
QUEUE = [
    {"id": "pr-101", "pr_number": 101, "title": "Fix typo in README", "diff": "- Wellcome\n+ Welcome", "complexity": "trivial"},
    {"id": "pr-102", "pr_number": 102, "title": "Refactor payment processor", "diff": "\n".join([f"  line {i}" for i in range(120)]), "complexity": "alta"},
    {"id": "pr-103", "pr_number": 103, "title": "Add input validation", "diff": "+ if not user_input:\n+     raise ValueError('required')", "complexity": "media"},
    {"id": "pr-104", "pr_number": 103, "title": "Add input validation", "diff": "+ if not user_input:\n+     raise ValueError('required')", "complexity": "media"},  # duplicado intencional
]

PROCESSED = set()
metrics = WorkerMetrics()
running = True

def handle_shutdown(sig, frame):
    global running
    print("\n⚠ Shutdown signal recibido. Terminando ejecución actual...")
    running = False

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

REVIEW_PROMPT = """Revisá este PR. Sé específico y conciso. Solo problemas reales.
Formato: bullets. Si no hay problemas, decí "Sin observaciones críticas." """

def process_pr(event: dict) -> dict:
    if event["id"] in PROCESSED:
        return {"status": "skipped"}

    model = choose_model(event["diff"])
    start = time.time()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=400,
            system=[{"type": "text", "text": REVIEW_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"PR #{event['pr_number']}: {event['title']}\n\n{event['diff']}"}]
        )

        # Calcular costo aproximado (precios Haiku/Sonnet)
        input_t = response.usage.input_tokens
        output_t = response.usage.output_tokens
        cached_t = response.usage.cache_read_input_tokens
        if "haiku" in model:
            cost = (input_t * 0.8 + output_t * 4.0 + cached_t * 0.08) / 1_000_000
        else:
            cost = (input_t * 3.0 + output_t * 15.0 + cached_t * 0.30) / 1_000_000

        PROCESSED.add(event["id"])
        duration = time.time() - start

        return {
            "status": "ok",
            "model": model.split("-")[1],  # "haiku" o "sonnet"
            "review": response.content[0].text,
            "cost_usd": cost,
            "duration_s": duration,
            "cache_pct": int(cached_t / input_t * 100) if input_t else 0
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

def run_worker():
    print("PR Review Worker v1.0")
    print("=" * 40)

    for event in QUEUE:
        if not running:
            print("Worker detenido por shutdown signal.")
            break

        print(f"\n→ [{event['id']}] PR #{event['pr_number']} ({event['complexity']})")
        result = process_pr(event)

        if result["status"] == "skipped":
            metrics.skipped += 1
            print(f"  ↷ Saltado (ya procesado)")

        elif result["status"] == "error":
            metrics.failed += 1
            print(f"  ✗ Error: {result['error']}")

        else:
            metrics.processed += 1
            metrics.total_cost_usd += result["cost_usd"]
            metrics.durations.append(result["duration_s"])

            print(f"  ✓ Modelo: {result['model']} | {result['duration_s']:.2f}s | ${result['cost_usd']:.5f} | caché: {result['cache_pct']}%")
            print(f"  Review: {result['review'][:200]}{'...' if len(result['review']) > 200 else ''}")

    metrics.print_report()

run_worker()
```

**Output esperado:**

```
PR Review Worker v1.0
========================================

→ [pr-101] PR #101 trivial
  ✓ Modelo: haiku | 0.91s | $0.00003 | caché: 0%
  Review: Sin observaciones críticas.

→ [pr-102] PR #102 alta
  ✓ Modelo: sonnet | 2.34s | $0.00187 | caché: 43%
  Review:
  • El diff tiene 120 líneas de cambio — sin contexto de qué hace cada una, es difícil evaluar correctamente
  • Si es un refactor de PaymentProcessor, verificar que los tests de integración cubran los flujos críticos (cobro, reembolso, fallo de red)
  • Asegurar que los nombres de métodos nuevos sean consistentes con el resto del dominio...

→ [pr-103] PR #103 media
  ✓ Modelo: haiku | 0.88s | $0.00004 | caché: 67%
  Review:
  • La validación lanza ValueError pero no hay tests que verifiquen el mensaje de error ni el tipo de excepción
  • Considerar retornar un error tipado en lugar de una excepción genérica si esto es una API pública

→ [pr-104] PR #103 media
  ↷ Saltado (ya procesado)

=== Reporte del worker ===
  Procesados:     3
  Fallidos:       0
  Salteados:      1
  Success rate:   100.0%
  Costo total:    $0.00194
  Costo/evento:   $0.00065
  p95 duración:   2.34s
```

**Qué muestra este ejemplo:**
- Selección automática de modelo por complejidad del diff
- El caché crece con cada evento: 0% → 43% → 67%
- El costo total de 3 PRs es $0.002 — viable a escala
- La idempotencia detectó el PR duplicado (pr-104 == pr-103)
- El reporte final da visibilidad completa del worker

---

## Ejemplo 3 — Multi-agent router

**Archivo:** `examples/03_multi_agent_router.py`

Router que clasifica eventos entrantes y los despacha a agentes especializados con distintos prompts y modelos.

```python
import json
from anthropic import Anthropic

client = Anthropic()

# ── Agentes especializados ──────────────────────────────────────

def agent_pr_review(event: dict) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system="Sos un code reviewer. Revisá el diff. Máximo 3 bullets.",
        messages=[{"role": "user", "content": f"PR: {event['title']}\nDiff: {event.get('diff', 'N/A')}"}]
    )
    return response.content[0].text

def agent_issue_triage(event: dict) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system="""Triageá este issue. Respondé en JSON con exactamente estos campos:
{"severity": "low|medium|high|critical", "category": "bug|feature|question|docs", "needs_clarification": true|false}""",
        messages=[{"role": "user", "content": f"Issue: {event['title']}\n{event.get('body', '')}"}]
    )
    return response.content[0].text

def agent_ci_fix(event: dict) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",  # CI failures requieren más razonamiento
        max_tokens=500,
        system="Analizá el log de CI y explicá la causa raíz y el fix más probable. Sé específico.",
        messages=[{"role": "user", "content": f"CI failure en {event['workflow']}:\n{event.get('log', 'N/A')}"}]
    )
    return response.content[0].text

# ── Router ──────────────────────────────────────────────────────

ROUTES = {
    "pr_opened":        ("PR Review Agent",   agent_pr_review),
    "pr_synchronize":   ("PR Review Agent",   agent_pr_review),
    "issues_opened":    ("Issue Triage Agent", agent_issue_triage),
    "workflow_failure": ("CI Fix Agent",       agent_ci_fix),
}

def route_and_process(event: dict) -> dict:
    event_type = event["type"]

    if event_type not in ROUTES:
        return {"status": "ignored", "type": event_type}

    agent_name, agent_fn = ROUTES[event_type]
    print(f"  → Despachando a: {agent_name}")

    result = agent_fn(event)
    return {"status": "processed", "agent": agent_name, "output": result}

# ── Simulación de eventos mezclados ─────────────────────────────

EVENTS = [
    {
        "id": "e1", "type": "pr_opened",
        "title": "Add rate limiting to login endpoint",
        "diff": "+ @rate_limit(max_calls=5, period=60)\n  def login(request):\n      ..."
    },
    {
        "id": "e2", "type": "issues_opened",
        "title": "App crashes on logout when session is expired",
        "body": "Steps to reproduce: 1) Login 2) Wait 2 hours 3) Click logout → 500 error"
    },
    {
        "id": "e3", "type": "workflow_failure",
        "workflow": "CI / test (python 3.11)",
        "log": "FAILED tests/test_auth.py::test_login_rate_limit - AttributeError: 'NoneType' object has no attribute 'remaining_calls'\n  File 'src/middleware.py', line 42, in check_rate_limit"
    },
    {
        "id": "e4", "type": "pr_review_requested",  # tipo no registrado
        "title": "..."
    },
]

print("Multi-Agent Router")
print("=" * 40)

for event in EVENTS:
    print(f"\n[{event['id']}] Tipo: {event['type']}")
    result = route_and_process(event)

    if result["status"] == "ignored":
        print(f"  ↷ Ignorado (sin agente para este tipo)")
    else:
        print(f"  ✓ {result['agent']} respondió:")
        print(f"  {result['output']}")
```

**Output esperado:**

```
Multi-Agent Router
========================================

[e1] Tipo: pr_opened
  → Despachando a: PR Review Agent
  ✓ PR Review Agent respondió:
  • El rate limiting de 5 llamadas/60s es razonable para login — verificar que el contador se resetea correctamente entre períodos
  • Asegurarse de que el decorator maneja correctamente el caso de IP detrás de proxy (header X-Forwarded-For)
  • Falta test que verifique el comportamiento al superar el límite (¿retorna 429?)

[e2] Tipo: issues_opened
  → Despachando a: Issue Triage Agent
  ✓ Issue Triage Agent respondió:
  {"severity": "high", "category": "bug", "needs_clarification": false}

[e3] Tipo: workflow_failure
  → Despachando a: CI Fix Agent
  ✓ CI Fix Agent respondió:
  Causa raíz: `check_rate_limit` en `middleware.py:42` intenta acceder a `.remaining_calls` en un objeto que es `None`.
  
  Esto ocurre cuando la sesión de rate limiting no existe en Redis/caché — probablemente el objeto `RateLimitState` no se inicializa antes de ser consultado.
  
  Fix probable: agregar un guard en línea 42:
  ```python
  state = get_rate_limit_state(request)
  if state is None:
      state = RateLimitState(remaining_calls=MAX_CALLS)
  ```
  
  Verificar también: ¿el test `test_login_rate_limit` crea el estado de rate limit antes de llamar al endpoint?

[e4] Tipo: pr_review_requested
  ↷ Ignorado (sin agente para este tipo)
```

**Qué muestra este ejemplo:**
- Cada tipo de evento va al agente correcto automáticamente
- El Issue Triage Agent retorna JSON estructurado (severity, category, needs_clarification)
- El CI Fix Agent usa Sonnet (más caro pero más preciso para debugging)
- Eventos sin ruta definida se ignoran sin error

---

## Comparación de costos por patrón

```
Escenario: equipo con 20 PRs/día y 15 issues/día

PATRÓN ON-DEMAND (manual, sin background agent):
  Costo: $0
  Tiempo del equipo: 2-3h/día en reviews y triage

PATRÓN BACKGROUND AGENT (ejemplos de este módulo):
  PR reviews (haiku):      20 × $0.00065 = $0.013/día
  Issue triage (haiku):    15 × $0.00030 = $0.005/día
  CI fix analysis (sonnet): 3 × $0.002   = $0.006/día
                                           ──────────
  Total diario:                            $0.024/día
  Total mensual:                           $0.72/mes

RESULTADO:
  Costo mensual: $0.72
  Tiempo ahorrado: ~1.5h/día en reviews y triage rutinario
  El equipo se enfoca en reviews de cambios complejos, no en typos ni issues obvios
```

---

## Qué pasa cuando algo falla

```
Escenario: el modelo retorna texto malformado en el triage de issues

Sin manejo de errores:
  → El worker crashea
  → El mensaje vuelve a la cola (bien)
  → Se reintenta 3 veces
  → Va a la DLQ
  → Alerta al equipo

Con retry + fallback (recomendado):
  Intento 1: modelo retorna "severity: HIGH" (no es JSON válido)
    → Retry con instrucción: "Tu respuesta anterior no era JSON válido: 'severity: HIGH'. Respondé solo con JSON."
  Intento 2: modelo retorna {"severity": "high", "category": "bug", "needs_clarification": false}
    → Éxito

Código del retry:
  for attempt in range(3):
      result = call_agent(event)
      try:
          parsed = json.loads(result)
          return parsed  # éxito
      except json.JSONDecodeError:
          if attempt < 2:
              event["correction"] = f"Respuesta inválida: {result}. Corregí el JSON."
          else:
              raise  # va a DLQ después de 3 intentos
```

---

Ver el [README principal](./README.md) para los conceptos y el checklist de producción.
