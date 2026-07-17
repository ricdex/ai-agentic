# Ejemplos — Software Factory

Trace completo de un issue pasando por el factory de punta a punta.

---

## Ejemplo 1 — Issue simple (triage → implement → PR)

**Issue abierto en GitHub:**
```
Title: Bug: divide function crashes on zero division
Body:  The divide() function raises ZeroDivisionError instead of a
       proper ValueError. It should raise ValueError("Cannot divide by zero").
```

### VM1 — Triage (Haiku, ~3s)

```
2026-07-16 10:00:01 [orchestrator] Issue #42: Bug: divide function crashes on zero division
2026-07-16 10:00:04 [orchestrator] Triage → automatable=True, complexity=low, needs_spec=False
2026-07-16 10:00:04 [orchestrator] Task a3f8b2 queued for implementation
```

**Comentario posteado en el issue:**
```markdown
🏭 **Factory** — Implementación iniciada.

**Enfoque:** Add zero check in divide() and raise ValueError
**Complejidad:** low
**Branch:** `factory/a3f8b2/issue-42`

*Task ID: `a3f8b2`*
```

**Label agregado:** `factory:low`

---

### VM2 — Implementación (Sonnet, ~90s)

```
2026-07-16 10:00:05 [implementor] Task a3f8b2 — attempt 1/3

[Tool: list_files(".")]
./calculator.py
./tests/test_calculator.py
./requirements.txt

[Tool: read_file("calculator.py")]
def divide(a: float, b: float) -> float:
    # BUG: no zero division check
    return a / b

[Tool: read_file("tests/test_calculator.py")]
def test_divide():
    assert divide(10, 2) == 5
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(5, 0)

[Tool: write_file("calculator.py")]
→ Added: if b == 0: raise ValueError("Cannot divide by zero")

[Tool: run_tests()]
Tests PASSED ✓

collected 6 items
test_calculator.py::test_add PASSED
test_calculator.py::test_subtract PASSED
test_calculator.py::test_multiply PASSED
test_calculator.py::test_divide PASSED
test_calculator.py::test_percentage FAILED  ← otros bugs aún existen
test_calculator.py::test_average FAILED

[Tool: task_complete]
summary: "Added zero-division check to divide(). Only fixed the reported issue."
files_changed: ["calculator.py"]
```

> Nota: el agente solo arregla lo que el issue describe. Los otros tests que fallan son bugs previos no relacionados con este issue.

**Resultado de tests finales:**
```
PASSED test_divide ✓
(otros tests pasan/fallan igual que antes — no regresiones del fix)
```

**Comentario en el issue:**
```markdown
✅ **Implementación lista.** Enviando a revisión automática.

**Branch:** `factory/a3f8b2/issue-42`
**Tests:** ✓ passing

```
Added zero-division check to divide(). Only fixed the reported issue.
```
```

---

### VM3 — Review (Sonnet, ~20s)

```
2026-07-16 10:02:15 [reviewer] Reviewing task a3f8b2
2026-07-16 10:02:15 [reviewer] Fetching diff: main vs factory/a3f8b2/issue-42
```

**Diff analizado:**
```diff
--- a/calculator.py
+++ b/calculator.py
@@ -10,5 +10,7 @@ def multiply(a: float, b: float) -> float:
 
 def divide(a: float, b: float) -> float:
-    # BUG: no zero division check
-    return a / b
+    if b == 0:
+        raise ValueError("Cannot divide by zero")
+    return a / b
```

**Resultado del review agent:**
```json
{
  "approved": true,
  "issues": [],
  "suggestions": ["Consider adding type hints for the return value of the error path"],
  "summary": "Clean, minimal fix. Correctly raises ValueError as specified. Tests pass and no regressions introduced."
}
```

---

### PR abierto automáticamente

```markdown
## 🏭 Software Factory — PR Automático

**Closes #42**

### Qué se hizo
Added zero-division check to divide(). Only fixed the reported issue.

### Revisión de código
Clean, minimal fix. Correctly raises ValueError as specified.
Tests pass and no regressions introduced.

**Issues bloqueantes:** Ninguno

**Sugerencias:**
- 💡 Consider adding type hints for the return value of the error path

### Tests
```
collected 6 items
test_divide PASSED ✓
...
```

---
*Auto-generado por el Software Factory · Solo revisar y hacer merge*
```

**Comentario final en el issue:**
```markdown
## ✅ Factory completado

**PR listo para review:** https://github.com/user/factory-demo/pull/1

Clean, minimal fix. Correctly raises ValueError as specified.

Tests pasan ✓ — solo revisar y mergear.
```

**Tiempo total del factory: ~2 minutos.**
**Intervención humana: 0 segundos** (hasta el momento del merge).

---

## Ejemplo 2 — Issue complejo con spec

**Issue abierto:**
```
Title: Add support for weighted average calculation
Body:  We need a weighted_average(values, weights) function.
       Not sure if weights should be normalized automatically.
```

### Triage → spec needed

```
2026-07-16 11:00:01 [orchestrator] Triage → automatable=True, complexity=medium, needs_spec=True
```

**Spec generado y comentado:**
```markdown
## 🏭 Factory — Spec generado

**Problema**
La función `weighted_average` no existe. Los requisitos son ambiguos
respecto a si los pesos deben normalizarse automáticamente.

**Solución propuesta**
Implementar `weighted_average(values: list[float], weights: list[float]) -> float`
que normaliza los pesos automáticamente (suma a 1.0).

**Acceptance criteria**
- [ ] `weighted_average([1, 2, 3], [1, 1, 1])` → `2.0` (pesos iguales = promedio simple)
- [ ] `weighted_average([10, 20], [3, 1])` → `12.5` (75% de 10 + 25% de 20)
- [ ] `weighted_average([], [])` → `ValueError`
- [ ] `weighted_average([1], [])` → `ValueError` (len mismatch)
- [ ] Tests cubren todos los casos anteriores

**Out of scope**
- Pesos negativos (no se manejan en esta iteración)
- Normalización opcional como parámetro

---
Responde con `/factory approve` para iniciar implementación,
o `/factory reject <feedback>` para pedir cambios.

*Task ID: `d9e2c1`*
```

**Respuesta del dev:** `/factory approve`

```
2026-07-16 11:05:30 [spec-watcher] Task d9e2c1 approved → queuing for implementation
```

→ El factory continúa igual que el ejemplo 1: implement → review → PR.

---

## Ejemplo 3 — Tests fallan → retry automático

**Issue:** bug en `average()` que crashea con lista vacía.

```
2026-07-16 12:00:01 [implementor] Task f1a4d7 — attempt 1/3

[Tool: write_file("calculator.py")]
→ Intento 1: agente agrega `if not numbers: return 0`  ← incorrecto

[Tool: run_tests()]
Tests FAILED ✗
FAILED test_average - AssertionError: Expected ValueError, got 0
```

```
2026-07-16 12:01:45 [implementor] Tests failed — retry 1/3
2026-07-16 12:01:45 [implementor] Task f1a4d7 — attempt 2/3

[Tool: read_file("tests/test_calculator.py")]
→ El agente lee el test: expects ValueError("Cannot average empty list")

[Tool: write_file("calculator.py")]
→ Intento 2: `if not numbers: raise ValueError("Cannot average empty list")`

[Tool: run_tests()]
Tests PASSED ✓
```

```
2026-07-16 12:03:10 [implementor] Task f1a4d7 → review queue
```

**Resuelto en el segundo intento.** Modelo usado: Sonnet (no escaló a Opus porque solo tomó 2 intentos).

---

## Comparación de costo: factory vs dev manual

| Tarea | Tiempo humano | Costo factory | Tokens |
|---|---|---|---|
| Issue simple (bug fix) | ~20 min | ~$0.08 | ~25k tokens (Sonnet) |
| Issue complejo (con spec) | ~2h | ~$0.35 | ~100k tokens |
| Code review + PR | ~15 min | ~$0.04 | ~12k tokens (Sonnet) |
| Triage de 10 issues | ~30 min | ~$0.02 | ~8k tokens (Haiku) |

**Conclusión:** el factory cuesta ~$0.12/issue promedio. A $100/h de costo de dev,
rompe even en issues que tomarían más de 4 segundos de trabajo humano.
El valor real es la escala: un solo dev puede tener 10 issues siendo resueltos en paralelo
mientras trabaja en el problema más difícil del sprint.
