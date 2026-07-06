# Módulo 12 — Agentes Persistentes y Background Workers

> "Un agente que sólo vive mientras vos lo mirás no es un agente — es un demo. Un agente real trabaja mientras dormís."

---

## 12.1 El problema que resuelven

La mayoría del trabajo agéntico del curso hasta acá es **on-demand**: vos lanzás el agente, esperás el resultado, terminás. Eso funciona para muchos casos. Pero hay una clase de problemas que requieren otro patrón:

| Caso | ¿Por qué no alcanza on-demand? |
|---|---|
| Revisar cada PR que llega al repo | Los PRs llegan cuando llegan, no cuando vos corrés el script |
| Detectar regresiones de performance en tiempo real | Necesitás procesar cada deploy, las 24h |
| Moderar contenido en una plataforma | El contenido no espera tu turno |
| Monitorear logs de producción en busca de anomalías | Los logs fluyen continuamente |
| Responder issues de soporte automáticamente | Los usuarios esperan en minutos, no horas |

El patrón que resuelve esto es el **background agent**: un agente que corre indefinidamente, reaccionando a eventos o verificando condiciones, sin que nadie lo active manualmente.

---

## 12.2 Por qué es tendencia ahora

En 2024-2026 hubo un cambio de paradigma: los equipos pasaron de "agentes como herramientas" a "agentes como infraestructura". Las razones:

**1. Los LLMs son lo suficientemente buenos para tareas repetitivas**
El 80% del trabajo de revisión de código, triage de issues y categorización de bugs sigue patrones. Un agente bien diseñado los captura.

**2. El costo del token bajó drásticamente**
En 2023 era prohibitivo tener un agente leyendo cada PR. Hoy con prompt caching, Haiku, y optimización, procesar un PR cuesta < $0.01.

**3. La IA como infraestructura no como feature**
Linear, Notion, GitHub: todos tienen agentes de fondo que procesan eventos, no features de "chat con AI". El agente es parte del sistema operativo del producto.

**4. La atención humana es el recurso escaso**
Un equipo de 5 personas no puede revisar 50 PRs al día en profundidad. Un background agent puede pre-filtrar, comentar issues obvios, y detectar regresiones antes de que lleguen a revisión humana.

---

## 12.3 Qué necesitás ANTES de correr un agente persistente

Esta es la parte que más se saltea. Correr un agente en loop sin estos fundamentos es garantía de problemas:

### Checklist de prerequisites

**Observabilidad** (Módulo 5)
- [ ] Cada ejecución del agente tiene un `trace_id` único
- [ ] Tokens usados por ejecución loggeados y alertados
- [ ] Errores clasificados (¿es un error del agente, del modelo, o de la herramienta?)
- [ ] Dashboard de cuántas ejecuciones por hora/día

**Control de costos**
- [ ] Budget diario/mensual configurado en Anthropic Console
- [ ] Alerta cuando el costo supera X% del budget
- [ ] Límite máximo de tokens por ejecución individual
- [ ] Log del costo por evento procesado

**Idempotencia**
- [ ] Procesar el mismo evento dos veces produce el mismo resultado (o no hace nada la segunda vez)
- [ ] IDs de eventos guardados en DB para detectar duplicados
- [ ] Herramientas del agente son idempotentes (ej: `create_or_update_comment`, no `create_comment`)

**Dead Letter Queue**
- [ ] Mensajes que fallan después de N intentos van a una DLQ
- [ ] Alerta cuando la DLQ tiene mensajes
- [ ] Proceso para revisar y re-procesar mensajes de la DLQ

**Rate limiting**
- [ ] Rate limits de APIs externas respetados (GitHub: 5000 req/h)
- [ ] Backoff exponencial en reintentos
- [ ] Máximo de concurrencia configurado

**Graceful shutdown**
- [ ] El worker termina la ejecución actual antes de apagarse
- [ ] El estado no se corrompe si el proceso muere a mitad

**Falla:** saltarte cualquiera de estos y ponés un agente persistente en producción garantiza que en algún momento vas a procesar el mismo evento 5 veces, gastar $200 de tokens en un loop buggy, o perder eventos sin saber.

---

## 12.4 Los cuatro patrones de persistencia

### Patrón A — Queue-based Worker (el más robusto)

```
Evento externo → Cola (SQS/Redis) → Worker → Agente → Resultado
                                       ↑
                              [loop: consume → procesa → repite]
```

El agente no sabe de dónde vienen los eventos. Solo consume de la cola. La cola actúa como buffer, maneja reintentos y garantiza que los mensajes no se pierden.

**Cuándo usarlo:** cuando los eventos vienen de múltiples fuentes, cuando necesitás garantías de entrega, cuando el volumen puede pico.

```python
import asyncio
import json
from anthropic import Anthropic

client = Anthropic()

async def process_event(event: dict) -> dict:
    """Procesa un evento con el agente. Idempotente."""
    event_id = event["id"]

    # Idempotencia: si ya procesamos este evento, saltar
    if await already_processed(event_id):
        return {"skipped": True, "event_id": event_id}

    # El agente hace su trabajo
    result = await run_agent(event)

    # Marcar como procesado DESPUÉS de éxito
    await mark_processed(event_id)
    return result

async def worker_loop(queue):
    """Loop principal del worker. Corre indefinidamente."""
    print("Worker iniciado. Esperando eventos...")

    while True:
        try:
            message = await queue.receive(timeout=30)  # espera hasta 30s

            if message is None:
                continue  # cola vacía, volver a esperar

            event = json.loads(message.body)
            result = await process_event(event)

            if result.get("skipped"):
                await queue.delete(message)
                continue

            await queue.delete(message)  # solo borrar si procesó OK
            log_success(event["id"], result)

        except Exception as e:
            log_error(e)
            # NO borrar el mensaje → quedará en la cola → reintento automático
            # Después de N reintentos → DLQ
            await asyncio.sleep(5)  # backoff antes de reintentar
```

### Patrón B — Scheduled Worker (Cron)

```
Cron trigger → Agente corre una vez → Termina → Duerme hasta el próximo trigger
```

El agente no corre continuamente. Se lanza en intervalos.

**Cuándo usarlo:** reportes periódicos, auditorías, sincronización de datos, scraping.

```python
import time
import schedule

def run_nightly_analysis():
    """Corre análisis de issues sin resolver."""
    issues = fetch_open_issues_older_than(days=7)
    for issue in issues:
        agent_prioritize_issue(issue)

# Correr a las 3am todos los días
schedule.every().day.at("03:00").do(run_nightly_analysis)

while True:
    schedule.run_pending()
    time.sleep(60)
```

**En producción**, esto va en un CronJob de Kubernetes o AWS EventBridge → Lambda.

### Patrón C — Event-Reactive (Webhook → Queue)

```
Webhook (GitHub/Slack/etc.) → Lambda (validar + encolar) → Queue → Worker → Agente
```

La respuesta al webhook es instantánea (< 1s). El trabajo real es asíncrono.

**Cuándo usarlo:** responder a eventos externos en tiempo real sin que el webhook timeout.

```python
# Lambda: solo valida y encola (debe responder en < 3s)
def webhook_handler(event, context):
    if not validate_signature(event):
        return {"statusCode": 401}

    payload = json.loads(event["body"])
    if payload["action"] not in ("opened", "synchronize"):
        return {"statusCode": 200, "body": "ignored"}

    # Encolar para procesamiento async
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "pr_number": payload["pull_request"]["number"],
            "repo": payload["repository"]["full_name"],
            "sha": payload["pull_request"]["head"]["sha"]
        })
    )
    return {"statusCode": 202, "body": "queued"}

# Worker (ECS/Cloud Run): procesa cuando puede
async def process_pr_review(message):
    pr = json.loads(message["body"])
    review = await code_review_agent(pr)
    await post_github_comment(pr["pr_number"], review)
```

### Patrón D — Polling Loop (el más simple, el más costoso)

```
while True:
    eventos = buscar_eventos_nuevos()
    for evento in eventos:
        agente.procesar(evento)
    sleep(interval)
```

**Cuándo usarlo:** cuando no podés recibir webhooks (APIs que no los soportan), para prototipo rápido.

**Advertencia:** polling cada 30 segundos = 2880 requests/día a la API externa. Puede consumir rate limit rápido y cuesta más que un queue-based approach.

---

## 12.5 Anatomía de un background worker robusto

```python
import asyncio
import signal
import logging
from dataclasses import dataclass
from anthropic import Anthropic

logger = logging.getLogger(__name__)

@dataclass
class WorkerConfig:
    max_concurrent: int = 3       # máximo de eventos procesando en paralelo
    max_tokens_per_run: int = 8000  # budget por ejecución
    retry_attempts: int = 3
    shutdown_timeout: int = 30    # segundos para terminar ejecuciones en curso

class BackgroundWorker:
    def __init__(self, queue, config: WorkerConfig):
        self.queue = queue
        self.config = config
        self.client = Anthropic()
        self._running = True
        self._active_tasks = set()

        # Graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, *args):
        logger.info("Señal de shutdown recibida. Terminando ejecuciones en curso...")
        self._running = False

    async def run(self):
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        while self._running:
            messages = await self.queue.receive_batch(max_messages=self.config.max_concurrent)

            if not messages:
                await asyncio.sleep(1)
                continue

            tasks = [
                asyncio.create_task(
                    self._process_with_semaphore(semaphore, msg)
                )
                for msg in messages
            ]
            self._active_tasks.update(tasks)

            for task in tasks:
                task.add_done_callback(self._active_tasks.discard)

        # Esperar que terminen las tareas en curso antes de salir
        if self._active_tasks:
            logger.info(f"Esperando {len(self._active_tasks)} tareas en curso...")
            await asyncio.wait(self._active_tasks, timeout=self.config.shutdown_timeout)

    async def _process_with_semaphore(self, semaphore, message):
        async with semaphore:
            await self._process(message)

    async def _process(self, message):
        event = json.loads(message.body)
        trace_id = event.get("id", "unknown")

        try:
            logger.info(f"[{trace_id}] Procesando evento")
            result = await self._run_agent(event)
            await self.queue.delete(message)
            logger.info(f"[{trace_id}] Completado. Costo: ${result['cost_usd']:.4f}")

        except Exception as e:
            logger.error(f"[{trace_id}] Error: {e}")
            # El mensaje vuelve a la cola automáticamente (visibility timeout)
```

---

## 12.6 Multi-agente persistente

Para workloads con distintos tipos de eventos, un patrón común es tener agentes especializados:

```
                    ┌── Queue: PRs abiertos ──→ [PR Review Agent]
                    │
GitHub Webhook ──→  ├── Queue: Issues ──────→ [Issue Triage Agent]
                    │
                    └── Queue: CI failures ──→ [Bug Fix Agent]
```

Cada agente:
- Está optimizado para su tipo de tarea (prompts distintos, modelos distintos)
- Tiene su propio rate limit y budget
- Puede escalarse independientemente

```python
# Router que decide qué cola recibe el evento
def route_event(payload: dict) -> str:
    if payload["type"] == "pull_request" and payload["action"] == "opened":
        return "queue-pr-review"
    elif payload["type"] == "issues" and payload["action"] == "opened":
        return "queue-issue-triage"
    elif payload["type"] == "workflow_run" and payload["conclusion"] == "failure":
        return "queue-ci-fix"
    return "queue-default"
```

---

## 12.7 Eficiencia real: cuándo conviene vs cuándo no

No todos los casos justifican un agente persistente.

### Conviene cuando:

| Condición | Por qué ayuda |
|---|---|
| Volumen > 20 eventos/día | El setup tiene ROI |
| Eventos llegan de forma impredecible | On-demand no puede anticiparlo |
| El contexto del repo cambia poco | Prompt caching funciona bien: el contexto del repo se cachea entre ejecuciones |
| La latencia importa (< 5 min de respuesta) | No podés esperar a que alguien lo lance manualmente |

### No conviene cuando:

| Condición | Por qué no |
|---|---|
| Volumen < 5 eventos/día | El overhead de infra no tiene sentido |
| Cada evento necesita input humano para procesarse | No podés automatizarlo de todas formas |
| El costo por evento es alto (> $0.50) | Mejor proceso manual selectivo |
| El contexto cambia en cada evento | El prompt caching no ayuda, el costo es lineal |

### La trampa del costo oculto

Un agente que revisa PRs puede parecer barato por PR individual. Pero:

```
5 PRs/día × $0.05/PR × 30 días = $7.50/mes   ← razonable
50 PRs/día × $0.05/PR × 30 días = $75/mes    ← revisá si tiene ROI
500 PRs/día × $0.05/PR × 30 días = $750/mes  ← necesitás Haiku + caching agresivo
```

**Estrategia por volumen:**
- < 50 eventos/día: Sonnet, sin optimización especial
- 50-500 eventos/día: Haiku para clasificación inicial, Sonnet solo si es necesario
- > 500 eventos/día: arquitectura de dos etapas (filtro rápido + análisis profundo)

---

## 12.8 Prompt caching en workers: la optimización más importante

El contexto del repo (CONTEXT.md, estructura de archivos, reglas del proyecto) no cambia entre eventos. Cachearlo reduce el costo en 60-90%.

```python
# El contexto del repo se carga una vez y se reutiliza en cada evento
REPO_CONTEXT = load_repo_context()  # CONTEXT.md + estructura

async def run_agent(event: dict) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=[
            {
                "type": "text",
                "text": REPO_CONTEXT,
                "cache_control": {"type": "ephemeral"}  # ← se cachea entre llamadas
            }
        ],
        messages=[{
            "role": "user",
            "content": f"Revisá este PR:\n\n{format_pr(event)}"
        }]
    )

    # El costo de REPO_CONTEXT se paga una vez, no en cada evento
    cached_tokens = response.usage.cache_read_input_tokens
    total_tokens = response.usage.input_tokens
    savings = cached_tokens / total_tokens if total_tokens > 0 else 0
    logger.info(f"Cache hit: {savings:.0%} de los tokens en caché")

    return parse_response(response)
```

**TTL del caché de Anthropic:** 5 minutos. Si tu worker procesa eventos con menos de 5 minutos entre ellos, el caché siempre está warm.

---

## 12.9 Ejemplo completo: PR Review Worker

Un worker que revisa cada PR que se abre en un repo y deja un comentario automático.

```python
import asyncio
import json
import os
from anthropic import Anthropic
import httpx

client = Anthropic()
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

# Contexto que se cachea entre revisiones
REVIEW_CONTEXT = """
Sos un code reviewer experto. Tu trabajo es:
1. Detectar bugs evidentes
2. Identificar problemas de seguridad
3. Verificar que el cambio tiene tests
4. Revisar que la lógica es correcta

Sé conciso. Máximo 5 puntos por revisión.
Formato: bullet points, sin intro, directo al punto.
"""

async def review_pr(pr_data: dict) -> str:
    """Revisa un PR y retorna el comentario."""
    diff = await fetch_pr_diff(pr_data["repo"], pr_data["pr_number"])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=[{
            "type": "text",
            "text": REVIEW_CONTEXT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{
            "role": "user",
            "content": f"""
PR #{pr_data['pr_number']}: {pr_data['title']}

Diff:
{diff[:6000]}  # limitar tamaño del diff
"""
        }]
    )

    return response.content[0].text

async def post_review_comment(repo: str, pr_number: int, comment: str):
    async with httpx.AsyncClient() as http:
        await http.post(
            f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
            json={"body": f"🤖 **Revisión automática**\n\n{comment}"}
        )

async def worker():
    """Worker que procesa eventos de la cola."""
    queue = RedisQueue("pr-review-queue")

    print("PR Review Worker iniciado...")
    while True:
        message = await queue.receive(timeout=10)
        if not message:
            continue

        pr_data = json.loads(message)
        print(f"Revisando PR #{pr_data['pr_number']}...")

        try:
            comment = await review_pr(pr_data)
            await post_review_comment(pr_data["repo"], pr_data["pr_number"], comment)
            print(f"✓ PR #{pr_data['pr_number']} revisado")
        except Exception as e:
            print(f"✗ Error en PR #{pr_data['pr_number']}: {e}")

if __name__ == "__main__":
    asyncio.run(worker())
```

---

## 12.10 Observabilidad específica para workers

Los workers necesitan métricas propias:

```python
from dataclasses import dataclass, field
from datetime import datetime
import time

@dataclass
class WorkerMetrics:
    events_processed: int = 0
    events_failed: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    processing_times: list = field(default_factory=list)

    def record_success(self, cost_usd: float, tokens: int, duration_s: float):
        self.events_processed += 1
        self.total_cost_usd += cost_usd
        self.total_tokens += tokens
        self.processing_times.append(duration_s)

    def record_failure(self):
        self.events_failed += 1

    def report(self) -> dict:
        times = self.processing_times
        return {
            "events_processed": self.events_processed,
            "events_failed": self.events_failed,
            "success_rate": self.events_processed / (self.events_processed + self.events_failed),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "avg_cost_per_event": round(self.total_cost_usd / max(self.events_processed, 1), 4),
            "avg_processing_s": sum(times) / len(times) if times else 0,
            "p95_processing_s": sorted(times)[int(len(times) * 0.95)] if times else 0,
        }
```

**Métricas que importan para un worker:**
- **Success rate**: si baja de 95%, hay un problema sistémico
- **Costo promedio por evento**: si sube, el agente está consumiendo más tokens
- **p95 de tiempo de procesamiento**: detecta slowdowns antes de que afecten SLAs
- **Queue depth**: si crece, el worker no da abasto

---

## 12.11 Checklist: antes de poner tu worker en producción

- [ ] **Idempotencia verificada**: procesé el mismo evento 3 veces en staging, el resultado es el mismo
- [ ] **DLQ configurada y alertada**: sé cuándo un mensaje falla repetidamente
- [ ] **Budget diario configurado** en Anthropic Console con alerta al 80%
- [ ] **Límite de tokens por ejecución** definido y enforceado en el código
- [ ] **Graceful shutdown**: el worker termina la ejecución actual antes de apagarse
- [ ] **Health check endpoint**: el orchestrator puede verificar que el worker está vivo
- [ ] **Rate limits respetados**: el agente no puede hammear APIs externas
- [ ] **Logging estructurado**: cada evento tiene trace_id, costo, duración, resultado
- [ ] **Alerta de queue depth**: notificación si la cola crece por más de X minutos
- [ ] **Rollback plan**: cómo deshabilitar el worker en < 60 segundos si algo sale mal

---

## Ejemplos con output

Los tres ejemplos con código completo y el output real que producen están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Queue Worker básico](./EXAMPLES.md#ejemplo-1--queue-worker-básico) | Idempotencia, prompt caching, loop de consumo |
| [02 — PR Review Worker completo](./EXAMPLES.md#ejemplo-2--pr-review-worker-completo) | Métricas, selección de modelo por complejidad, graceful shutdown |
| [03 — Multi-agent router](./EXAMPLES.md#ejemplo-3--multi-agent-router) | Despacho de eventos a agentes especializados, JSON estructurado |

---

## Ejercicio

Tomá el `issue_solver.py` del módulo 3 y convertilo en un background worker:

1. **Modelá la cola**: definí el schema del mensaje (qué info necesita el agente para procesar un issue sin intervención humana)
2. **Implementá idempotencia**: el worker no debe procesar el mismo issue dos veces
3. **Agregá prompt caching**: el contexto del repo debe cachearse entre issues
4. **Implementá graceful shutdown**: si el proceso recibe SIGTERM, termina el issue actual antes de salir
5. **Medí el costo**: loggear cuánto costó cada issue procesado

Bonus: configurá un webhook de GitHub que encolé issues nuevos automáticamente y activá el worker en Cloud Run o Railway.

---

Anterior: [Módulo 11 → Deployment](../module-11-deployment/README.md)
