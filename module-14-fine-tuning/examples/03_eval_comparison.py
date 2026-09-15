"""
Módulo 14 — Ejemplo 3: Comparación baseline vs fine-tuneado con el harness del Módulo 10

Corre el MISMO dataset de eval (EVAL_SET, igual que en 01_decision_framework.py)
contra dos sistemas distintos:
  - baseline: Claude + few-shot prompting (01_decision_framework.py)
  - candidato: el clasificador LoRA entrenado en 02_lora_classifier.py

Reporta accuracy, latencia y costo por predicción — la comparación real que
justifica (o no) haber entrenado algo. Ver 14.6 del README.

Requisitos:
    pip install anthropic torch transformers peft
    # y haber corrido 02_lora_classifier.py antes, para tener el adapter guardado

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 03_eval_comparison.py
"""

import time
from dataclasses import dataclass

import torch
from peft import PeftModel
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import anthropic

client = anthropic.Anthropic()

BASE_MODEL = "distilbert-base-uncased"
ADAPTER_PATH = "/tmp/urgency-lora/adapter"
LABELS = ["low", "medium", "high", "critical"]
ID2LABEL = dict(enumerate(LABELS))

# Costo aproximado de Claude Haiku por 1M tokens (ver Módulo 5, 5.4) —
# usado solo para estimar costo relativo, no como fuente de verdad de pricing.
HAIKU_INPUT_COST_PER_TOKEN = 1.00 / 1_000_000
HAIKU_OUTPUT_COST_PER_TOKEN = 5.00 / 1_000_000

EVAL_SET = [
    ("Do you offer gift wrapping?", "low"),
    ("All endpoints are returning 500 in production right now.", "critical"),
    ("I'd like to exchange this for a different color, no rush.", "low"),
    ("My card was declined and my plan lapses tomorrow, need this fixed today.", "high"),
    ("Item arrived with a missing part, need the replacement by the weekend.", "medium"),
    ("I can see another customer's card details in my account.", "critical"),
    ("Does the promo code also cover shipping?", "low"),
    ("Three failed payment attempts and my event is in two days.", "high"),
    ("The app crashes on the payment screen on every device.", "critical"),
    ("Can I update my shipping address after checkout?", "low"),
]

TOOL = {
    "name": "classify_urgency",
    "description": "Clasifica la urgencia de un ticket de soporte",
    "input_schema": {
        "type": "object",
        "properties": {"urgency": {"type": "string", "enum": LABELS}},
        "required": ["urgency"],
    },
}


@dataclass
class SystemReport:
    name: str
    accuracy: float
    avg_latency_ms: float
    cost_per_1000_predictions_usd: float


def eval_claude_baseline() -> SystemReport:
    correct = 0
    total_latency = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    for ticket, expected in EVAL_SET:
        start = time.time()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "classify_urgency"},
            messages=[{"role": "user", "content": f"Ticket: \"{ticket}\"\nUrgencia:"}],
        )
        total_latency += (time.time() - start) * 1000
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        predicted = next(b for b in response.content if b.type == "tool_use").input["urgency"]
        correct += predicted == expected

    avg_cost_per_call = (
        total_input_tokens / len(EVAL_SET) * HAIKU_INPUT_COST_PER_TOKEN
        + total_output_tokens / len(EVAL_SET) * HAIKU_OUTPUT_COST_PER_TOKEN
    )
    return SystemReport(
        name="Claude Haiku + few-shot (baseline)",
        accuracy=correct / len(EVAL_SET),
        avg_latency_ms=total_latency / len(EVAL_SET),
        cost_per_1000_predictions_usd=avg_cost_per_call * 1000,
    )


def eval_lora_classifier() -> SystemReport:
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    base_model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=len(LABELS))
    model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
    model.eval()

    correct = 0
    total_latency = 0.0

    for ticket, expected in EVAL_SET:
        inputs = tokenizer(ticket, return_tensors="pt", truncation=True, padding=True, max_length=64)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        start = time.time()
        with torch.no_grad():
            logits = model(**inputs).logits
        total_latency += (time.time() - start) * 1000

        predicted = ID2LABEL[int(torch.argmax(logits, dim=-1))]
        correct += predicted == expected

    return SystemReport(
        name="DistilBERT + LoRA (candidato, local)",
        accuracy=correct / len(EVAL_SET),
        avg_latency_ms=total_latency / len(EVAL_SET),
        cost_per_1000_predictions_usd=0.0,  # inferencia local en CPU, sin costo por llamada
    )


def print_comparison(baseline: SystemReport, candidate: SystemReport) -> None:
    print(f"{'Sistema':35s} {'Accuracy':>10s} {'Latencia (ms)':>15s} {'Costo/1000 (USD)':>18s}")
    for report in (baseline, candidate):
        print(f"{report.name:35s} {report.accuracy:>10.2f} {report.avg_latency_ms:>15.1f} {report.cost_per_1000_predictions_usd:>18.4f}")

    accuracy_delta = candidate.accuracy - baseline.accuracy
    latency_ratio = baseline.avg_latency_ms / max(candidate.avg_latency_ms, 0.01)
    print(f"\nDelta de accuracy: {accuracy_delta:+.2f}")
    print(f"El candidato es {latency_ratio:.0f}x más rápido y elimina el costo por llamada.")

    if accuracy_delta >= -0.05:
        print(
            "\nVeredicto: el fine-tune vale la pena SI el volumen justifica mantener el modelo "
            "(ver checklist 14.8) — no porque haya ganado en accuracy, sino en costo/latencia con "
            "calidad comparable."
        )
    else:
        print(
            "\nVeredicto: el candidato pierde demasiada accuracy. O el dataset de entrenamiento "
            "es chico/no representativo, o esta tarea todavía necesita el razonamiento de Claude."
        )


if __name__ == "__main__":
    print("Evaluando baseline (Claude + prompting)...")
    baseline_report = eval_claude_baseline()

    print("Evaluando candidato (DistilBERT + LoRA)...")
    try:
        candidate_report = eval_lora_classifier()
    except OSError:
        print(
            f"\nNo se encontró un adapter en {ADAPTER_PATH}. "
            "Corré 02_lora_classifier.py primero para entrenarlo."
        )
        raise SystemExit(1)

    print()
    print_comparison(baseline_report, candidate_report)
