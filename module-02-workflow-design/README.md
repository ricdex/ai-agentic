# Módulo 2 — Diseño de Workflows Agénticos

> "Un workflow agéntico no es un script con LLM. Es un grafo de estados con decisiones explícitas y feedback loops que se autocorrigen."

---

## 2.1 El problema del script lineal

La mayoría de los intentos de "automatizar con AI" terminan siendo esto:

```python
# ❌ Script lineal — no es un workflow agéntico
def auto_fix_bug(issue):
    code = read_codebase()
    fix = llm.ask(f"Arregla este bug: {issue}\n\nCódigo:\n{code}")
    write_file(fix)
    # FIN — sin verificación, sin iteración, sin feedback
```

¿Qué falla?
- No sabe si el fix funcionó
- No itera si hay errores
- No tiene criterio de corte
- No hay mecanismo para escalar a un humano

Un workflow agéntico real tiene **estados**, **transiciones** y **feedback loops**.

---

## 2.2 Anatomía de un feedback loop

```
        ┌─────────────────────────────┐
        │                             │
        ▼                             │
   [PLANIFICAR]                       │
        │                             │ falló
        ▼                             │
   [EJECUTAR] ─────────────────── [ANALIZAR ERROR]
        │                             ▲
        ▼                             │
   [VERIFICAR] ──── tests fallan ─────┘
        │
        │ tests pasan
        ▼
   [DONE / ESCALAR]
```

Los loops bien diseñados tienen:
1. **Condición de salida** (tests pasan, criterio satisfecho)
2. **Límite de iteraciones** (no loop infinito)
3. **Criterio de escalamiento** (cuándo involucrar a un humano)

---

## 2.3 Human-in-the-loop: cuándo y por qué

**Siempre automático (sin humano):**
- Tests unitarios pasan/fallan
- Lint errors
- Formateo de código
- Generación de tests para código nuevo

**Requiere humano:**
- Cambios en contratos de API públicas
- Modificaciones de esquema de base de datos en producción
- Decisiones de arquitectura (cambiar un patrón fundamental)
- Cuando el agente alcanzó max_retries sin resolver

**Regla:** si el error de un agente es recuperable y sin efecto secundario irreversible, dejalo iterar solo. Si no, involucra al humano.

---

## 2.4 Coordinación multi-agente

Dos patrones principales:

### Orquestador-Ejecutor (el más común)

```
[Orquestador] ── planifica ──→ [Ejecutor A: escribir código]
      │                        [Ejecutor B: correr tests]
      │                        [Ejecutor C: revisar código]
      │
      └── consolida resultados y decide próximo paso
```

**Cuándo usarlo:** cuando las subtareas son independientes y pueden correr en paralelo.

**Ejemplo real:** [SWE-bench](https://www.swebench.com/) — un orquestador recibe un issue, delega a agentes especializados (análisis, codeo, testing), consolida el resultado.

### Peer-to-Peer (menos común, más complejo)

```
[Agente A] ←──────────────────→ [Agente B]
   (propone)         (critica / aprueba)
```

**Cuándo usarlo:** cuando necesitás doble revisión, como un "code review" de agente.

---

## 2.5 Decisiones en runtime

Un agente sofisticado cambia su comportamiento según el contexto actual. Esto se implementa pasando el **estado del sistema** como contexto al agente.

```python
# Estado que el agente recibe antes de decidir
state = {
    "stage": "production",          # dev | staging | production
    "test_failures_so_far": 2,      # cuántos intentos fallidos
    "budget_remaining_tokens": 8000, # presupuesto restante
    "files_changed": ["auth.py"],   # qué archivos modificó
    "risk_score": "high"            # calculado por otra función
}

# El agente usa esto para decidir cuán agresivo ser
# Si stage=production y risk_score=high → más conservador, escala a humano
# Si stage=dev y failures < 3 → sigue iterando solo
```

---

## 2.6 LangGraph: cuando necesitás más estructura

Para workflows con estados complejos y transiciones explícitas, LangGraph es la herramienta correcta. Define el workflow como un **grafo**:

```python
from langgraph.graph import StateGraph

workflow = StateGraph(AgentState)
workflow.add_node("plan", plan_node)
workflow.add_node("code", code_node)
workflow.add_node("test", test_node)
workflow.add_node("human_review", human_review_node)

workflow.add_conditional_edges(
    "test",
    decide_next_step,     # función que devuelve el nombre del siguiente nodo
    {
        "retry": "code",
        "escalate": "human_review",
        "done": END
    }
)
```

**Referencia:** [LangGraph Docs](https://langchain-ai.github.io/langgraph/)

Para casos simples (< 4 estados), no uses LangGraph — es overhead innecesario.

---

## Ejemplos de código

- [`feedback_loop.py`](./examples/feedback_loop.py) — Agente que escribe código y itera hasta que compila y pasa tests
- [`multi_agent.py`](./examples/multi_agent.py) — Patrón orquestador-ejecutor: planificador + ejecutor separados

---

## Ejercicio

Diseñá (en papel o código) un workflow para este caso:

**Escenario:** Querés un agente que, dado un nuevo endpoint de API, genere automáticamente los tests de integración.

Preguntas a responder:
1. ¿Cuáles son los estados del workflow?
2. ¿Cuál es la condición de salida exitosa?
3. ¿Cuándo debe escalar al humano?
4. ¿Cuál es el límite de iteraciones y por qué?
5. ¿Qué herramientas necesita el agente?

---

Siguiente: [Módulo 3 → Dev Workflows Agénticos](../module-03-dev-workflows/README.md)
