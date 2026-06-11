# Módulo 10 — Evals: Medir para Mejorar

> "Sin evals, mejorar un agente es como optimizar a ciegas. Cambiás el prompt, algo mejora, algo empeora, no sabés qué."

---

## 10.1 Por qué evals son diferentes en agentes

En sistemas clásicos, las métricas son claras: latencia, error rate, throughput.
En sistemas AI, la calidad del output es subjetiva y multidimensional:

```
¿El agente resolvió el issue?
  → ¿Los tests pasan? ← fácil de medir
  → ¿El código es idiomático? ← difícil de medir
  → ¿Tocó solo lo necesario? ← difícil de medir
  → ¿El PR message es claro? ← muy difícil de medir
```

Las evals dan respuestas numéricas a estas preguntas. Sin ellas, sabés que algo funcionó o falló pero no **por qué** ni **qué tan bien**.

---

## 10.2 Tipos de evals

### 1. Evals determinísticas (las más confiables)
Resultados objetivos, sin ambigüedad:

```python
def eval_tests_pass(agent_output: AgentOutput) -> float:
    return 1.0 if agent_output.tests_passed else 0.0

def eval_no_regression(agent_output: AgentOutput) -> float:
    return 1.0 if agent_output.regression_tests_passed else 0.0

def eval_minimal_change(agent_output: AgentOutput) -> float:
    # Penalizar cambios excesivos de archivos
    if agent_output.files_changed > 3:
        return max(0.0, 1.0 - (agent_output.files_changed - 3) * 0.2)
    return 1.0
```

### 2. LLM-as-Judge (para aspectos subjetivos)
Usar otro Claude para evaluar la calidad:

```python
def eval_code_quality(original_code: str, fixed_code: str) -> float:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        messages=[{
            "role": "user",
            "content": f"""
            Evaluá la calidad del fix en una escala de 0.0 a 1.0.
            Criterios: ¿Es idiomático? ¿Mínimo? ¿Sin side effects innecesarios?

            Original: {original_code}
            Fixed: {fixed_code}

            Respondé SOLO con el número decimal (ej: 0.85).
            """
        }]
    )
    return float(response.content[0].text.strip())
```

### 3. Human evals (ground truth)
Evaluación humana sobre un conjunto pequeño de casos de referencia. Más caro, más preciso.

---

## 10.3 Dataset de evals

Un dataset de evals es una colección de casos de prueba con:
- **Input**: la tarea o issue
- **Expected output** (opcional): la solución correcta conocida
- **Evaluation criteria**: cómo juzgar el output del agente

```python
@dataclass
class EvalCase:
    id: str
    issue_title: str
    issue_body: str
    repo_path: str

    # Ground truth (si existe)
    expected_fix_path: str | None = None
    expected_tests_pass: bool = True

    # Metadata
    difficulty: str = "medium"  # easy | medium | hard
    category: str = "bug"
```

**Cuántos casos necesitás:**
- Mínimo viable: 20 casos
- Bueno: 50-100 casos
- Ideal: 200+ con balance de categorías

---

## 10.4 Eval suite completa

```python
class AgentEvalSuite:
    def __init__(self, cases: list[EvalCase]):
        self.cases = cases
        self.results = []

    def run(self, agent_fn) -> EvalReport:
        for case in self.cases:
            output = agent_fn(case)
            scores = {
                "tests_pass":    eval_tests_pass(output),
                "no_regression": eval_no_regression(output),
                "minimal_change": eval_minimal_change(output),
                "cost_usd":      output.cost_usd,
                "iterations":    output.iterations
            }
            self.results.append(EvalResult(case=case, output=output, scores=scores))

        return EvalReport(self.results)

    def compare(self, baseline_report: EvalReport, new_report: EvalReport):
        """Muestra delta entre baseline y nueva versión."""
        for metric in ["tests_pass", "no_regression", "minimal_change"]:
            delta = new_report.avg(metric) - baseline_report.avg(metric)
            direction = "↑" if delta > 0 else "↓"
            print(f"  {metric}: {direction} {abs(delta):.3f}")
```

---

## 10.5 Evals en CI

```yaml
# .github/workflows/evals.yml
on:
  pull_request:
    paths:
      - "agent/**"
      - "prompts/**"

jobs:
  evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run eval suite
        run: python evals/run_suite.py --threshold 0.75
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - name: Post results to PR
        run: python evals/comment_pr.py
```

**Threshold práctico:** el CI falla si el score promedio cae por debajo de 0.75 (75% de los casos exitosos).

---

## 10.6 Regression evals: proteger lo que funciona

```python
# Antes de mergear cualquier cambio al agente:
# 1. Correr el suite completo
# 2. Comparar con el baseline guardado
# 3. Fallar si alguna métrica crítica bajó más de 0.05 (5%)

REGRESSIONS_ALLOWED = {
    "tests_pass": 0.0,      # cero tolerancia a regresar en esto
    "no_regression": 0.0,
    "minimal_change": 0.05  # puede bajar un poco
}
```

---

## Ejemplos de código

- [`01_basic_eval.py`](./examples/01_basic_eval.py) — Suite de evals determinísticas para el agente del módulo 3
- [`02_llm_judge.py`](./examples/02_llm_judge.py) — LLM-as-Judge para evaluar calidad de código y claridad de PR

---

## Ejercicio

Construí un dataset de evals para el proyecto Autopilot:

1. Creá 10 issues de prueba en 3 categorías: bug simple, bug con efectos secundarios, feature pequeña
2. Para cada uno, definí el criterio de éxito (¿qué tests deben pasar?)
3. Corré el agente en los 10 casos y calculá el score inicial (tu baseline)
4. Hacé un cambio al system prompt y correlo de nuevo
5. ¿Mejoró o empeoró? ¿En qué categorías?

Esto es exactamente cómo los equipos que construyen Devin y similares trabajan.

---

Siguiente: [Módulo 11 → Deployment](../module-11-deployment/README.md)
