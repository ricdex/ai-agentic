# AI Agentic Engineering

> De "uso AI para escribir código" a "diseño sistemas que mueven producto solos"

---

## El gap real en el mercado

En 2025-2026 el criterio de evaluación para ingenieros en startups cambió.

Una empresa en SF rechazó a un candidato con excelente código porque:

> "The engagement has a specific requirement around production AI agentic workflows that we weren't able to fully evaluate from your take-home"

Ya no alcanza con saber usar Copilot. Ahora evalúan:

- ¿Cómo **diseñas** un feedback loop automático que detecta una regresión y abre un PR de fix?
- ¿Cómo cambia un agente sus **criterios de decisión en runtime** según el stage?
- ¿Cómo construyes un workflow que mueve producto con **poca intervención humana**?

Este curso es para pasar de "usuario de AI" a "arquitecto de sistemas agénticos".

---

## Para quién es

**Sí — este curso es para vos si:**
- Tenés 2+ años de experiencia en producción
- Conocés tus frameworks en profundidad (no solo la API surface)
- Tenés background en CS: algoritmos, sistemas, concurrencia
- Ya usás AI con alta productividad
- Querés escribir código sólido que escala, no prompts que "funcionan a veces"

**No — este curso no es para:**
- Vibe coders o prompt engineers sin base técnica
- Quienes buscan una lista de MCPs para instalar y listo
- Quienes no entienden cómo funciona HTTP, bases de datos o concurrencia

---

## Stack

| Componente | Tecnología | Por qué |
|---|---|---|
| AI Core | **Claude** (Anthropic) | Tool use nativo, extended thinking, prompt caching |
| Orquestación | **LangGraph** (OSS) | Grafos de estado explícitos, testeable, debuggeable |
| Observabilidad | **Langfuse** (OSS) | Trazabilidad, costos, evals — self-hosteable |
| Agents / lógica | **Python** | Ecosistema AI maduro, Anthropic SDK |
| APIs / Webhooks | **TypeScript** | Type safety, ecosistema web |
| Workers rápidos | **Go** | Performance, bajo consumo, arranque en <10ms |
| Estado | **Redis** + **PostgreSQL** | Simple, predecible, sin vendor lock-in |

**Principio:** minimizar software propietario. Todo lo que se puede hacer open-source, se hace open-source.

---

## Ingeniería guiada por especificaciones, no por volumen de código

Un agente puede producir código mucho más rápido que una persona. Por eso el trabajo de un AI Engineer no es dictarle implementaciones: es definir con precisión **qué resultado de negocio debe conseguir**, qué no puede hacer y cómo se comprobará.

Usamos **Spec → Tests → Implementación → Evals**:

1. **Spec**: contrato breve y versionado con objetivo, alcance, reglas, interfaces observables, riesgos y criterios de aceptación.
2. **Tests**: evidencia determinista de los comportamientos críticos del contrato.
3. **Implementación**: el agente elige el mínimo código necesario para satisfacer ambos.
4. **Evals**: miden calidad, seguridad, coste y comportamiento del agente en escenarios reales.

Los tests no sustituyen una spec: prueban ejemplos concretos. La spec evita que el agente optimice para una suite incompleta, invente alcance o tome decisiones de producto sin autorización. Tampoco buscamos documentos largos: una spec debe explicar el resultado y los límites, no prescribir cada clase o función.

El template de [Feature Spec](./module-00-developer-workflow/templates/feature-spec.md.template) es el punto de partida para cada cambio no trivial.

---

## Ruta paso a paso

No intentes leer todos los módulos ni ejecutar todos los scripts. Cada paso produce un artefacto que el siguiente usa.

1. **Define el contrato:** completa una Feature Spec con resultado, límites y criterios de aceptación. Empieza en el [Módulo 0](./module-00-developer-workflow/README.md).
2. **Entiende el loop mínimo:** ejecuta un agente que usa una herramienta, observa el ciclo y añade una sola regla de finalización en el [Módulo 1](./module-01-fundamentals/README.md).
3. **Hazlo confiable:** diseña el estado, los reintentos y el gate humano de un caso real en el [Módulo 2](./module-02-workflow-design/README.md).
4. **Resuelve una issue:** pasa de una Feature Spec a tests, cambio mínimo y PR en el [Módulo 3](./module-03-dev-workflows/README.md).
5. **Añade controles de producción:** define política por entorno, trazas, coste y evals en los módulos [4](./module-04-runtime-adaptability/README.md), [5](./module-05-production/README.md) y [10](./module-10-evals/README.md).
6. **Elige capacidades solo si el caso las necesita:** memoria/RAG (6), datos estructurados (7), MCP (8), streaming (9) y multimodal (13).
7. **Despliega el patrón adecuado:** usa serverless para trabajo corto o jobs efímeros para trabajo largo en el [Módulo 11](./module-11-deployment/README.md); usa agentes persistentes solo si hay un evento o una cola que los justifique (12).
8. **Entrená solo si el volumen lo justifica:** agotá prompting y RAG antes de considerar fine-tuning — el framework de decisión está en el [Módulo 14](./module-14-fine-tuning/README.md).
9. **Integra todo:** ejecuta y mejora la [Software Factory](./final-project/README.md) sin saltarte la aprobación de la Feature Spec.

**Regla de avance:** no pases al siguiente paso hasta poder explicar el artefacto generado y el criterio que demuestra que funciona. El código es la última consecuencia de una decisión bien especificada.

---

## Estructura del curso

```
module-00-developer-workflow/ ← Setup, CONTEXT.md, TDD, diagnóstico, handoffs
module-01-fundamentals/       ← Qué es un agente de verdad
module-02-workflow-design/    ← Cómo diseñar loops y coordinación
module-03-dev-workflows/      ← Agentes que mueven producto
module-04-runtime-adaptability/ ← Decisiones dinámicas en runtime
module-05-production/         ← Observabilidad, costos, seguridad
final-project/                ← Software Factory: Issue → Triage → Implement → Review → PR

── Avanzado ──────────────────────────────────────────────────────
module-06-rag-memory/         ← RAG, embeddings, memoria semántica
module-07-structured-outputs/ ← Schema enforcement, Pydantic, extracción
module-08-mcp/                ← Model Context Protocol (estándar emergente)
module-09-streaming/          ← Streaming, TTFT, SSE para frontend
module-10-evals/              ← Eval suites, LLM-as-Judge, regresiones en CI
module-11-deployment/         ← Lambda, containers, IaC, secrets, health checks
module-12-background-agents/  ← Workers persistentes, queues, agentes 24/7
module-13-multimodal/         ← Vision, documentos, audio → texto + Claude
module-14-fine-tuning/        ← Cuándo (no) entrenar; LoRA en modelos abiertos
```

| # | Módulo | Duración estimada |
|---|---|---|
| 0 | **Developer Workflow con AI** | 3 días |
| 1 | Fundamentos de agentes | 1 semana |
| 2 | Diseño de workflows | 1.5 semanas |
| 3 | Dev workflows agénticos | 1.5 semanas |
| 4 | Runtime adaptability | 1 semana |
| 5 | Producción y observabilidad | 1 semana |
| F | **Proyecto Final: Software Factory** | 2 semanas |
| — | *— Avanzado —* | — |
| 6 | RAG y memoria semántica | 1 semana |
| 7 | Structured outputs | 3 días |
| 8 | MCP (Model Context Protocol) | 3 días |
| 9 | Streaming | 2 días |
| 10 | Evals y calidad | 1 semana |
| 11 | Deployment en producción | 1 semana |
| 12 | Agentes persistentes y background workers | 1 semana |
| 13 | Agentes multimodales (vision, documentos, audio) | 3 días |
| 14 | Fine-tuning: cuándo (no) usarlo | 3 días |

---

## Setup inicial

### Requisitos

```bash
python --version          # 3.11+
docker --version          # para el proyecto final (docker compose)
docker compose version    # para el proyecto final
```

### Variables de entorno

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export LANGFUSE_PUBLIC_KEY="pk-lf-..."   # opcional, para observabilidad
export LANGFUSE_SECRET_KEY="sk-lf-..."
export GITHUB_WEBHOOK_SECRET="..."        # solo para proyecto final
```

### Instalar dependencias

```bash
# Python (módulos 1-5 + final)
pip install anthropic langfuse pydantic pytest pytest-asyncio httpx

# Python (módulos avanzados 6-11)
pip install sentence-transformers numpy mcp fastapi uvicorn

# Python (módulo 6, vector store en producción — opcional, requiere Postgres+pgvector)
pip install psycopg[binary]

# Python (módulo 13 — multimodal)
pip install faster-whisper

# Python (módulo 14 — fine-tuning local con LoRA)
pip install torch transformers peft datasets

# Proyecto final: Software Factory (vm1-orchestrator, vm2-implementor, vm3-reviewer)
# Corre entera con Docker Compose, no hace falta instalar cada servicio a mano
cd final-project && make up
```

---

## Modelos de Claude que usamos

| Modelo | Cuándo usarlo | Costo relativo |
|---|---|---|
| `claude-opus-5` | Planificación compleja, razonamiento profundo | Alto |
| `claude-sonnet-5` | Balance calidad/velocidad, la mayoría de los casos | Medio |
| `claude-haiku-4-5-20251001` | Clasificación, routing, tareas simples y rápidas | Bajo |

**Regla práctica:** empezá con Sonnet. Bajá a Haiku si no necesitás razonamiento. Subí a Opus solo si el problema lo requiere.

---

## Referencias clave

- [Anthropic Docs](https://docs.anthropic.com)
- [Claude Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [Claude Extended Thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)
- [Claude Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Anthropic TypeScript SDK](https://github.com/anthropics/anthropic-sdk-typescript)
- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [Langfuse](https://langfuse.com/docs)

---

Empezá por [Módulo 0 → Developer Workflow](./module-00-developer-workflow/README.md)
