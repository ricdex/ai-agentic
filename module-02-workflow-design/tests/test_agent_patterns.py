import json
import threading
from types import SimpleNamespace

import pytest

import agent_patterns as ap


def scripted(*outputs):
    """LLM falso: devuelve las salidas en orden y registra los prompts."""
    queue = list(outputs)
    calls = []

    def llm(system, prompt):
        calls.append((system, prompt))
        out = queue.pop(0)
        return out if isinstance(out, str) else json.dumps(out)

    llm.calls = calls
    return llm


# --- helpers ----------------------------------------------------------------

def test_extract_json_from_wrapped_text():
    assert ap.extract_json('Claro:\n{"a": 1}\nlisto') == {"a": 1}
    assert ap.extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        ap.extract_json("sin json")


def test_claude_llm_adapter_joins_text_blocks():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text="ho"),
            SimpleNamespace(type="text", text="la"),
        ])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    assert ap.claude_llm(client, "m")("sys", "p") == "hola"
    assert calls[0]["model"] == "m" and calls[0]["system"] == "sys"


# --- plan-and-execute -------------------------------------------------------

def test_plan_and_execute_happy_path_passes_prior_results():
    planner = scripted({"steps": ["a", "b"]})
    executor = scripted({"ok": True, "output": "A hecho"}, {"ok": True, "output": "B hecho"})
    run = ap.plan_and_execute("t", planner, executor)
    assert run.status == "done" and run.replans == 0
    assert [r["step"] for r in run.results] == ["a", "b"]
    assert "a: A hecho" in executor.calls[1][1]


def test_plan_and_execute_replans_only_remaining_steps():
    planner = scripted({"steps": ["a", "b", "c"]}, {"steps": ["b2", "c"]})
    executor = scripted(
        {"ok": True, "output": "ok"},
        {"ok": False, "output": "no existe la tabla"},
        {"ok": True, "output": "ok"},
        {"ok": True, "output": "ok"},
    )
    run = ap.plan_and_execute("t", planner, executor, max_replans=1)
    assert run.status == "done" and run.replans == 1
    assert run.plan == ["a", "b2", "c"]
    replan_prompt = planner.calls[1][1]
    assert "Ya completado: ['a']" in replan_prompt and "no existe la tabla" in replan_prompt


def test_plan_and_execute_fails_after_max_replans():
    planner = scripted({"steps": ["a"]})
    executor = scripted({"ok": False, "output": "x"})
    run = ap.plan_and_execute("t", planner, executor, max_replans=0)
    assert run.status == "failed"


@pytest.mark.parametrize("plan", [{"steps": []}, {"steps": ["ok", ""]}, {}])
def test_invalid_plan_is_rejected(plan):
    with pytest.raises(ValueError):
        ap.plan_and_execute("t", scripted(plan), scripted())


def test_plan_is_capped_at_six_steps():
    planner = scripted({"steps": [str(i) for i in range(10)]})
    executor = scripted(*[{"ok": True, "output": ""}] * 6)
    assert len(ap.plan_and_execute("t", planner, executor).plan) == 6


# --- reflection -------------------------------------------------------------

def test_reflect_stops_when_evaluator_passes():
    gen = scripted("v1", "v2")
    verdicts = iter([ap.Verdict(False, "falta X"), ap.Verdict(True, "")])
    draft, history = ap.reflect("t", gen, lambda d: next(verdicts))
    assert draft == "v2"
    assert [v.passed for v in history] == [False, True]
    assert "falta X" in gen.calls[1][1]


def test_reflect_gives_up_after_max_rounds_and_reports_last_draft():
    gen = scripted("v1", "v2", "v3")
    seen = []

    def evaluator(d):
        seen.append(d)
        return ap.Verdict(False, "mal")

    draft, history = ap.reflect("t", gen, evaluator, max_rounds=2)
    assert draft == "v3"
    assert seen == ["v1", "v2", "v3"]
    assert len(history) == 3 and not history[-1].passed


def test_llm_judge_parses_verdict():
    judge = scripted({"pass": False, "feedback": "agregá timeouts"})
    verdict = ap.llm_judge(judge, "rúbrica")("borrador")
    assert verdict == ap.Verdict(False, "agregá timeouts")
    assert "rúbrica" in judge.calls[0][1]


# --- subagentes -------------------------------------------------------------

def test_subagents_get_isolated_context_and_bounded_summary():
    seen_prompts = []
    lock = threading.Lock()

    def worker(system, prompt):
        with lock:
            seen_prompts.append(prompt)
        if prompt == "rota":
            raise RuntimeError("timeout")
        return prompt.upper() * 100

    results = ap.run_subagents(["a", "rota", "c"], worker, max_summary_chars=10)
    assert sorted(seen_prompts) == ["a", "c", "rota"]  # cada uno ve solo su tarea
    assert [r.task for r in results] == ["a", "rota", "c"]  # orden preservado
    assert results[0].ok and len(results[0].summary) == 10
    assert not results[1].ok and "RuntimeError: timeout" in results[1].summary


def test_orchestrate_marks_failures_for_the_orchestrator():
    def worker(system, prompt):
        if prompt == "b":
            raise ValueError("x")
        return "resumen a"

    orchestrator = scripted("informe final")
    assert ap.orchestrate("objetivo", ["a", "b"], orchestrator, worker) == "informe final"
    prompt = orchestrator.calls[0][1]
    assert "### a\nresumen a" in prompt and "### b\n[FALLÓ]" in prompt
