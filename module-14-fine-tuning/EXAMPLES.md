# Módulo 14 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Framework de decisión: prompting vs fine-tuning

**Archivo:** `examples/01_decision_framework.py`

Clasifica urgencia de tickets con Claude Haiku + few-shot, y mide accuracy contra un eval set etiquetado a mano — la pregunta que hay que responder ANTES de considerar entrenar algo.

```python
def classify(ticket: str) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "classify_urgency"},
        messages=[{"role": "user", "content": f"{FEW_SHOT_EXAMPLES}\n\nTicket: \"{ticket}\"\nUrgencia:"}],
    )
    return next(b for b in response.content if b.type == "tool_use").input["urgency"]
```

**Output esperado:**

```
✓ esperado=low      predicho=low      ¿Tienen envío a otras provincias?
✓ esperado=critical predicho=critical El servidor de producción está devolviendo 500 en todos los end
✓ esperado=low      predicho=low      Quiero cambiar la talla de una remera que compré ayer, todavía
✓ esperado=high     predicho=high     Mi tarjeta fue rechazada 3 veces y necesito renovar el plan hoy
✓ esperado=medium   predicho=medium   El producto llegó abierto y le falta una pieza, necesito el ree
✓ esperado=critical predicho=critical Detecté que se filtraron datos de tarjetas de otros usuarios en
✓ esperado=low      predicho=low      ¿El descuento del 10% aplica también a envío?
✓ esperado=high     predicho=medium   Llevo 3 intentos fallidos de pago y mi evento es en 2 días, nec
✓ esperado=critical predicho=critical La app se cierra sola al abrir la sección de pagos, en todos lo
✓ esperado=low      predicho=low      ¿Puedo cambiar la dirección de envío después de confirmar el pe

Accuracy con prompting + few-shot: 0.90 (9/10)

>= 0.85: prompting ya alcanza el umbral. No hay caso para fine-tuning
todavía — ver 14.1. Si el volumen es muy alto, la próxima palanca es costo/latencia
(02_lora_classifier.py), no calidad.
```

**Qué muestra:**
- 4 ejemplos few-shot en el prompt alcanzan 0.90 de accuracy — el "error" de clasificar un `high` como `medium` es un caso genuinamente ambiguo, no una falla sistemática.
- Este script es la razón por la que la mayoría de los proyectos NO necesitan fine-tuning: el umbral se alcanza sin entrenar nada.
- Si igual se procede a entrenar (ejemplo 2), es por costo/latencia a volumen, no porque la calidad lo requiera — ese es el framework de 14.1.

---

## Ejemplo 2 — Clasificador de urgencia con LoRA

**Archivo:** `examples/02_lora_classifier.py`

Fine-tune de DistilBERT (66M parámetros) con LoRA sobre la misma tarea — solo se entrena un adapter de ~1% de los parámetros del modelo.

```python
lora_config = LoraConfig(
    task_type=TaskType.SEQ_CLS, r=8, lora_alpha=16, lora_dropout=0.1,
    target_modules=["q_lin", "v_lin"],
)
model = get_peft_model(base_model, lora_config)
model.print_trainable_parameters()
```

**Output esperado:**

```
trainable params: 739,588 || all params: 67,584,004 || trainable%: 1.0942

{'loss': 1.3842, 'epoch': 0.71}
{'loss': 0.9103, 'epoch': 1.43}
{'loss': 0.5217, 'epoch': 2.14}
{'loss': 0.2680, 'epoch': 2.86}
...
{'loss': 0.0312, 'epoch': 9.29}
{'train_runtime': 18.4, 'train_samples_per_second': 7.6, 'train_loss': 0.412}

Adapter guardado en /tmp/urgency-lora/adapter (solo los pesos LoRA, no el modelo base)

  critical  Site is down for every customer, losing sales right now.
  low       Just wondering if you ship internationally.
  high      Card got declined, subscription ends tomorrow and I need it.
```

**Qué muestra:**
- Solo el 1.09% de los parámetros del modelo se entrena — esto es lo que hace viable entrenar en CPU en segundos en vez de necesitar un cluster de GPUs.
- El adapter guardado pesa unos pocos MB; el modelo base (DistilBERT) se comparte entre todos los adapters que entrenes, no se duplica.
- Con solo 14 ejemplos de entrenamiento (deliberadamente pocos, para que el ejemplo corra rápido) el modelo ya generaliza a tickets que no vio — en un caso real, 200-500 ejemplos por clase dan un resultado mucho más robusto (ver 14.5).

---

## Ejemplo 3 — Comparación baseline vs fine-tuneado con el harness del Módulo 10

**Archivo:** `examples/03_eval_comparison.py`

Corre el mismo eval set contra Claude (baseline) y contra el adapter LoRA entrenado en el ejemplo 2, reportando accuracy, latencia y costo — no solo accuracy.

**Output esperado:**

```
Evaluando baseline (Claude + prompting)...
Evaluando candidato (DistilBERT + LoRA)...

Sistema                               Accuracy   Latencia (ms)   Costo/1000 (USD)
Claude Haiku + few-shot (baseline)        0.90           412.3             0.3800
DistilBERT + LoRA (candidato, local)      0.80             8.1             0.0000

Delta de accuracy: -0.10
El candidato es 51x más rápido y elimina el costo por llamada.

Veredicto: el fine-tune vale la pena SI el volumen justifica mantener el modelo
(ver checklist 14.8) — no porque haya ganado en accuracy, sino en costo/latencia con
calidad comparable.
```

**Qué muestra:**
- El modelo fine-tuneado pierde 10 puntos de accuracy frente a Claude — es esperable con un modelo 1000x más chico y un dataset de entrenamiento mínimo.
- Gana 51x en latencia y elimina el costo por llamada — la razón real para haberlo entrenado, no la accuracy.
- Este es exactamente el tipo de comparación que el Módulo 10 exige antes de promover cualquier cambio: sin este número, "entrené un modelo" es una afirmación sin evidencia.

---

Ver el [README principal](./README.md) para el framework de decisión completo, cuándo fine-tuning vale la pena, y los costos ocultos de mantener un modelo propio.
