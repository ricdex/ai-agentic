# Módulo 5 — Producción y Observabilidad

> "Un agente que no podés observar no es un agente de producción — es una caja negra con esperanza."

---

## 5.1 Por qué la observabilidad es diferente en agentes

En un backend clásico trazás requests. En un agente trazás **cadenas de decisiones**.

Lo que necesitás ver:

```
Trace: solve_issue(issue_id=456)
  │
  ├─ span: explore_repo (2.3s)
  │    ├─ tool: list_files → 23 archivos
  │    └─ tool: search_code("payment") → 5 matches
  │
  ├─ span: write_fix (1.1s)
  │    ├─ tool: read_file("src/payments.py") → 340 tokens
  │    └─ tool: write_file("src/payments.py") → éxito
  │
  ├─ span: verify (4.2s)
  │    └─ tool: run_tests() → FAILED: 2 tests
  │
  └─ span: iterate_fix (1.8s)
       ├─ model: claude-sonnet-4-6
       ├─ input_tokens: 4523 (cached: 3100)
       └─ output_tokens: 891
```

Sin esto, cuando un agente falla no sabés si fue el modelo, una herramienta, o la lógica de orquestación.

---

## 5.2 Langfuse: observabilidad open-source para agentes

[Langfuse](https://langfuse.com) es el estándar de facto para observabilidad de LLMs. Se puede auto-hostear con Docker.

```bash
# Self-hosted con Docker
docker run --name langfuse \
  -e DATABASE_URL=postgresql://... \
  -e NEXTAUTH_SECRET=... \
  -p 3000:3000 \
  langfuse/langfuse:latest
```

Lo que trackea automáticamente:
- Latencia por llamada y por trace completo
- Tokens usados (input/output/cached)
- Costo estimado
- Errores y excepciones
- Scores de evaluación (podés agregar los tuyos)

**Referencia:** [Langfuse Docs](https://langfuse.com/docs)

---

## 5.3 Evals: la única forma de saber si mejoró

Un agente sin evals es como un servidor sin métricas — sabés que algo falló cuando el usuario se queja.

**Eval básica para un dev agent:**

```python
@dataclass
class AgentEval:
    issue_id: str
    ground_truth_fix: str    # el fix correcto
    agent_fix: str           # lo que produjo el agente

    def score(self) -> dict:
        return {
            "tests_pass": self.run_tests_on_fix(),
            "diff_similarity": self.compare_diffs(),
            "no_regression": self.check_no_regression()
        }
```

**Cuándo correr evals:**
- En cada PR que toca el agente
- Nightly contra un conjunto de issues históricos
- Cuando cambiás de modelo

**Referencia:** [Langfuse Evals](https://langfuse.com/docs/scores/overview)

---

## 5.4 Costos: cómo no arruinarte

Fórmula de costo aproximado (Claude Sonnet):

```
costo = (input_tokens × $3/MTok) + (output_tokens × $15/MTok)
costo_cached = input_tokens × $0.30/MTok  # 90% más barato
```

**Estrategias de reducción de costo:**

1. **Prompt caching** — siempre para contexto estático (ya lo vimos)
2. **Selección de modelo** — Haiku para tareas simples
3. **Límite de herramientas** — menos context = menos tokens
4. **Compresión de historial** — resumí conversaciones largas antes de continuar

```python
# Comprimir historial cuando crece demasiado
def compress_history(messages: list, max_tokens: int = 10_000) -> list:
    if estimate_tokens(messages) < max_tokens:
        return messages

    # Pedir a Claude que resuma la conversación anterior
    summary = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku para esto
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"Resumí esta conversación en 3-5 bullets:\n\n{format_messages(messages)}"
        }]
    ).content[0].text

    return [
        {"role": "user", "content": f"[Historial resumido]\n{summary}"},
        messages[-1]  # Solo el último mensaje
    ]
```

---

## 5.5 Seguridad en agentes

Los agentes tienen herramientas que pueden hacer cosas irreversibles. Salvaguardas mínimas:

**1. Sandboxing de herramientas**
```python
ALLOWED_PATHS = ["/tmp/agent-workspace/"]

def safe_write_file(path: str, content: str) -> str:
    # Prevenir path traversal
    real_path = os.path.realpath(path)
    if not any(real_path.startswith(allowed) for allowed in ALLOWED_PATHS):
        return f"ERROR: Path no permitido: {path}"
    return write_file(path, content)
```

**2. Rate limiting por agente**
```python
from functools import wraps
import time

def rate_limit(calls_per_minute: int):
    min_interval = 60.0 / calls_per_minute
    last_called = {}

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            if func.__name__ in last_called:
                elapsed = now - last_called[func.__name__]
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
            last_called[func.__name__] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

**3. Prompt injection prevention**
Si el agente lee archivos que podrían contener instrucciones maliciosas:
```python
def sanitize_tool_result(result: str) -> str:
    # Prevenir prompt injection desde archivos externos
    suspicious_patterns = [
        "ignore previous instructions",
        "system prompt",
        "you are now",
        "<|im_start|>"
    ]
    for pattern in suspicious_patterns:
        if pattern.lower() in result.lower():
            return "[CONTENIDO SANITIZADO: posible prompt injection detectado]"
    return result
```

---

## 5.6 Checklist de production-readiness

Antes de poner un agente en producción:

- [ ] Trazabilidad completa (cada llamada loggea trace_id, tokens, latencia)
- [ ] Límite de iteraciones en todos los loops
- [ ] Timeout en todas las herramientas
- [ ] Path sandboxing para herramientas de filesystem
- [ ] Rate limiting
- [ ] Escalamiento a humano definido
- [ ] Evals corriendo en CI
- [ ] Budget de tokens por request
- [ ] Alertas en Langfuse (costo > umbral, error rate > umbral)
- [ ] Documentación de qué puede y no puede hacer el agente

---

## Ejemplo de código

- [`observability.py`](./examples/observability.py) — El issue solver del módulo 3 con trazabilidad completa en Langfuse

---

## Ejercicio

Instrumentá uno de los agentes de módulos anteriores con:

1. Logging estructurado (JSON) de cada llamada a Claude y cada tool call
2. Tracking de tokens (input, output, cached)
3. Tiempo total y por iteración
4. Un script que lea esos logs y genere un reporte de: "cuánto costó cada run", "cuántas iteraciones en promedio", "cuál es la tasa de éxito"

Bonus: deployalo como función serverless (AWS Lambda o Cloud Run) con un endpoint HTTP que recibe el issue y retorna el resultado asíncronamente.

---

Siguiente: [Proyecto Final → Autopilot](../final-project/README.md)
