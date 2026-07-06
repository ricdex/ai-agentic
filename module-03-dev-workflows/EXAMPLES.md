# Módulo 3 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Issue solver: de GitHub issue a código

**Archivo:** `examples/issue_solver.py`

El agente recibe el título y cuerpo de un issue, explora el repo local, escribe el fix, corre los tests y reporta el resultado.

```python
import anthropic
import subprocess
import os

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "list_files",
        "description": "Lista archivos de un directorio",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"]
        }
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "search_code",
        "description": "Busca un patrón en todos los archivos .py del directorio",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "directory": {"type": "string"}
            },
            "required": ["pattern", "directory"]
        }
    },
    {
        "name": "write_file",
        "description": "Escribe o sobreescribe un archivo",
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
        "description": "Corre los tests del proyecto",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directorio o archivo de tests"}},
            "required": ["path"]
        }
    }
]

def execute_tool(name, inp, repo_path):
    if name == "list_files":
        d = os.path.join(repo_path, inp["directory"].lstrip("./"))
        try:
            return "\n".join(os.listdir(d))
        except FileNotFoundError:
            return f"Directorio no encontrado: {d}"

    elif name == "read_file":
        p = os.path.join(repo_path, inp["path"].lstrip("./"))
        try:
            return open(p).read()
        except FileNotFoundError:
            return f"Archivo no encontrado: {p}"

    elif name == "search_code":
        d = os.path.join(repo_path, inp["directory"].lstrip("./"))
        result = subprocess.run(
            ["grep", "-rn", inp["pattern"], d, "--include=*.py"],
            capture_output=True, text=True
        )
        return result.stdout or "Sin resultados"

    elif name == "write_file":
        p = os.path.join(repo_path, inp["path"].lstrip("./"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(inp["content"])
        return f"Escrito: {p}"

    elif name == "run_tests":
        p = os.path.join(repo_path, inp["path"].lstrip("./"))
        result = subprocess.run(
            ["python", "-m", "pytest", p, "-v", "--tb=short"],
            capture_output=True, text=True, cwd=repo_path
        )
        return result.stdout + result.stderr

SYSTEM = """Sos un agente de desarrollo autónomo. Tu trabajo es resolver GitHub issues.

Proceso obligatorio:
1. Explorá el repo para entender la estructura (NO leas todo, buscá lo relevante)
2. Identificá el archivo con el bug
3. Leé ese archivo y los tests relacionados
4. Escribí el fix mínimo necesario
5. Corré los tests — si fallan, iterá
6. Reportá qué hiciste y qué tests pasan

Reglas:
- NO cambies tests existentes para que pasen (el test define el comportamiento correcto)
- Máximo 3 archivos modificados por issue
- Si el fix requiere más cambios, reportalo y pedí confirmación"""

def solve_issue(issue_title: str, issue_body: str, repo_path: str) -> str:
    issue_text = f"# {issue_title}\n\n{issue_body}"
    messages = [{"role": "user", "content": f"Resolvé este issue en el repo en {repo_path}:\n\n{issue_text}"}]
    MAX_ITER = 6

    print(f"Resolviendo: {issue_title}")
    print("=" * 50)

    for i in range(MAX_ITER):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            return response.content[0].text

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input, repo_path)
                    print(f"  [{block.name}] {list(block.input.values())[0]!r:.50s}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "user", "content": results})

    return "Límite de iteraciones alcanzado."

result = solve_issue(
    issue_title="Bug: calculate_discount returns wrong amount for percentage discounts",
    issue_body="""When applying a percentage discount, the function returns the discount amount
instead of the final price.

Expected: calculate_discount(100, type='percent', value=20) → 80
Actual:   calculate_discount(100, type='percent', value=20) → 20

The test test_percentage_discount is failing.""",
    repo_path="./sample_repo"
)

print(f"\n=== Resultado del agente ===\n{result}")
```

**Output esperado:**

```
Resolviendo: Bug: calculate_discount returns wrong amount for percentage discounts
==================================================
  [list_files] '.'
  [list_files] 'src'
  [search_code] 'calculate_discount'
  [read_file] 'src/discounts.py'
  [read_file] 'tests/test_discounts.py'
  [write_file] 'src/discounts.py'
  [run_tests] 'tests/test_discounts.py'

=== Resultado del agente ===
Fix aplicado en `src/discounts.py`.

**Causa raíz:** En la función `calculate_discount`, el caso `type='percent'` retornaba
`amount * value / 100` (el valor del descuento) en lugar de `amount - amount * value / 100`
(el precio final).

**Cambio:**
```python
# Antes (línea 12):
return amount * value / 100

# Después:
return amount - (amount * value / 100)
```

**Tests:** 4 passed, 0 failed
- test_percentage_discount ✓ (era el que fallaba)
- test_fixed_discount ✓
- test_zero_discount ✓
- test_full_discount ✓
```

**Qué muestra:**
- El agente NO lee todo el repo — busca directamente con `search_code`
- Explora solo los archivos relevantes (discounts.py + test_discounts.py)
- El fix es mínimo: una línea cambiada
- Verifica con tests reales antes de reportar éxito

---

## Ejemplo 2 — Prompt caching: costo con y sin caché

**Archivo:** `examples/prompt_caching_comparison.py`

Demuestra el ahorro de tokens al cachear el contexto del repo entre iteraciones del agente.

```python
import anthropic
import time

client = anthropic.Anthropic()

# Simular contexto del repo (en prod: CONTEXT.md + estructura real)
REPO_CONTEXT = """
# Proyecto: E-commerce API

## Entidades principales
- Order: id, user_id, items[], status, created_at
- OrderItem: product_id, quantity, unit_price
- Payment: order_id, amount, method, status
- Discount: code, type (percent|fixed), value, expires_at

## Reglas de negocio
- El precio se congela al confirmar la orden (no puede cambiar después)
- Los descuentos se aplican antes de congelar el precio
- Un pago fallido no cancela la orden automáticamente (requiere 3 intentos)
- Las notificaciones son async (no bloquean el flujo principal)

## Stack
- Python 3.11, FastAPI, PostgreSQL, Redis, Celery

## Convenciones
- Todos los precios en centavos (int), no float
- IDs son UUIDs v4
- Timestamps en UTC
- Errores retornan {"error": "código", "message": "descripción"}
""" * 10  # ~2000 tokens de contexto

ISSUES = [
    "¿Cómo se maneja el caso donde un cupón vence entre que el usuario lo ingresa y se procesa el pago?",
    "¿Qué pasa si un OrderItem tiene quantity=0?",
    "¿Cómo se calcula el total de una orden con múltiples descuentos?"
]

print("=== SIN prompt caching ===\n")
total_tokens_no_cache = 0
for i, issue in enumerate(ISSUES):
    start = time.time()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=REPO_CONTEXT,
        messages=[{"role": "user", "content": issue}]
    )
    elapsed = time.time() - start
    tokens = response.usage.input_tokens
    total_tokens_no_cache += tokens
    print(f"Issue {i+1}: {tokens} input tokens | {elapsed:.2f}s")

print(f"Total: {total_tokens_no_cache} tokens\n")

print("=== CON prompt caching ===\n")
total_tokens_cached = 0
total_cached_hits = 0
for i, issue in enumerate(ISSUES):
    start = time.time()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=[{
            "type": "text",
            "text": REPO_CONTEXT,
            "cache_control": {"type": "ephemeral"}  # ← diferencia clave
        }],
        messages=[{"role": "user", "content": issue}]
    )
    elapsed = time.time() - start
    tokens = response.usage.input_tokens
    cached = response.usage.cache_read_input_tokens
    total_tokens_cached += tokens
    total_cached_hits += cached

    label = "(primer call, se crea caché)" if i == 0 else f"({cached} tokens desde caché)"
    print(f"Issue {i+1}: {tokens} input tokens | {elapsed:.2f}s | {label}")

print(f"Total tokens procesados: {total_tokens_cached}")
print(f"Total tokens desde caché: {total_cached_hits}")

# Cálculo de ahorro (precios Haiku)
cost_no_cache = total_tokens_no_cache * 0.8 / 1_000_000
cost_cached = total_tokens_cached * 0.8 / 1_000_000 + total_cached_hits * 0.08 / 1_000_000
saving_pct = (1 - cost_cached / cost_no_cache) * 100
print(f"\nCosto sin caché:  ${cost_no_cache:.5f}")
print(f"Costo con caché:  ${cost_cached:.5f}")
print(f"Ahorro:           {saving_pct:.0f}%")
```

**Output esperado:**

```
=== SIN prompt caching ===

Issue 1: 2134 input tokens | 1.82s
Issue 2: 2134 input tokens | 1.71s
Issue 3: 2134 input tokens | 1.68s
Total: 6402 tokens

=== CON prompt caching ===

Issue 1: 2134 input tokens | 1.89s | (primer call, se crea caché)
Issue 2: 2134 input tokens | 0.94s | (2098 tokens desde caché)
Issue 3: 2134 input tokens | 0.91s | (2098 tokens desde caché)
Total tokens procesados: 6402
Total tokens desde caché: 4196

Costo sin caché:  $0.00512
Costo con caché:  $0.00143
Ahorro:           72%
```

**Qué muestra:**
- El tiempo del primer call es igual (se crea el caché)
- Los calls 2 y 3 son casi el doble de rápidos (datos servidos desde caché)
- El ahorro de costo es ~72% — en producción con decenas de issues, el ROI es significativo
- Los tokens procesados son los mismos, pero los "cached" cuestan 90% menos

---

## Ejemplo 3 — CI/CD agéntico: fix automático cuando falla el pipeline

Este es el flujo completo del módulo 3.6. El GitHub Actions workflow dispara el agente cuando CI falla.

**`.github/workflows/ai-fix.yml`:**

```yaml
name: AI Fix on CI Failure

on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]

jobs:
  auto-fix:
    if: github.event.workflow_run.conclusion == 'failure'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install anthropic

      - name: Fetch failed CI logs
        id: fetch-logs
        run: |
          gh run view ${{ github.event.workflow_run.id }} --log-failed > failed_logs.txt
          echo "Log size: $(wc -c < failed_logs.txt) bytes"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Run AI fix agent
        run: python agents/ci_fixer.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          FAILED_RUN_ID: ${{ github.event.workflow_run.id }}
          FAILED_LOG_FILE: failed_logs.txt

      - name: Create fix PR if changes were made
        run: |
          if [ -n "$(git status --porcelain)" ]; then
            git checkout -b "ai-fix/ci-failure-${{ github.event.workflow_run.id }}"
            git add -A
            git commit -m "fix: AI-generated fix for CI failure #${{ github.event.workflow_run.id }}"
            git push -u origin HEAD
            gh pr create \
              --title "🤖 AI Fix: CI failure in run #${{ github.event.workflow_run.id }}" \
              --body "$(cat fix_summary.txt)" \
              --label "ai-generated,needs-review"
          else
            echo "No changes to commit"
          fi
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Output en GitHub Actions cuando CI falla:**

```
Run AI fix agent
  Analizando log de CI...
  Error detectado: AttributeError en tests/test_payments.py::test_refund_partial
  Buscando código relacionado...
  Leyendo src/payments.py...
  Fix identificado: método refund() no maneja amount=None
  Escribiendo fix...
  Corriendo tests localmente...
  ✓ 12 tests pasan, 0 fallan

Create fix PR if changes were made
  [main 2a3f891] fix: AI-generated fix for CI failure #1842
  Branch ai-fix/ci-failure-1842 created
  PR creado: https://github.com/org/repo/pull/234
```

**El PR creado contiene:**
```
🤖 AI Fix: CI failure in run #1842

## Análisis
El test `test_refund_partial` fallaba porque `payments.refund()` no validaba
cuando `amount` es `None`, lanzando `TypeError: '<' not supported between NoneType and int`.

## Cambio
`src/payments.py` línea 87: agregado guard para `amount is None`.

## Tests
12 tests pasan. El test que fallaba ahora pasa.

⚠️ Revisión requerida antes de mergear.
```

**Qué muestra:**
- El agente corre en CI sin intervención humana
- Crea un PR con el fix — NO mergea automáticamente
- El PR está etiquetado como `needs-review`: un humano lo aprueba
- Si el agente no puede hacer el fix (problema complejo), el job termina sin crear PR y el equipo lo revisa manualmente

---

Ver el [README principal](./README.md) para el workflow completo y la estrategia de selección de modelos.
