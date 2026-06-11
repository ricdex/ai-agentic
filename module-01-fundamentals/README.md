# Módulo 1 — Fundamentos de Agentes

> "Un agente no es un LLM que llama funciones. Es un sistema que percibe, decide y actúa en un loop — con memoria."

---

## 1.1 ¿Qué es un agente de verdad?

### La distinción que importa

**Esto NO es un agente:**
```python
response = claude.ask("Generame código para esta función")
print(response)
```

Eso es autocompletado glorificado. No hay loop, no hay memoria, no hay capacidad de iterar.

**Esto SÍ es un agente:**

```
while not done:
    observation  = perceive(environment)
    plan         = decide(observation, memory, tools)
    action       = select_action(plan)
    result       = execute(action)
    memory.update(result)
    done         = check_completion(result, goal)
```

La diferencia es el **loop de decisión** y la **memoria de estado**.

### Ejemplo de la vida real: Devin vs Copilot

| | GitHub Copilot | Devin / Copilot Workspace |
|---|---|---|
| Percibe | Cursor position + contexto | Repo completo + issue + tests |
| Decide | Próxima línea probable | Plan de cambios (multi-step) |
| Actúa | Sugerencia de código | Edita archivos, corre tests, itera |
| Memoria | Context window | Estado del workspace (archivos, resultados) |
| Loop | No | Sí — itera hasta que tests pasan |

Copilot es un **asistente de escritura**. Devin es un **agente de desarrollo**.

---

## 1.2 El loop de un agente

El loop clásico en sistemas agénticos se llama **ReAct** (Reason + Act):

```
Thought: Necesito entender qué falla antes de cambiar código
Action: run_tests()
Observation: "TypeError: 'NoneType' object is not subscriptable en line 42"
Thought: El bug está en que no validamos el retorno de fetch_user()
Action: read_file("src/users.py")
Observation: [contenido del archivo]
Thought: Veo que fetch_user() puede retornar None. Necesito agregar un check.
Action: write_file("src/users.py", <contenido corregido>)
Observation: "Archivo actualizado"
Action: run_tests()
Observation: "All tests passed"
Thought: El bug está resuelto.
Final Answer: Agregué validación de None en fetch_user() en línea 42.
```

Este loop es la base de todos los agentes que vas a construir en este curso.

**Referencia:** [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

---

## 1.3 Taxonomía de agentes

| Tipo | Comportamiento | Cuándo usarlo |
|---|---|---|
| **Reactive** | Estímulo → respuesta directa, sin planificación | Routing, clasificación, respuestas simples |
| **Deliberative** | Planifica antes de actuar, mantiene modelo del mundo | Tareas complejas multi-step |
| **Hybrid** | Planifica a alto nivel, reacciona a bajo nivel | La mayoría de casos en producción |

**Ejemplo real:** Un agente de soporte al cliente (Intercom, Zendesk AI) es híbrido: planifica si escalar o resolver, pero reacciona rápido a preguntas frecuentes.

---

## 1.4 Tipos de memoria

```
┌─────────────────────────────────────────────┐
│                   AGENTE                     │
│                                             │
│  ┌──────────────┐   ┌──────────────────┐   │
│  │  In-Context  │   │   External DB    │   │
│  │  (efímera)   │   │   (persistente)  │   │
│  │              │   │                  │   │
│  │ Conversación │   │ PostgreSQL       │   │
│  │ actual       │   │ Redis            │   │
│  │ ~200k tokens │   │ Vector store     │   │
│  └──────────────┘   └──────────────────┘   │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │           Episodic Memory             │  │
│  │  "La última vez que traté de hacer   │  │
│  │   X, falló por Y. Esta vez evito Y"  │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**Regla práctica:**
- In-context: para el task actual
- External: para conocimiento que sobrevive sesiones
- Episodic: para aprender de errores pasados (avanzado)

---

## 1.5 Tool use con Claude

El mecanismo central. Claude puede llamar herramientas (funciones que vos definís) durante su razonamiento.

**Flujo:**

```
Tu código                      Claude
    │                             │
    │ messages + tools_schema ──→ │
    │                             │ ← razona
    │ ←── tool_use: read_file ─── │
    │                             │
    │ ejecuta read_file()         │
    │ ──── tool_result ─────────→ │
    │                             │ ← continúa razonando
    │ ←── end_turn: "El bug..." ─ │
```

Lo importante: **Claude decide cuándo y cómo usar cada herramienta**. Vos solo definís qué herramientas existen.

---

## Ejemplos de código

- [`01_hello_agent.py`](./examples/01_hello_agent.py) — El agente más simple posible
- [`02_tool_use.py`](./examples/02_tool_use.py) — Múltiples herramientas, loop completo
- [`03_memory.py`](./examples/03_memory.py) — Memoria in-context vs externa

---

## Ejercicio

Construí un agente que:
1. Recibe una pregunta sobre el código en un directorio
2. Puede leer archivos del directorio (`read_file`, `list_files`)
3. Responde solo basándose en lo que leyó (no inventa)
4. Si no encontró la respuesta, dice explícitamente qué buscó

Criterio de éxito: el agente no alucina. Si preguntás "¿dónde está la función `calculate_tax`?" y no existe, debe decir que buscó y no la encontró.

---

Siguiente: [Módulo 2 → Diseño de Workflows](../module-02-workflow-design/README.md)
