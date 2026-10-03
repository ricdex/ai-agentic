"""
Módulo 2 — Ejemplo 3: Patrones de agente

Tres patrones que aparecen en casi todo sistema agéntico serio, más allá del
loop ReAct del módulo 1:

1. Plan-and-Execute  — planificar una vez, ejecutar pasos, replanificar si falla
2. Reflection        — generar, evaluar contra un criterio, revisar (evaluator-optimizer)
3. Subagentes        — delegar subtareas a agentes con contexto propio y aislado

Los patrones reciben el LLM como una función `llm(system, prompt) -> str` para
que la orquestación sea testeable sin red. `claude_llm(client)` es el adaptador real.

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python agent_patterns.py
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import anthropic

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5-5")
WORKER_MODEL = os.environ.get("WORKER_MODEL", "claude-haiku-4-5")

LLM = Callable[[str, str], str]


def claude_llm(client, model: str = MODEL, max_tokens: int = 4096) -> LLM:
    def call(system: str, prompt: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text")

    return call


def extract_json(text: str):
    """Extrae el primer objeto o array JSON de una respuesta de texto.

    Para producción preferí structured outputs (Módulo 7); esto es el mínimo
    para que el ejemplo no dependa de features adicionales.
    """
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not match:
        raise ValueError(f"No hay JSON en la respuesta: {text[:200]!r}")
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# 1. Plan-and-Execute
# ---------------------------------------------------------------------------

PLANNER_SYSTEM = (
    "Sos un planificador. Dividí la tarea en pasos concretos y verificables, en orden. "
    'Respondé solo JSON: {"steps": ["paso 1", "paso 2", ...]}. Máximo 6 pasos.'
)
EXECUTOR_SYSTEM = (
    "Ejecutás UN paso de un plan. Usá los resultados previos como contexto. "
    'Respondé solo JSON: {"ok": true|false, "output": "..."}. '
    "ok=false si el paso no se puede completar, explicando por qué en output."
)


@dataclass
class PlanRun:
    plan: list[str]
    results: list[dict] = field(default_factory=list)
    replans: int = 0
    status: str = "running"


def plan_and_execute(task: str, planner: LLM, executor: LLM, max_replans: int = 1) -> PlanRun:
    """Planifica con un modelo capaz, ejecuta cada paso con uno barato.

    Ventaja frente a ReAct: el plan es un artefacto visible (se puede revisar,
    loguear, aprobar) y el modelo caro se llama una vez, no en cada paso.
    Desventaja: si el mundo no coincide con el plan, hay que replanificar.
    """
    run = PlanRun(plan=_make_plan(planner, task))
    i = 0
    while i < len(run.plan):
        step = run.plan[i]
        prior = "\n".join(f"- {r['step']}: {r['output']}" for r in run.results) or "(ninguno)"
        result = extract_json(executor(EXECUTOR_SYSTEM, f"Tarea: {task}\nResultados previos:\n{prior}\n\nPaso: {step}"))
        run.results.append({"step": step, "ok": bool(result.get("ok")), "output": str(result.get("output", ""))})

        if result.get("ok"):
            i += 1
            continue
        if run.replans >= max_replans:
            run.status = "failed"
            return run
        # Replanificar SOLO lo que falta, con el fallo como contexto.
        run.replans += 1
        done = [r["step"] for r in run.results if r["ok"]]
        new_steps = _make_plan(
            planner,
            f"{task}\n\nYa completado: {done}\nFalló '{step}': {result.get('output')}\n"
            "Planificá solo los pasos restantes.",
        )
        run.plan = run.plan[:i] + new_steps
    run.status = "done"
    return run


def _make_plan(planner: LLM, task: str) -> list[str]:
    steps = extract_json(planner(PLANNER_SYSTEM, task)).get("steps", [])
    if not steps or not all(isinstance(s, str) and s.strip() for s in steps):
        raise ValueError("El planner devolvió un plan vacío o inválido")
    return steps[:6]


# ---------------------------------------------------------------------------
# 2. Reflection (evaluator-optimizer)
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    passed: bool
    feedback: str


Evaluator = Callable[[str], Verdict]


def reflect(task: str, generator: LLM, evaluator: Evaluator, max_rounds: int = 3) -> tuple[str, list[Verdict]]:
    """Genera, evalúa y revisa hasta pasar o agotar rondas.

    El evaluador vale lo que vale su señal. Preferí señales externas y
    deterministas (tests, linters, validación de schema) antes que pedirle al
    mismo modelo "¿está bien?": un modelo se autoevalúa con sesgo a aprobar.
    """
    draft = generator("Resolvé la tarea.", task)
    history: list[Verdict] = []
    for _ in range(max_rounds):
        verdict = evaluator(draft)
        history.append(verdict)
        if verdict.passed:
            break
        draft = generator(
            "Revisá tu respuesta anterior aplicando el feedback. Devolvé solo la versión corregida.",
            f"Tarea: {task}\n\nRespuesta anterior:\n{draft}\n\nFeedback:\n{verdict.feedback}",
        )
    else:
        # Agotó las rondas sin pasar: evaluamos la última revisión para reportarla.
        history.append(evaluator(draft))
    return draft, history


def llm_judge(judge: LLM, rubric: str) -> Evaluator:
    """Evaluador con un LLM distinto del generador y una rúbrica explícita."""
    def evaluate(draft: str) -> Verdict:
        data = extract_json(judge(
            "Evaluás una respuesta contra una rúbrica. Sé estricto. "
            'Respondé solo JSON: {"pass": true|false, "feedback": "qué corregir"}.',
            f"Rúbrica:\n{rubric}\n\nRespuesta:\n{draft}",
        ))
        return Verdict(bool(data.get("pass")), str(data.get("feedback", "")))

    return evaluate


# ---------------------------------------------------------------------------
# 3. Subagentes
# ---------------------------------------------------------------------------

@dataclass
class SubagentResult:
    task: str
    ok: bool
    summary: str


def run_subagents(tasks: list[str], worker: LLM, max_workers: int = 4,
                  max_summary_chars: int = 2_000) -> list[SubagentResult]:
    """Cada subagente arranca con contexto LIMPIO (solo su tarea) y devuelve
    un resumen acotado. El orquestador nunca ve la exploración intermedia.

    Por qué: si el orquestador hiciera las 4 investigaciones él mismo, su
    contexto acumularía todo lo leído. Con subagentes solo acumula 4 resúmenes.
    Un fallo en un subagente no tumba a los demás.
    """
    system = (
        "Sos un subagente con una única tarea. Resolvela y devolvé un resumen "
        "breve y autocontenido: el orquestador no ve nada más que ese resumen."
    )

    def one(task: str) -> SubagentResult:
        try:
            out = worker(system, task)
            return SubagentResult(task, True, out[:max_summary_chars])
        except Exception as exc:  # noqa: BLE001 — aislar: un subagente roto no rompe el resto
            return SubagentResult(task, False, f"{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(one, tasks))


def orchestrate(goal: str, subtasks: list[str], orchestrator: LLM, worker: LLM) -> str:
    results = run_subagents(subtasks, worker)
    report = "\n\n".join(
        f"### {r.task}\n{'' if r.ok else '[FALLÓ] '}{r.summary}" for r in results
    )
    return orchestrator(
        "Consolidás resultados de subagentes. Marcá explícitamente lo que falló.",
        f"Objetivo: {goal}\n\nResultados:\n{report}",
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _demo():  # pragma: no cover - llama a la API real
    client = anthropic.Anthropic()
    smart, cheap = claude_llm(client, MODEL), claude_llm(client, WORKER_MODEL)

    print("=== 1. Plan-and-Execute ===")
    run = plan_and_execute("Diseñar el esquema de una tabla de cupones de descuento", smart, cheap)
    for r in run.results:
        print(f"  [{'ok' if r['ok'] else 'FAIL'}] {r['step']}")
    print(f"  status={run.status} replans={run.replans}\n")

    print("=== 2. Reflection ===")
    rubric = "- Menciona idempotencia\n- Menciona timeouts\n- Máximo 5 líneas"
    draft, verdicts = reflect(
        "Escribí 5 reglas para llamar a una API de pagos desde un worker",
        cheap, llm_judge(smart, rubric),
    )
    print(f"  rondas={len(verdicts)} pasó={verdicts[-1].passed}")
    print("  " + draft.replace("\n", "\n  ") + "\n")

    print("=== 3. Subagentes ===")
    print(orchestrate(
        "Elegir una cola para workers de agentes",
        ["Ventajas y límites de SQS para workers", "Ventajas y límites de Redis Streams",
         "Ventajas y límites de Pub/Sub de GCP"],
        smart, cheap,
    ))


if __name__ == "__main__":  # pragma: no cover
    _demo()
