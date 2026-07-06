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

## ¿Por qué no SDD (Spec Driven Development)?

SDD agrega un paso formal de especificación antes de codear. En workflows agénticos, **los tests son la spec**. El agente sabe que terminó cuando los tests pasan — no cuando un documento dice que terminó.

Usamos **TaS (Tests as Spec)**: escribís los tests primero, el agente trabaja hasta que pasan. Más simple, más robusto, más alineado con cómo funcionan los sistemas en producción.

---

## Estructura del curso

```
module-00-developer-workflow/ ← Setup, CONTEXT.md, TDD, diagnóstico, handoffs
module-01-fundamentals/       ← Qué es un agente de verdad
module-02-workflow-design/    ← Cómo diseñar loops y coordinación
module-03-dev-workflows/      ← Agentes que mueven producto
module-04-runtime-adaptability/ ← Decisiones dinámicas en runtime
module-05-production/         ← Observabilidad, costos, seguridad
final-project/                ← Autopilot: GitHub Issue → PR autónomo

── Avanzado ──────────────────────────────────────────────────────
module-06-rag-memory/         ← RAG, embeddings, memoria semántica
module-07-structured-outputs/ ← Schema enforcement, Pydantic, extracción
module-08-mcp/                ← Model Context Protocol (estándar emergente)
module-09-streaming/          ← Streaming, TTFT, SSE para frontend
module-10-evals/              ← Eval suites, LLM-as-Judge, regresiones en CI
module-11-deployment/         ← Lambda, containers, IaC, secrets, health checks
module-12-background-agents/  ← Workers persistentes, queues, agentes 24/7
```

| # | Módulo | Duración estimada |
|---|---|---|
| 0 | **Developer Workflow con AI** | 3 días |
| 1 | Fundamentos de agentes | 1 semana |
| 2 | Diseño de workflows | 1.5 semanas |
| 3 | Dev workflows agénticos | 1.5 semanas |
| 4 | Runtime adaptability | 1 semana |
| 5 | Producción y observabilidad | 1 semana |
| F | **Proyecto Final: Autopilot** | 2 semanas |
| — | *— Avanzado —* | — |
| 6 | RAG y memoria semántica | 1 semana |
| 7 | Structured outputs | 3 días |
| 8 | MCP (Model Context Protocol) | 3 días |
| 9 | Streaming | 2 días |
| 10 | Evals y calidad | 1 semana |
| 11 | Deployment en producción | 1 semana |
| 12 | Agentes persistentes y background workers | 1 semana |

---

## Setup inicial

### Requisitos

```bash
python --version   # 3.11+
node --version     # 20+
go version         # 1.22+
redis-cli --version # 7+
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

# TypeScript (webhook handler del proyecto final)
cd final-project/webhook-handler && npm install

# Go (test runner del proyecto final)
cd final-project/test-runner && go mod download
```

---

## Modelos de Claude que usamos

| Modelo | Cuándo usarlo | Costo relativo |
|---|---|---|
| `claude-opus-4-7` | Planificación compleja, razonamiento profundo | Alto |
| `claude-sonnet-4-6` | Balance calidad/velocidad, la mayoría de los casos | Medio |
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
