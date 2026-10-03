# Módulo 2 — Diseño de Workflows Agénticos

> "Un workflow agéntico no es un script con LLM. Es un grafo de estados con decisiones explícitas y feedback loops que se autocorrigen."

---

## Paso a paso

1. Elegí una Feature Spec del módulo 0 y dibujá sus estados: inicio, verificación, éxito, fallo y escalamiento.
2. Ejecutá `examples/feedback_loop.py`; observá qué dato decide un retry y cuándo termina.
3. Añadí un gate humano para una acción irreversible.
4. Recién después ejecutá `multi_agent.py`; usá múltiples agentes solo si un especialista reduce riesgo o tiempo de forma medible.
5. Con `agent_patterns.py`, compará plan-and-execute, reflection y subagentes sobre la misma tarea. Elegí el patrón por la falla que querés evitar, no por moda.

**Complejidad a evitar:** un grafo grande o multi-agente sin criterio de evaluación, límite de reintentos y dueño de la decisión final.

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

## 2.7 Patrones de agente: elegir por la falla que querés evitar

El loop ReAct del Módulo 1 (pensar → actuar → observar, repetir) es el punto de partida. Los patrones de esta sección **no lo reemplazan**: lo envuelven para corregir fallas concretas.

| Patrón | Falla que corrige | Costo |
|---|---|---|
| **Plan-and-Execute** | El agente "deambula": decide el próximo paso sin visión global | Replanificar cuando el plan choca con la realidad |
| **Reflection** | La primera respuesta es mediocre y nadie la revisa | 1 llamada de evaluación + 1 de revisión por ronda |
| **Subagentes** | El contexto del agente principal se llena con exploración | Más llamadas totales; latencia si no se paraleliza |

### Plan-and-Execute

Un modelo capaz escribe el plan **una vez**; un modelo barato ejecuta cada paso. Si un paso falla, se replanifica **solo lo que falta**, con el fallo como contexto.

```
planner (Opus) ──→ ["crear tabla", "agregar índice", "escribir migración"]
                      │
executor (Haiku) ─────┼─ paso 1 ✓
                      ├─ paso 2 ✗ "no existe la columna"
planner ──────────────┤  replan: ["agregar columna", "agregar índice", "escribir migración"]
                      └─ ...
```

Ventaja extra: el plan es un **artefacto visible**. Se puede loguear, revisar o aprobar (gate humano) antes de ejecutar nada.

### Reflection (evaluator-optimizer)

Generar → evaluar contra un criterio → revisar con el feedback, hasta pasar o agotar rondas. Es el mismo feedback loop de 2.2, pero el "test" puede ser una rúbrica.

**El evaluador vale lo que vale su señal.** En orden de confiabilidad:

1. Señal externa determinista: tests, linter, validación de schema, compilador.
2. LLM-as-judge con **otro modelo** y una rúbrica explícita ([Módulo 10](../module-10-evals/README.md)).
3. El mismo modelo preguntándose "¿está bien?": tiene sesgo a aprobarse. Evitalo.

### Subagentes: aislar contexto

Un subagente es un agente que arranca con **contexto limpio** (solo su tarea), trabaja y devuelve **un resumen acotado**. El orquestador nunca ve los 30 archivos que leyó el subagente, solo la conclusión.

```
Orquestador (contexto: objetivo + 3 resúmenes)
   ├── subagente A: "investigar SQS"            → 300 tokens de resumen
   ├── subagente B: "investigar Redis Streams"  → 300 tokens   (en paralelo)
   └── subagente C: "investigar Pub/Sub"        → 300 tokens
```

Cuándo sí: tareas **independientes** y de lectura pesada (investigar, revisar N archivos, buscar en N fuentes). Cuándo no: tareas que comparten estado o se escriben mutuamente los mismos archivos; ahí la coordinación cuesta más que el aislamiento. Es lo que hace Claude Code con su herramienta de subagentes, y lo que ofrece Managed Agents como sesiones multi-agente.

---

## 2.8 Skills: instrucciones que se cargan bajo demanda

Un system prompt que intenta cubrir todos los casos crece hasta degradarse. Una **skill** es una carpeta con un `SKILL.md` (instrucciones + scripts + referencias). En el contexto solo vive su **descripción de una línea**; el agente lee el archivo completo cuando la tarea lo requiere.

```
skills/
  migraciones-db/
    SKILL.md          ← "Usar al crear o modificar migraciones de base de datos"
    checklist.md
    scripts/validate_migration.py
```

Es *context engineering* aplicado a instrucciones ([Módulo 3, sección 3.7](../module-03-dev-workflows/README.md#37-context-engineering-el-contexto-es-un-recurso-finito)): conocimiento procedural disponible sin pagar sus tokens en cada turno. El [Módulo 0](../module-00-developer-workflow/README.md) ya muestra el equivalente como skills de Claude Code. Por API, las skills se usan con la herramienta de code execution; ver la [documentación de Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).

---

## 2.9 Computer use: cuando no hay API

Un agente de *computer use* opera una interfaz gráfica: recibe screenshots y devuelve acciones (click, tipear, scroll). Claude lo soporta como herramienta del API (`computer_toolset_20260801` en los modelos actuales; ver la [documentación de computer use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)).

Es la **última** opción, no la primera:

| Si existe... | Usá |
|---|---|
| API o SDK | Tool use normal: más rápido, barato y determinista |
| MCP server | MCP ([Módulo 8](../module-08-mcp/README.md)) |
| Solo una web | Automatización de browser (Playwright) controlada por el agente |
| Solo una app de escritorio legacy | Computer use |

Reglas si lo usás: correr en una VM o contenedor aislado, sin credenciales reales salvo las mínimas, con allowlist de dominios, y con gate humano antes de cualquier acción irreversible (pagar, borrar, enviar). Todo lo que aparece en pantalla es input no confiable: una página puede contener instrucciones dirigidas al agente ([Módulo 5, sección 5.5](../module-05-production/README.md#55-seguridad-en-agentes)).

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Feedback loop](./EXAMPLES.md#ejemplo-1--feedback-loop-agente-que-itera-hasta-que-los-tests-pasan) | Agente escribe código, corre tests, itera hasta verde — 3 iteraciones para Stack |
| [02 — Multi-agente orquestador](./EXAMPLES.md#ejemplo-2--multi-agente-orquestador--ejecutores-especializados) | Planificador (Haiku) + Developer (Sonnet) coordinados por un orquestador |
| [03 — Patrones de agente](./EXAMPLES.md#ejemplo-3--patrones-de-agente-plan-and-execute-reflection-subagentes) | Plan-and-execute con replan, reflection que pasa en la 2ª ronda, 3 subagentes en paralelo |

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
