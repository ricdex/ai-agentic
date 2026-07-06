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

**Ejemplo mínimo — un tool call completo:**

```python
import anthropic

client = anthropic.Anthropic()

# 1. Definís la herramienta
tools = [{
    "name": "read_file",
    "description": "Lee el contenido de un archivo",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta del archivo"}
        },
        "required": ["path"]
    }
}]

messages = [{"role": "user", "content": "¿Qué hace la función main en src/app.py?"}]

# 2. Loop hasta que el agente termine
while True:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=tools,
        messages=messages
    )

    # 3. Si terminó, imprimís la respuesta
    if response.stop_reason == "end_turn":
        print(response.content[0].text)
        break

    # 4. Si llamó una herramienta, ejecutarla y continuar
    if response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "read_file":
                    result = open(block.input["path"]).read()
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

        messages.append({"role": "user", "content": tool_results})
```

Este loop es la base de todo agente. El módulo 0 lo construye en detalle; acá lo importante es entender la estructura: **el agente itera hasta que `stop_reason == "end_turn"`**.

---

## 1.6 Criterio de terminación: la parte que más falla

Todo agente necesita saber cuándo parar. Hay dos tipos de criterio:

**Criterio por herramienta** (el agente llama una herramienta especial cuando terminó):
```python
DONE_TOOL = {
    "name": "task_complete",
    "description": "Llamá esto cuando hayas completado la tarea",
    "input_schema": {
        "type": "object",
        "properties": {
            "result": {"type": "string"},
            "success": {"type": "boolean"}
        },
        "required": ["result", "success"]
    }
}
```

**Criterio por condición externa** (vos verificás si el objetivo se cumplió):
```python
# El agente escribe código → vos corrés los tests → si pasan, terminaste
while not tests_pass():
    response = agent.iterate()
    if retries > MAX_RETRIES:
        raise AgentStuck("El agente no pudo resolver el problema")
```

**Siempre definí un `max_iterations`**. Un agente sin límite puede loopear indefinidamente gastando tokens.

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Hello Agent](./EXAMPLES.md#ejemplo-1--hello-agent-react-loop-mínimo) | Loop ReAct mínimo, exploración de directorio, no alucina |
| [02 — Tool use con completion tool](./EXAMPLES.md#ejemplo-2--tool-use-con-criterio-de-terminación-explícito) | Patrón `task_complete`, output estructurado con confianza y fuentes |
| [03 — Memoria in-context vs SQLite](./EXAMPLES.md#ejemplo-3--memoria-in-context-vs-externa) | La memoria in-context muere con el proceso; SQLite persiste entre sesiones |

---

## Ejercicio

Construí un agente que:
1. Recibe una pregunta sobre el código en un directorio
2. Puede leer archivos del directorio (`read_file`, `list_files`)
3. Responde solo basándose en lo que leyó (no inventa)
4. Si no encontró la respuesta, dice explícitamente qué buscó
5. Tiene un límite de 5 iteraciones (tool calls)

Criterio de éxito: el agente no alucina. Si preguntás "¿dónde está la función `calculate_tax`?" y no existe, debe decir que buscó y no la encontró — no inventar una respuesta.

**Pista:** el criterio de "no inventar" se implementa en el system prompt, no en el código. El agente necesita instrucciones explícitas de que si no encuentra la información, lo diga.

---

Siguiente: [Módulo 2 → Diseño de Workflows](../module-02-workflow-design/README.md)
