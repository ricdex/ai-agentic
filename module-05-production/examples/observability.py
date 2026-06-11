"""
Módulo 5 — Issue Solver con Observabilidad

El mismo agente del módulo 3, ahora con:
- Trazabilidad completa en Langfuse (o logging local si no hay Langfuse)
- Tracking de tokens y costos
- Métricas de performance por iteración
- Alertas de umbral

Requisitos:
    pip install anthropic langfuse

Variables de entorno:
    ANTHROPIC_API_KEY=sk-ant-...
    LANGFUSE_PUBLIC_KEY=pk-lf-...   (opcional)
    LANGFUSE_SECRET_KEY=sk-lf-...   (opcional)
    LANGFUSE_HOST=http://localhost:3000  (si self-hosted)

Uso:
    python observability.py
"""

import os
import time
import json
import uuid
import anthropic
from dataclasses import dataclass, field
from pathlib import Path

client = anthropic.Anthropic()

# Langfuse es opcional — si no está configurado, usamos logging local
try:
    from langfuse import Langfuse
    langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    )
    LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
except ImportError:
    LANGFUSE_ENABLED = False
    print("[Observabilidad] Langfuse no instalado — usando logging local")


# --- Telemetría local (fallback) ---

@dataclass
class SpanMetrics:
    name: str
    start_time: float
    end_time: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    tool_calls: list = field(default_factory=list)
    error: str = ""

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    @property
    def cost_usd(self) -> float:
        # Precios aproximados claude-sonnet-4-6 (Mayo 2025)
        input_cost = (self.input_tokens - self.cached_tokens) * 3.0 / 1_000_000
        cached_cost = self.cached_tokens * 0.30 / 1_000_000
        output_cost = self.output_tokens * 15.0 / 1_000_000
        return input_cost + cached_cost + output_cost


@dataclass
class TraceMetrics:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task: str = ""
    spans: list = field(default_factory=list)
    success: bool = False
    iterations: int = 0

    @property
    def total_cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.spans)

    @property
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.spans)

    @property
    def total_duration_ms(self) -> float:
        return sum(s.duration_ms for s in self.spans)

    def log_summary(self):
        print(f"\n[Trace {self.trace_id}] Summary")
        print(f"  Task: {self.task[:60]}")
        print(f"  Success: {self.success}")
        print(f"  Iterations: {self.iterations}")
        print(f"  Total tokens: {self.total_tokens:,} | Cost: ${self.total_cost_usd:.4f}")
        print(f"  Total time: {self.total_duration_ms:.0f}ms")
        print(f"\n  Spans:")
        for span in self.spans:
            status = "✓" if not span.error else "✗"
            print(
                f"    [{status}] {span.name}: "
                f"{span.duration_ms:.0f}ms | "
                f"{span.input_tokens + span.output_tokens} tokens | "
                f"${span.cost_usd:.4f}"
            )
            if span.error:
                print(f"        Error: {span.error[:80]}")


class Tracer:
    """
    Abstracción sobre Langfuse o logging local.
    La API es la misma — el destino cambia según configuración.
    """

    def __init__(self, task: str):
        self.metrics = TraceMetrics(task=task)
        self._lf_trace = None
        self._lf_span = None

        if LANGFUSE_ENABLED:
            self._lf_trace = langfuse.trace(
                name="issue-solver",
                input={"task": task},
                metadata={"trace_id": self.metrics.trace_id}
            )

    def start_span(self, name: str) -> SpanMetrics:
        span = SpanMetrics(name=name, start_time=time.time())
        self.metrics.spans.append(span)
        return span

    def end_span(self, span: SpanMetrics, response=None, error: str = ""):
        span.end_time = time.time()
        span.error = error

        if response is not None and hasattr(response, "usage"):
            span.input_tokens = response.usage.input_tokens
            span.output_tokens = response.usage.output_tokens
            span.cached_tokens = getattr(response.usage, "cache_read_input_tokens", 0)

        if LANGFUSE_ENABLED and self._lf_trace:
            self._lf_trace.span(
                name=span.name,
                start_time=span.start_time,
                end_time=span.end_time,
                metadata={
                    "input_tokens": span.input_tokens,
                    "output_tokens": span.output_tokens,
                    "cached_tokens": span.cached_tokens,
                    "cost_usd": span.cost_usd,
                    "tool_calls": span.tool_calls,
                    "error": span.error
                }
            )

    def log_tool_call(self, span: SpanMetrics, tool_name: str, result_preview: str):
        span.tool_calls.append({"tool": tool_name, "preview": result_preview[:100]})

    def finish(self, success: bool, output: str = ""):
        self.metrics.success = success
        if LANGFUSE_ENABLED and self._lf_trace:
            self._lf_trace.update(
                output=output,
                metadata={"success": success, "total_cost": self.metrics.total_cost_usd}
            )
        self.metrics.log_summary()


# --- El agente con observabilidad ---

TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Escribe un archivo completo.",
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
        "description": "Corre pytest en el directorio dado.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
            "required": []
        }
    }
]


def make_executor(repo_path: str):
    import subprocess

    def execute(name: str, inputs: dict) -> str:
        base = Path(repo_path)
        if name == "read_file":
            try:
                return (base / inputs["path"]).read_text()
            except Exception as e:
                return f"ERROR: {e}"
        elif name == "write_file":
            try:
                p = base / inputs["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(inputs["content"])
                return "OK"
            except Exception as e:
                return f"ERROR: {e}"
        elif name == "run_tests":
            test_path = inputs.get("path", str(base))
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", test_path, "-v", "--tb=short"],
                    capture_output=True, text=True, timeout=30, cwd=str(base)
                )
                return (result.stdout + result.stderr)[-3000:]
            except Exception as e:
                return f"ERROR: {e}"
        return f"ERROR: unknown tool {name}"

    return execute


def solve_with_observability(task: str, repo_path: str) -> TraceMetrics:
    """Issue solver con trazabilidad completa."""
    tracer = Tracer(task=task)
    execute_tool = make_executor(repo_path)

    print(f"\n[Trace {tracer.metrics.trace_id}] Starting: {task[:60]}")
    print("=" * 60)

    messages = [{"role": "user", "content": f"Repo: {repo_path}\n\nTarea: {task}"}]
    test_passed = False
    iteration = 0
    max_iterations = 3

    system = [
        {
            "type": "text",
            "text": (
                "Sos un agente de debugging. "
                "Leé el código, identificá el bug, arreglalo, corré los tests. "
                "Si los tests pasan, terminá."
            ),
            "cache_control": {"type": "ephemeral"}
        }
    ]

    while not test_passed and iteration < max_iterations:
        iteration += 1
        tracer.metrics.iterations = iteration
        span = tracer.start_span(f"iteration_{iteration}")

        print(f"\n[Iteración {iteration}]")

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                tools=TOOLS,
                messages=messages,
                system=system
            )
            tracer.end_span(span, response=response)

        except Exception as e:
            tracer.end_span(span, error=str(e))
            print(f"  ERROR: {e}")
            break

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            print(f"  Agente: {text[:200]}")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_span = tracer.start_span(f"tool_{block.name}")
                    result = execute_tool(block.name, block.input)
                    tracer.end_span(tool_span)
                    tracer.log_tool_call(span, block.name, result)

                    print(f"  → {block.name}: {result[:80]}...")

                    if block.name == "run_tests":
                        if "passed" in result and "failed" not in result:
                            test_passed = True
                            print(f"  [✓] Tests pasaron!")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})

    tracer.finish(success=test_passed)
    return tracer.metrics


# --- Demo ---

if __name__ == "__main__":
    # Reusar el demo_repo del módulo 3
    demo_path = "/tmp/demo_repo"

    # Recrear si no existe
    if not Path(f"{demo_path}/src/stack.py").exists():
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "module-03-dev-workflows/examples"))
        try:
            from issue_solver import create_demo_repo
            create_demo_repo(demo_path)
        except ImportError:
            # Crear manualmente
            os.makedirs(f"{demo_path}/src", exist_ok=True)
            os.makedirs(f"{demo_path}/tests", exist_ok=True)
            Path(f"{demo_path}/src/__init__.py").write_text("")
            Path(f"{demo_path}/src/stack.py").write_text('''
class Stack:
    def __init__(self):
        self._items = []
    def push(self, item):
        self._items.append(item)
    def pop(self):
        if not self._items:
            raise IndexError("Stack is empty")
        return self._items.pop(0)  # BUG: debería ser pop() sin argumento
    def is_empty(self):
        return len(self._items) == 0
''')
            Path(f"{demo_path}/tests/__init__.py").write_text("")
            Path(f"{demo_path}/tests/test_stack.py").write_text('''
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.stack import Stack
def test_lifo_order():
    s = Stack()
    s.push(1); s.push(2); s.push(3)
    assert s.pop() == 3
''')

    metrics = solve_with_observability(
        task="El Stack.pop() retorna el primer elemento en vez del último. Arreglalo.",
        repo_path=demo_path
    )

    # Guardar métricas en JSON
    report_path = "/tmp/agent_metrics.json"
    report = {
        "trace_id": metrics.trace_id,
        "success": metrics.success,
        "iterations": metrics.iterations,
        "total_cost_usd": metrics.total_cost_usd,
        "total_tokens": metrics.total_tokens,
        "total_duration_ms": metrics.total_duration_ms,
        "spans": [
            {
                "name": s.name,
                "duration_ms": s.duration_ms,
                "tokens": s.input_tokens + s.output_tokens,
                "cached_tokens": s.cached_tokens,
                "cost_usd": s.cost_usd
            }
            for s in metrics.spans
        ]
    }
    Path(report_path).write_text(json.dumps(report, indent=2))
    print(f"\n[Métricas guardadas en {report_path}]")
