# Módulo 3 — Agentic Development Workflows

> "El agente que más valor genera no es el que escribe más código — es el que convierte una Feature Spec aprobada en un PR verificable, con gates humanos donde el riesgo lo exige."

---

## Paso a paso

1. Usá una Feature Spec aprobada, no una issue ambigua, como entrada del workflow.
2. Ejecutá `examples/issue_solver.py` en un repositorio de demo y observá exploración, tests, retry y diff.
3. Compará el cambio con los criterios de aceptación: debe tocar el mínimo de archivos posible.
4. Crea un PR solo cuando tests y criterios de la spec coincidan; si fallan, capturá el diagnóstico como evidencia.

**Complejidad a evitar:** dar acceso de escritura o credenciales amplias antes de tener sandbox, tests y límite de reintentos.

---

## 3.1 El workflow que las empresas evalúan

Cuando en SF dicen "production AI agentic workflows", esto es lo que miran:

```
GitHub Issue ──→ Análisis ──→ Plan ──→ Código ──→ Tests ──→ PR
     ↑                                              │
     │                                              ↓
     └──────────────── si tests fallan ─────── Análisis de fallo
                                                    │
                                                    ↓
                                                 Iteración
                                              (máx 3 veces)
```

El ingeniero no toca el código. El agente lo hace. El ingeniero revisa el PR.

**Ejemplos reales:**
- [GitHub Copilot Workspace](https://githubnext.com/projects/copilot-workspace) — plan → código → PR desde un issue
- [Devin](https://www.cognition.ai/) — agente de ingeniería autónomo
- [SWE-bench](https://www.swebench.com/) — benchmark de agentes que resuelven issues reales de repos open-source

---

## 3.2 El problema del contexto: cómo un agente "entiende" un repo

Un humano nuevo en un proyecto tarda horas leyendo código. Un agente tiene tokens limitados. La estrategia:

**1. Exploración dirigida (no leer todo)**
```
Agente: "Necesito encontrar dónde se procesa el pago"
→ search_code("payment", "checkout", "stripe")
→ read_file("src/payments/processor.py")
→ read_file("src/payments/models.py")
# NO leer todo el repo
```

**2. Mapa del repo primero**
```
→ list_files("src/")
→ leer README
→ leer estructura de directorios
→ buscar el archivo más relevante para el issue
```

**3. Tests como especificación**
Los tests existentes te dicen qué debe hacer el código. El agente los lee para entender el contrato.

---

## 3.3 Herramientas que todo dev agent necesita

| Herramienta | Por qué | Qué retorna |
|---|---|---|
| `read_file(path)` | Ver código específico | Contenido del archivo |
| `write_file(path, content)` | Modificar código | Éxito/error |
| `search_code(pattern, dir)` | Encontrar símbolos | Lista de matches con línea |
| `run_tests(path)` | Verificar que funciona | Output de pytest/jest/go test |
| `list_files(dir)` | Mapear estructura | Lista de archivos |
| `git_diff()` | Ver qué cambió | Diff del working tree |

Lo que NO debe tener:
- `execute_arbitrary_shell_command` — demasiado amplio, inseguro
- `deploy_to_production` — irreversible, requiere humano

---

## 3.4 Estrategia de selección de modelo

```
Issue recibido
    │
    ▼
¿Es un bug simple con stack trace claro?
    │
    ├─ SÍ → Haiku para análisis rápido
    │
    └─ NO → ¿Requiere entender arquitectura compleja?
                │
                ├─ SÍ → Sonnet (o Opus para bugs muy difíciles)
                │
                └─ NO → Sonnet estándar
```

**Regla del 80/20:** El 80% de los issues se resuelven con Sonnet. Usá Haiku para clasificación y Opus solo si Sonnet falla después de 2 intentos.

---

## 3.5 Prompt caching: reducir costos en 60-90%

En un dev agent, el system prompt y el contexto del repo son estáticos entre iteraciones. Cachearlos ahorra dinero.

```python
# Sin caching: cada iteración cuesta $X
response = client.messages.create(
    model="claude-sonnet-5",
    system="[2000 tokens de contexto del repo]",  # se procesa 5 veces
    messages=[...]
)

# Con caching: solo la primera vez cuesta $X
response = client.messages.create(
    model="claude-sonnet-5",
    system=[
        {
            "type": "text",
            "text": "[2000 tokens de contexto del repo]",
            "cache_control": {"type": "ephemeral"}  # ← magia
        }
    ],
    messages=[...]
)
```

**Ahorro típico:** 60-90% en llamadas subsecuentes. Fundamental en producción.

**Referencia:** [Anthropic Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)

---

## 3.6 CI/CD agéntico

El mismo principio aplicado a pipelines:

```yaml
# .github/workflows/ai-fix.yml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    
jobs:
  auto-fix:
    if: github.event.workflow_run.conclusion == 'failure'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run AI fix agent
        run: python agents/ci_fixer.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          FAILED_RUN_ID: ${{ github.event.workflow_run.id }}
```

El agente analiza el log de CI fallido, identifica el problema, escribe el fix, y abre un PR.

---

## 3.7 Context engineering: el contexto es un recurso finito

Un agente que resuelve un issue real hace decenas de llamadas a herramientas. Cada `read_file`, cada log de tests y cada diff se queda en el historial y **se reenvía en cada turno**. El modelo no falla porque "no entiende", sino porque el contexto se llenó de ruido:

- **Costo y latencia:** el turno 40 paga todos los tokens de los 39 anteriores (el prompt caching lo atenúa, pero no lo elimina).
- **Atención degradada:** los modelos usan peor la información enterrada en el medio de un contexto largo que la que está al principio o al final (*lost in the middle*).
- **Límite duro:** al llegar a la ventana, el request falla.

*Prompt engineering* es elegir las palabras de una instrucción. *Context engineering* es decidir **qué entra en la ventana, en qué orden y cuándo sale**. En agentes largos, lo segundo pesa más.

### Las cuatro palancas, de la más barata a la más cara

| # | Palanca | Cuándo | Dónde se aplica |
|---|---|---|---|
| 1 | **Recortar lo que entra** — cabeza + cola de logs, `grep` en vez de `read_file` completo, paginar | Siempre | En el tool, antes de devolver el `tool_result` |
| 2 | **Ordenar para la atención** — lo más relevante al principio y al final | Al armar contexto con muchos documentos (RAG, archivos) | Al construir el prompt |
| 3 | **Limpiar tool results viejos** (*context editing*) | El historial crece con resultados que ya no se van a releer | Server-side: `clear_tool_uses_20250919` |
| 4 | **Compactar o hacer handoff** | Cerca del límite de la ventana | Server-side: compaction · o cortar y arrancar una sesión nueva con estado |

```python
# Palanca 3: el API vacía los tool results viejos antes de que el modelo los vea
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16_000,
    betas=["context-management-2025-06-27"],
    context_management={"edits": [{"type": "clear_tool_uses_20250919"}]},
    tools=tools,
    messages=messages,
)

# Palanca 4: compaction — el API resume el historial temprano
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16_000,
    betas=["compact-2026-01-12"],
    context_management={"edits": [{"type": "compact_20260112"}]},
    messages=messages,
)
messages.append({"role": "assistant", "content": response.content})  # content completo, no solo el texto
```

**No edites el historial a mano.** Borrar o reescribir mensajes viejos de tu lista `messages` invalida el prompt caching desde ese punto y, en los modelos con *preserved thinking* (Opus 5.5, Fable 5.1), invalida los bloques de thinking posteriores. Tratá el historial como append-only: recortá **antes** de agregar (palanca 1) y dejá que el servidor limpie o compacte (palancas 3 y 4). El context editing acepta umbrales (cuándo disparar, cuántos tool uses conservar); ver la [documentación de context management](https://platform.claude.com/docs/en/build-with-claude/context-editing).

### Handoff: cuando conviene empezar de cero

La compaction resume, y un resumen libre pierde detalles. Para tareas de horas, el patrón más robusto es que el agente mantenga un **estado explícito** (objetivo, hecho, pendiente, decisiones, archivos tocados) y que, al acercarse al límite, arranque una sesión nueva cuyo primer mensaje sea ese estado. Es el mismo principio del [Paso 06 — Agent Handoff](../module-00-developer-workflow/README.md#paso-06--agent-handoff) del módulo 0, pero automático.

```
uso de contexto:   0% ──── 40% ──── 70% ──── 90% ── 100%
acción:              ok   │ limpiar │ compactar │ handoff
```

Los umbrales son configuración, no constantes: dependen del modelo, del tamaño típico de tus tool outputs y de cuánto cuesta perder detalle.

> **Regla práctica:** si tu agente necesita compaction en casi todas las tareas, el problema suele estar en la palanca 1 (tools que devuelven demasiado), no en la 4.

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Issue solver](./EXAMPLES.md#ejemplo-1--issue-solver-de-github-issue-a-código) | Agente explora repo, encuentra bug, escribe fix, verifica con tests |
| [02 — Prompt caching comparison](./EXAMPLES.md#ejemplo-2--prompt-caching-costo-con-y-sin-caché) | 72% de ahorro en costo con `cache_control`, mismo resultado |
| [03 — CI/CD agéntico](./EXAMPLES.md#ejemplo-3--cicd-agéntico-fix-automático-cuando-falla-el-pipeline) | GitHub Actions workflow que abre PR automático cuando CI falla |
| [04 — Context engineering](./EXAMPLES.md#ejemplo-4--context-engineering-recortar-ordenar-limpiar-compactar) | Log de 9.7k tokens recortado a 500 sin perder el error; política ok → limpiar → compactar → handoff |

---

## Ejercicio

Tomá un repo tuyo (o cualquier repo open-source pequeño). Buscá un issue "good first issue". Sin tocar el código vos mismo:

1. Pasale el issue al agente del ejemplo
2. Observá cómo explora el repo
3. Verificá si el fix que genera es correcto
4. Identifica dónde falló o dónde acertó

Tomá notas: ¿qué información le faltó al agente? ¿Qué herramientas adicionales necesitaría?

---

Siguiente: [Módulo 4 → Runtime Adaptability](../module-04-runtime-adaptability/README.md)
