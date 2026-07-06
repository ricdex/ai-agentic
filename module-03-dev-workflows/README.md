# Módulo 3 — Agentic Development Workflows

> "El agente que más valor genera no es el que escribe mejor código — es el que cierra el loop desde el issue hasta el PR sin intervención humana."

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
    model="claude-sonnet-4-6",
    system="[2000 tokens de contexto del repo]",  # se procesa 5 veces
    messages=[...]
)

# Con caching: solo la primera vez cuesta $X
response = client.messages.create(
    model="claude-sonnet-4-6",
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

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Issue solver](./EXAMPLES.md#ejemplo-1--issue-solver-de-github-issue-a-código) | Agente explora repo, encuentra bug, escribe fix, verifica con tests |
| [02 — Prompt caching comparison](./EXAMPLES.md#ejemplo-2--prompt-caching-costo-con-y-sin-caché) | 72% de ahorro en costo con `cache_control`, mismo resultado |
| [03 — CI/CD agéntico](./EXAMPLES.md#ejemplo-3--cicd-agéntico-fix-automático-cuando-falla-el-pipeline) | GitHub Actions workflow que abre PR automático cuando CI falla |

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
