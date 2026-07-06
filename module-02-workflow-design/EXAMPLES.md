# Módulo 2 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Feedback loop: agente que itera hasta que los tests pasan

**Archivo:** `examples/feedback_loop.py`

El agente recibe una spec, escribe código, corre los tests, y si fallan analiza el error e itera. Máximo 5 intentos antes de escalar.

```python
import anthropic
import subprocess
import tempfile
import os

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "write_file",
        "description": "Escribe contenido en un archivo",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "run_tests",
        "description": "Corre pytest y retorna el resultado",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_file": {"type": "string", "description": "Ruta del archivo de tests"}
            },
            "required": ["test_file"]
        }
    }
]

def write_file(path: str, content: str) -> str:
    with open(path, "w") as f:
        f.write(content)
    return f"Archivo {path} escrito ({len(content)} chars)"

def run_tests(test_file: str) -> str:
    result = subprocess.run(
        ["python", "-m", "pytest", test_file, "-v", "--tb=short"],
        capture_output=True, text=True
    )
    return result.stdout + result.stderr

def execute_tool(name, input):
    if name == "write_file":
        return write_file(input["path"], input["content"])
    elif name == "run_tests":
        return run_tests(input["test_file"])

SPEC = """
Implementá una clase `Stack` en `stack.py` que pase estos tests en `test_stack.py`:

```python
from stack import Stack

def test_empty_stack():
    s = Stack()
    assert s.is_empty()
    assert s.size() == 0

def test_push_and_pop():
    s = Stack()
    s.push(1)
    s.push(2)
    assert s.pop() == 2
    assert s.pop() == 1

def test_pop_empty_raises():
    s = Stack()
    try:
        s.pop()
        assert False, "Debería haber lanzado IndexError"
    except IndexError:
        pass

def test_peek():
    s = Stack()
    s.push("a")
    assert s.peek() == "a"
    assert s.size() == 1  # peek no elimina
```
"""

SYSTEM = """Sos un developer implementando código para pasar tests.
Proceso:
1. Escribí el archivo de implementación
2. Escribí el archivo de tests (copiá los tests de la spec)
3. Corré los tests
4. Si fallan, analizá el error y corregí la implementación
5. Repetí hasta que todos pasen
Nunca reportes éxito sin haber corrido los tests y verificado que pasan."""

messages = [{"role": "user", "content": SPEC}]
MAX_ITERATIONS = 5

print("=== Feedback Loop Agent ===\n")

for iteration in range(1, MAX_ITERATIONS + 1):
    print(f"--- Iteración {iteration} ---")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM,
        tools=TOOLS,
        messages=messages
    )

    if response.stop_reason == "end_turn":
        print(f"\nAgente finalizó:\n{response.content[0].text}")
        break

    if response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  → {block.name}({list(block.input.keys())})")
                result = execute_tool(block.name, block.input)
                # Mostrar resultado de tests
                if block.name == "run_tests":
                    lines = result.split('\n')
                    summary = [l for l in lines if 'passed' in l or 'failed' in l or 'error' in l]
                    print(f"    {summary[-1] if summary else 'sin resultado'}")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": results})
```

**Output esperado:**

```
=== Feedback Loop Agent ===

--- Iteración 1 ---
  → write_file(['path', 'content'])
  → write_file(['path', 'content'])
  → run_tests(['test_file'])
    1 passed, 3 failed in 0.12s

--- Iteración 2 ---
  → write_file(['path', 'content'])
  → run_tests(['test_file'])
    3 passed, 1 failed in 0.09s

--- Iteración 3 ---
  → write_file(['path', 'content'])
  → run_tests(['test_file'])
    4 passed in 0.08s

Agente finalizó:
Implementé la clase `Stack` en `stack.py`. Los 4 tests pasan:
- test_empty_stack ✓
- test_push_and_pop ✓
- test_pop_empty_raises ✓
- test_peek ✓

El error inicial fue que `pop()` en stack vacío retornaba `None` en lugar de lanzar `IndexError`.
Lo corregí en la iteración 2. El test de `peek` fallaba porque la primera versión consumía el elemento.
```

**Qué muestra:**
- Iteración 1: primera versión del código — parcialmente correcta (1/4 tests)
- Iteración 2: corrige los bugs más evidentes (3/4 tests)
- Iteración 3: corrige el último bug (4/4 tests)
- El agente nunca declara éxito sin correr los tests — el criterio de éxito es objetivo

---

## Ejemplo 2 — Multi-agente: orquestador + ejecutores especializados

**Archivo:** `examples/multi_agent.py`

Un orquestador analiza el issue y delega a dos ejecutores independientes: uno planifica los archivos a cambiar, otro escribe el código. El orquestador consolida.

```python
import anthropic
import json

client = anthropic.Anthropic()

# ── Ejecutor A: Planificador ─────────────────────────────────────

def agent_planner(issue: str, codebase_map: str) -> dict:
    """Analiza el issue y decide qué archivos tocar."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system="""Analizá el issue y el mapa del codebase.
Retorná JSON con: {"files_to_change": [...], "files_to_create": [...], "approach": "..."}
Solo JSON, sin texto adicional.""",
        messages=[{"role": "user", "content": f"Issue: {issue}\n\nCódigo:\n{codebase_map}"}]
    )
    return json.loads(response.content[0].text)

# ── Ejecutor B: Developer ────────────────────────────────────────

def agent_developer(issue: str, plan: dict, file_content: str) -> str:
    """Escribe el código para implementar el cambio."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system="Implementá el cambio según el plan. Retorná SOLO el código Python del archivo modificado.",
        messages=[{"role": "user", "content": f"""
Issue: {issue}

Plan: {json.dumps(plan, indent=2)}

Contenido actual del archivo:
{file_content}
"""}]
    )
    return response.content[0].text

# ── Orquestador ──────────────────────────────────────────────────

def orchestrate(issue: str) -> dict:
    print("[Orquestador] Analizando issue...")

    # Mapa del codebase (en prod: exploración real del repo)
    codebase_map = """
src/
  orders.py     — Order, OrderLine, OrderStatus
  payments.py   — PaymentProcessor, PaymentResult
  discounts.py  — DiscountEngine (FALTA: no implementado)
tests/
  test_orders.py
"""

    # Paso 1: planificar (ejecutor A)
    print("[Planificador] Determinando archivos afectados...")
    plan = agent_planner(issue, codebase_map)
    print(f"  Plan: {plan['approach']}")
    print(f"  Archivos a modificar: {plan.get('files_to_change', [])}")
    print(f"  Archivos a crear: {plan.get('files_to_create', [])}")

    # Paso 2: implementar (ejecutor B, en paralelo si hay múltiples archivos)
    results = {}
    for file_path in plan.get("files_to_change", []) + plan.get("files_to_create", []):
        print(f"\n[Developer] Implementando {file_path}...")
        try:
            current_content = open(file_path).read()
        except FileNotFoundError:
            current_content = "# Archivo nuevo"

        new_content = agent_developer(issue, plan, current_content)
        results[file_path] = new_content
        print(f"  → {len(new_content)} chars generados")

    # Paso 3: el orquestador consolida
    print("\n[Orquestador] Consolidando resultados...")
    return {"plan": plan, "changes": results, "status": "ready_for_review"}

# ── Ejecución ────────────────────────────────────────────────────

issue = "Implementar DiscountEngine con soporte para descuentos porcentuales y fijos"
result = orchestrate(issue)
print(f"\n=== Resultado ===")
print(f"Archivos generados: {list(result['changes'].keys())}")
print(f"Status: {result['status']}")
```

**Output esperado:**

```
[Orquestador] Analizando issue...
[Planificador] Determinando archivos afectados...
  Plan: Crear DiscountEngine en discounts.py con métodos apply_percentage y apply_fixed.
        Modificar orders.py para integrar el engine en el proceso de checkout.
  Archivos a modificar: ['src/orders.py']
  Archivos a crear: ['src/discounts.py']

[Developer] Implementando src/orders.py...
  → 847 chars generados

[Developer] Implementando src/discounts.py...
  → 623 chars generados

[Orquestador] Consolidando resultados...

=== Resultado ===
Archivos generados: ['src/orders.py', 'src/discounts.py']
Status: ready_for_review
```

**Qué muestra:**
- El orquestador no escribe código — coordina y consolida
- El planificador (Haiku) es rápido y barato para análisis
- El developer (Sonnet) tiene mejor razonamiento para escribir código
- Los ejecutores son independientes — en un sistema real correrían en paralelo
- El resultado está "ready_for_review": un humano revisa el PR, no lo mergea automáticamente

---

## Comparación: script lineal vs workflow agéntico

```
Script lineal (lo que NO hacer):
─────────────────────────────────
Tiempo: 3s
Resultado: código generado sin verificar
Tests: no corridos
Si falla en prod: no lo sabés hasta que un usuario lo reporta

Feedback loop (este módulo):
─────────────────────────────
Tiempo: 12s (3 iteraciones × 4s)
Resultado: código verificado, todos los tests pasan
Tests: corridos 3 veces durante el desarrollo
Si hay un bug: el agente lo detecta y corrige antes de entregar

Multi-agente:
─────────────
Tiempo: 8s (planificación + implementación en paralelo)
Resultado: múltiples archivos coordinados
Tests: el orquestador puede incluir un ejecutor de testing
Si hay inconsistencia entre archivos: el orquestador lo detecta
```

---

Ver el [README principal](./README.md) para los patrones de diseño, human-in-the-loop y cuándo usar LangGraph.
