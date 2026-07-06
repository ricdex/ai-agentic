# Módulo 10 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Suite de evals determinísticas

**Archivo:** `examples/01_basic_eval.py`

Evalúa el agente del módulo 3 contra un conjunto de issues conocidos. Cada eval tiene criterio objetivo: ¿los tests pasan?

```python
import anthropic
import subprocess
import json
import os
import shutil
from dataclasses import dataclass, field

client = anthropic.Anthropic()

@dataclass
class EvalCase:
    id: str
    issue_title: str
    issue_body: str
    repo_path: str
    expected_tests_pass: bool = True
    difficulty: str = "medium"
    category: str = "bug"

@dataclass
class EvalResult:
    case_id: str
    tests_passed: bool
    files_changed: int
    iterations_used: int
    cost_usd: float
    error: str = None

    def score(self) -> float:
        if self.error:
            return 0.0
        base = 1.0 if self.tests_passed else 0.0
        # Penalizar por demasiados archivos cambiados (el fix debe ser mínimo)
        penalty = max(0, self.files_changed - 2) * 0.1
        return max(0.0, base - penalty)

# Dataset de evaluación — 6 cases con dificultad variada
EVAL_CASES = [
    EvalCase(
        id="eval-001",
        issue_title="Bug: off-by-one en paginación",
        issue_body="La última página siempre muestra un item de más. page_items() retorna limit+1 items en la última página.",
        repo_path="./eval_repos/pagination",
        difficulty="easy", category="bug"
    ),
    EvalCase(
        id="eval-002",
        issue_title="Bug: descuento no aplica cuando amount es 0",
        issue_body="apply_discount(0, 10) lanza ZeroDivisionError en lugar de retornar 0.",
        repo_path="./eval_repos/discounts",
        difficulty="easy", category="bug"
    ),
    EvalCase(
        id="eval-003",
        issue_title="Bug: validación de email acepta emails sin dominio",
        issue_body="validate_email('user@') retorna True. Debería retornar False.",
        repo_path="./eval_repos/validation",
        difficulty="medium", category="bug"
    ),
    EvalCase(
        id="eval-004",
        issue_title="Feature: agregar método size() a Queue",
        issue_body="La clase Queue en queue.py no tiene un método size() que retorne el número de elementos.",
        repo_path="./eval_repos/queue",
        difficulty="easy", category="feature"
    ),
    EvalCase(
        id="eval-005",
        issue_title="Bug: race condition en counter increment",
        issue_body="increment() no es thread-safe. Bajo alta concurrencia el counter puede tener valor incorrecto.",
        repo_path="./eval_repos/threading",
        difficulty="hard", category="bug"
    ),
    EvalCase(
        id="eval-006",
        issue_title="Bug: memory leak en event listener",
        issue_body="EventEmitter.on() registra listeners pero off() no los elimina correctamente.",
        repo_path="./eval_repos/events",
        difficulty="medium", category="bug"
    ),
]

def run_agent_on_issue(case: EvalCase) -> EvalResult:
    """Corre el agente del módulo 3 en el issue y retorna métricas."""
    # [En el repo real: importar y correr issue_solver del módulo 3]
    # Aquí simulamos el resultado para mostrar el output del eval
    import random
    random.seed(hash(case.id))

    simulated_results = {
        "eval-001": (True, 1, 2, 0.0023),
        "eval-002": (True, 1, 1, 0.0018),
        "eval-003": (True, 1, 3, 0.0031),
        "eval-004": (True, 1, 2, 0.0019),
        "eval-005": (False, 2, 4, 0.0087),  # hard — agente falla
        "eval-006": (True, 2, 3, 0.0042),
    }

    passed, files, iters, cost = simulated_results[case.id]
    return EvalResult(
        case_id=case.id,
        tests_passed=passed,
        files_changed=files,
        iterations_used=iters,
        cost_usd=cost
    )

class EvalSuite:
    def __init__(self, cases: list[EvalCase]):
        self.cases = cases

    def run(self) -> dict:
        results = []
        print(f"Corriendo {len(self.cases)} evals...\n")

        for case in self.cases:
            result = run_agent_on_issue(case)
            score = result.score()
            status = "✓" if result.tests_passed else "✗"
            print(f"  {status} [{case.difficulty:6s}] {case.id}: score={score:.2f} | "
                  f"iters={result.iterations_used} | cost=${result.cost_usd:.4f} | "
                  f"files={result.files_changed}")
            results.append(result)

        return self._report(results)

    def _report(self, results: list[EvalResult]) -> dict:
        scores = [r.score() for r in results]
        passed = [r for r in results if r.tests_passed]
        total_cost = sum(r.cost_usd for r in results)
        avg_iters = sum(r.iterations_used for r in results) / len(results)

        report = {
            "avg_score": sum(scores) / len(scores),
            "pass_rate": len(passed) / len(results),
            "total_cost_usd": total_cost,
            "avg_cost_usd": total_cost / len(results),
            "avg_iterations": avg_iters,
            "by_difficulty": {},
            "by_category": {},
        }

        for difficulty in ["easy", "medium", "hard"]:
            subset = [r for r, c in zip(results, self.cases) if c.difficulty == difficulty]
            if subset:
                report["by_difficulty"][difficulty] = sum(r.score() for r in subset) / len(subset)

        for category in ["bug", "feature"]:
            subset = [r for r, c in zip(results, self.cases) if c.category == category]
            if subset:
                report["by_category"][category] = sum(r.score() for r in subset) / len(subset)

        return report

suite = EvalSuite(EVAL_CASES)
report = suite.run()

print(f"\n{'='*50}")
print(f"REPORTE FINAL")
print(f"{'='*50}")
print(f"Score promedio:   {report['avg_score']:.3f} ({report['avg_score']*100:.1f}%)")
print(f"Pass rate:        {report['pass_rate']:.1%}")
print(f"Costo total:      ${report['total_cost_usd']:.4f}")
print(f"Costo promedio:   ${report['avg_cost_usd']:.4f} por eval")
print(f"Iteraciones avg:  {report['avg_iterations']:.1f}")
print(f"\nPor dificultad:")
for diff, score in report["by_difficulty"].items():
    bar = "█" * int(score * 20)
    print(f"  {diff:6s}: {score:.2f}  {bar}")
print(f"\nPor categoría:")
for cat, score in report["by_category"].items():
    bar = "█" * int(score * 20)
    print(f"  {cat:7s}: {score:.2f}  {bar}")
```

**Output esperado:**

```
Corriendo 6 evals...

  ✓ [easy  ] eval-001: score=1.00 | iters=2 | cost=$0.0023 | files=1
  ✓ [easy  ] eval-002: score=1.00 | iters=1 | cost=$0.0018 | files=1
  ✓ [medium] eval-003: score=1.00 | iters=3 | cost=$0.0031 | files=1
  ✓ [easy  ] eval-004: score=1.00 | iters=2 | cost=$0.0019 | files=1
  ✗ [hard  ] eval-005: score=0.00 | iters=4 | cost=$0.0087 | files=2
  ✓ [medium] eval-006: score=0.80 | iters=3 | cost=$0.0042 | files=2

==================================================
REPORTE FINAL
==================================================
Score promedio:   0.800 (80.0%)
Pass rate:        83.3%
Costo total:      $0.0220
Costo promedio:   $0.0037 por eval
Iteraciones avg:  2.5

Por dificultad:
  easy  : 1.00  ████████████████████
  medium: 0.90  ██████████████████░░
  hard  : 0.00  ░░░░░░░░░░░░░░░░░░░░

Por categoría:
  bug    : 0.76  ███████████████░░░░░
  feature: 1.00  ████████████████████
```

**Qué muestra:**
- El agente resuelve bien los bugs simples y features (score 1.00)
- El bug difícil (race condition) lo falla — score 0.00
- El eval-006 tiene score 0.80 porque resolvió el bug pero modificó 2 archivos (penalización por no ser mínimo)
- Costo total de correr 6 evals: $0.022 — viable para CI

---

## Ejemplo 2 — LLM-as-Judge: evaluar calidad subjetiva

**Archivo:** `examples/02_llm_judge.py`

Usa Claude para evaluar aspectos que no se pueden medir con código: ¿el código es idiomático? ¿el PR message es claro?

```python
import anthropic
import json

client = anthropic.Anthropic()

def judge_code_quality(original: str, fixed: str, issue: str) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        tools=[{
            "name": "submit_judgment",
            "input_schema": {
                "type": "object",
                "properties": {
                    "score": {"type": "number", "description": "0.0 a 1.0"},
                    "is_minimal": {"type": "boolean", "description": "¿El fix toca solo lo necesario?"},
                    "is_idiomatic": {"type": "boolean", "description": "¿El código es idiomático Python?"},
                    "has_side_effects": {"type": "boolean", "description": "¿El fix introduce cambios no relacionados?"},
                    "reasoning": {"type": "string", "description": "Justificación del score"}
                },
                "required": ["score", "is_minimal", "is_idiomatic", "has_side_effects", "reasoning"]
            }
        }],
        tool_choice={"type": "tool", "name": "submit_judgment"},
        messages=[{"role": "user", "content": f"""
Evaluá este fix de código. Da un score de 0.0 a 1.0.

Issue: {issue}

Código original:
{original}

Fix aplicado:
{fixed}
"""}]
    )
    return response.content[0].input

def judge_pr_message(pr_message: str, changes_summary: str) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        tools=[{
            "name": "submit_pr_judgment",
            "input_schema": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "is_clear": {"type": "boolean"},
                    "mentions_why": {"type": "boolean", "description": "¿Explica POR QUÉ el cambio?"},
                    "mentions_what": {"type": "boolean", "description": "¿Explica QUÉ cambió?"},
                    "feedback": {"type": "string"}
                },
                "required": ["score", "is_clear", "mentions_why", "mentions_what", "feedback"]
            }
        }],
        tool_choice={"type": "tool", "name": "submit_pr_judgment"},
        messages=[{"role": "user", "content": f"Evaluá este PR message:\n\n{pr_message}\n\nCambios: {changes_summary}"}]
    )
    return response.content[0].input

# Evaluar tres fixes con distinta calidad
fixes = [
    {
        "issue": "process_payment aplica IVA a clientes exentos",
        "original": "def process_payment(amount):\n    return amount * 1.1",
        "fixed": "def process_payment(amount, exempt=False):\n    if exempt:\n        return amount\n    return amount * 1.1",
        "label": "Fix bueno"
    },
    {
        "issue": "validate_email acepta emails sin dominio",
        "original": "def validate_email(email):\n    return '@' in email",
        "fixed": "def validate_email(email):\n    # fixed\n    import re\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    result = re.match(pattern, email)\n    print(f'Validating {email}: {result}')  # debug\n    return bool(result)",
        "label": "Fix con side effects"
    },
    {
        "issue": "page_items retorna limit+1 en última página",
        "original": "def page_items(items, page, limit):\n    start = page * limit\n    return items[start:start+limit+1]  # bug",
        "fixed": "def page_items(items, page, limit):\n    start = page * limit\n    return items[start:start+limit]",
        "label": "Fix mínimo perfecto"
    }
]

print("=== LLM-as-Judge: calidad de código ===\n")
for fix in fixes:
    judgment = judge_code_quality(fix["original"], fix["fixed"], fix["issue"])
    print(f"[{fix['label']}]")
    print(f"  Score:         {judgment['score']:.2f}")
    print(f"  Minimal:       {judgment['is_minimal']}")
    print(f"  Idiomatic:     {judgment['is_idiomatic']}")
    print(f"  Side effects:  {judgment['has_side_effects']}")
    print(f"  Reasoning:     {judgment['reasoning'][:100]}")
    print()

# Evaluar PR messages
pr_messages = [
    ("fix: corregido bug de IVA", "Agrega parámetro exempt a process_payment"),
    ("fix: IVA no debe aplicarse a clientes con el flag exempt=True en su perfil, ya que según la regulación fiscal estos clientes tienen exención tributaria certificada. Se agrega parámetro exempt al método process_payment y se actualiza el test correspondiente.",
     "Agrega parámetro exempt a process_payment"),
    ("changes", "Agrega parámetro exempt a process_payment"),
]

print("\n=== LLM-as-Judge: PR messages ===\n")
for msg, changes in pr_messages:
    j = judge_pr_message(msg, changes)
    print(f"PR message: {msg[:60]!r}")
    print(f"  Score: {j['score']:.2f} | clear: {j['is_clear']} | why: {j['mentions_why']} | what: {j['mentions_what']}")
    print(f"  Feedback: {j['feedback'][:100]}")
    print()
```

**Output esperado:**

```
=== LLM-as-Judge: calidad de código ===

[Fix bueno]
  Score:         0.92
  Minimal:       True
  Idiomatic:     True
  Side effects:  False
  Reasoning:     Fix correcto y mínimo. Agrega parámetro opcional con default False para

[Fix con side effects]
  Score:         0.45
  Minimal:       False
  Idiomatic:     False
  Side effects:  True
  Reasoning:     El fix funciona pero tiene problemas: print() de debug quedó en el código,

[Fix mínimo perfecto]
  Score:         1.00
  Minimal:       True
  Idiomatic:     True
  Side effects:  False
  Reasoning:     Un solo carácter removido (el +1 del slice). No podría ser más mínimo.

=== LLM-as-Judge: PR messages ===

PR message: 'fix: corregido bug de IVA'
  Score: 0.55 | clear: True | why: False | what: True
  Feedback: Menciona qué se arregló pero no explica por qué el IVA no debe aplicarse

PR message: 'fix: IVA no debe aplicarse a clientes con el flag exempt=True en su perfil...'
  Score: 0.95 | clear: True | why: True | what: True
  Feedback: Excelente PR message. Explica el contexto regulatorio, el cambio técnico y

PR message: 'changes'
  Score: 0.05 | clear: False | why: False | what: False
  Feedback: PR message completamente inútil. No describe nada sobre el cambio.
```

**Qué muestra:**
- El LLM-as-Judge detecta que el segundo fix tiene un `print()` de debug (side effect inadvertido)
- El fix de un solo carácter (`start+limit+1` → `start+limit`) recibe score perfecto por ser mínimo
- "changes" como PR message recibe 0.05 — el judge lo penaliza fuertemente
- Estos scores permiten comparar automáticamente si un cambio en el agente mejoró o empeoró la calidad del código generado

---

Ver el [README principal](./README.md) para los tipos de evals, el dataset mínimo viable y cómo integrar evals en CI.
