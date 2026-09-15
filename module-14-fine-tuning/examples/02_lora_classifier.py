"""
Módulo 14 — Ejemplo 2: Clasificador de urgencia con LoRA

Fine-tune de un modelo chico open-weight (DistilBERT, ~66M parámetros) con
LoRA para la MISMA tarea que 01_decision_framework.py resuelve con Claude
+ prompting. El objetivo no es "mejor calidad" — es correr la clasificación
local, en milisegundos, sin costo de API, para el caso de altísimo volumen
descrito en 14.4.

Solo entrena ~1% de los parámetros del modelo (los adapters LoRA); el
resto queda congelado. El resultado es un adapter de unos pocos MB, no un
modelo nuevo completo.

Requisitos:
    pip install torch transformers peft datasets

Uso:
    python 02_lora_classifier.py
"""

import numpy as np
import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

BASE_MODEL = "distilbert-base-uncased"
LABELS = ["low", "medium", "high", "critical"]
LABEL2ID = {label: i for i, label in enumerate(LABELS)}
ID2LABEL = {i: label for label, i in LABEL2ID.items()}

# Dataset de entrenamiento angosto y específico de la tarea. En un caso real
# esto viene de tickets ya triageados por humanos — ver el ejercicio del README.
TRAIN_DATA = [
    ("What are your business hours?", "low"),
    ("Can I change the shipping address before delivery?", "low"),
    ("Does the discount apply to shipping too?", "low"),
    ("My item arrived slightly scratched, not urgent but wanted to report it.", "low"),
    ("I received the wrong size, need an exchange when convenient.", "medium"),
    ("The product arrived damaged, need a replacement this week.", "medium"),
    ("My subscription renews in 3 days and I want to downgrade the plan.", "medium"),
    ("Payment failed twice, I need this resolved today, event is in 2 days.", "high"),
    ("My card expired and I'll lose access to a paid feature tomorrow.", "high"),
    ("Can't update payment method, subscription lapses in 24 hours.", "high"),
    ("Production site is returning 500 errors on all endpoints right now.", "critical"),
    ("I can see other customers' card data in my account.", "critical"),
    ("App crashes immediately on the payment screen, on every device.", "critical"),
    ("Checkout is completely broken, no customer can pay right now.", "critical"),
]


def build_dataset(tokenizer) -> Dataset:
    texts = [t for t, _ in TRAIN_DATA]
    labels = [LABEL2ID[label] for _, label in TRAIN_DATA]
    dataset = Dataset.from_dict({"text": texts, "label": labels})
    return dataset.map(
        lambda batch: tokenizer(batch["text"], truncation=True, padding="max_length", max_length=64),
        batched=True,
    )


def compute_metrics(eval_pred) -> dict:
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    accuracy = (predictions == labels).mean()
    return {"accuracy": float(accuracy)}


def build_lora_model():
    base_model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=len(LABELS), id2label=ID2LABEL, label2id=LABEL2ID
    )
    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=8,
        lora_alpha=16,
        lora_dropout=0.1,
        target_modules=["q_lin", "v_lin"],  # capas de atención de DistilBERT
    )
    model = get_peft_model(base_model, lora_config)
    model.print_trainable_parameters()
    return model


def predict(model, tokenizer, text: str) -> str:
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=64)
    # El Trainer mueve el modelo a GPU/MPS si hay una disponible; los tensores
    # del tokenizer nacen en CPU, así que hay que alinear el device o explota.
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits
    predicted_id = int(torch.argmax(logits, dim=-1))
    return ID2LABEL[predicted_id]


if __name__ == "__main__":
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    train_dataset = build_dataset(tokenizer)
    model = build_lora_model()

    training_args = TrainingArguments(
        output_dir="/tmp/urgency-lora",
        num_train_epochs=10,
        per_device_train_batch_size=4,
        learning_rate=1e-3,
        logging_steps=5,
        save_strategy="no",
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        compute_metrics=compute_metrics,
    )
    trainer.train()

    model.save_pretrained("/tmp/urgency-lora/adapter")
    print("\nAdapter guardado en /tmp/urgency-lora/adapter (solo los pesos LoRA, no el modelo base)\n")

    model.eval()  # apaga dropout — sin esto la inferencia no es determinista (ni portable entre devices)
    for ticket in [
        "Site is down for every customer, losing sales right now.",
        "Just wondering if you ship internationally.",
        "Card got declined, subscription ends tomorrow and I need it.",
    ]:
        print(f"  {predict(model, tokenizer, ticket):8s}  {ticket}")
