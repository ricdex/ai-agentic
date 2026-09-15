# Módulo 14 — Fine-tuning: Cuándo (No) Usarlo

> "Fine-tuning es la herramienta que todo el mundo quiere usar y casi nadie necesita. Antes de entrenar algo, medí si un buen prompt ya te da el 95% del camino."

---

## Paso a paso

1. Antes de leer sobre entrenamiento, ejecutá `examples/01_decision_framework.py`: mide si prompting + few-shot ya alcanza el umbral de calidad que necesitás. La mayoría de las veces, sí.
2. Si el baseline con prompting no alcanza y el caso es de **alto volumen + tarea angosta**, mirá `02_lora_classifier.py` — fine-tuning de un modelo chico open-weight con LoRA, no de Claude.
3. Nunca declares que un fine-tune "mejoró" sin `03_eval_comparison.py` corriendo el mismo harness del [Módulo 10](../module-10-evals/README.md) contra el baseline.
4. Si el caso no es de altísimo volumen o la tarea no es angosta y repetible, no hagas fine-tuning — iterá el prompt o agregá RAG ([Módulo 6](../module-06-rag-memory/README.md)).

**Complejidad a evitar:** entrenar un modelo antes de agotar prompting, few-shot y RAG. Fine-tuning es el recurso más caro de mantener (dataset versionado, reentrenamiento, drift) — se paga una sola vez para ganar algo que a veces un mejor prompt te da gratis.

---

## 14.1 El framework de decisión

```
¿El problema se resuelve con un mejor prompt / más ejemplos en contexto?
  → SÍ: hacé eso. Es reversible, no tiene costo de entrenamiento, itera en minutos.
  → NO: ¿el problema es de conocimiento (el modelo no sabe algo), no de comportamiento?
      → SÍ: usá RAG (Módulo 6), no fine-tuning. Fine-tuning no es buena forma de "enseñar hechos".
      → NO: ¿la tarea es angosta, repetible, y corre a MUY alto volumen
             (miles/millones de veces) donde latencia y costo por llamada importan?
          → NO: seguí con Claude + buen prompt. El caso no justifica el costo de mantener un modelo propio.
          → SÍ: ahí fine-tuning (de un modelo chico, no de Claude vía API) puede pagarse solo.
```

Este orden no es arbitrario: cada paso es más barato de revertir que el siguiente. Un prompt se cambia en un commit. Un modelo fine-tuneado necesita reentrenarse, reevaluarse y redeployarse cada vez que cambian los requisitos.

---

## 14.2 Qué resuelve fine-tuning que prompting no resuelve

| Necesidad | ¿La resuelve un mejor prompt? |
|---|---|
| El modelo no conoce datos internos de tu empresa | No — eso es RAG (Módulo 6), no fine-tuning |
| Necesitás que siga instrucciones más de cerca en casos raros | Probablemente sí — más ejemplos few-shot o un system prompt más específico |
| Necesitás un tono/estilo muy consistente en miles de outputs | A veces — probá few-shot con 5-10 ejemplos antes de asumir que hace falta entrenar |
| Necesitás clasificar/rutear con latencia de milisegundos y sin llamar a una API externa | No — acá sí hay un caso real para un modelo chico fine-tuneado corriendo local |
| Necesitás bajar el costo por llamada en una tarea de altísimo volumen y baja complejidad | No con Claude vía API — sí con un modelo abierto chico entrenado para esa tarea específica |

La columna de la derecha es la señal: fine-tuning gana cuando el cuello de botella es **volumen + latencia + costo por inferencia**, no calidad de razonamiento. Para razonamiento complejo, un modelo grande con buen prompt casi siempre le gana a un modelo chico fine-tuneado.

---

## 14.3 Fine-tuning de Claude: estado actual

Anthropic no ofrece fine-tuning self-serve de los modelos Claude vía la API pública — la vía para personalizar el comportamiento de Claude en producción es prompting (system prompts extensos, many-shot en el mensaje), prompt caching para que ese contexto no se pague en cada llamada (ver [Módulo 12, sección 12.8](../module-12-background-agents/README.md#128-prompt-caching-en-workers-la-optimización-más-importante)), y RAG para conocimiento específico. Antes de planificar un fine-tune de Claude, confirmá en la [documentación oficial](https://docs.anthropic.com) si esto cambió — es un área que se mueve rápido.

**Consecuencia práctica:** si tu necesidad es "que Claude se comporte distinto", la herramienta es el prompt, no un fine-tune. Fine-tuning entra en juego cuando decidís usar un modelo *open-weight* para una subtarea específica — no como reemplazo de Claude, sino como complemento.

---

## 14.4 El patrón real: modelo chico fine-tuneado + Claude para lo difícil

El caso de uso legítimo en un sistema agéntico no es "reemplazar Claude por un modelo entrenado" — es el mismo principio de selección de modelo por complejidad que ya usás en `MODELS = {"fast": ..., "standard": ..., "powerful": ...}` ([final-project/shared/claude_client.py](../final-project/shared/claude_client.py)), llevado un paso más allá:

```
Router / clasificador de alto volumen  →  modelo chico fine-tuneado (local, <50ms, sin costo de API)
Tarea que requiere razonamiento         →  Claude (Haiku/Sonnet/Opus según complejidad)
```

Ejemplo real: un sistema que procesa 500.000 tickets/día necesita clasificar urgencia antes de rutear. Eso es un problema angosto y repetitivo — un clasificador fine-tuneado (BERT-sized, corre en CPU) lo resuelve en milisegundos y sin costo de API. Los tickets que el clasificador marca como ambiguos o complejos sí pasan por Claude, que puede razonar sobre casos que el modelo chico no puede.

---

## 14.5 Anatomía de un fine-tune con LoRA

LoRA (Low-Rank Adaptation) entrena una fracción pequeña de parámetros nuevos en vez de todo el modelo — mucho más barato en cómputo y memoria, y el resultado es un adapter de unos pocos MB en vez de un modelo completo nuevo.

```python
from peft import LoraConfig, get_peft_model

config = LoraConfig(
    r=8,                    # rango de la descomposición — más alto = más capacidad, más costo
    lora_alpha=16,
    target_modules=["q_proj", "v_proj"],  # qué capas del modelo se adaptan
    lora_dropout=0.05,
    task_type="SEQ_CLS",    # o CAUSAL_LM según la tarea
)
model = get_peft_model(base_model, config)
# De acá en más, model.train() como cualquier fine-tune — pero solo ~1% de los parámetros son entrenables
```

**Dataset mínimo:** para un clasificador angosto y bien definido, 200-500 ejemplos etiquetados por clase suelen alcanzar. Para tareas más abiertas, se necesita bastante más — si no tenés ese volumen de datos limpios y etiquetados, fine-tuning no es viable todavía; conseguir el dataset es el verdadero costo, no el entrenamiento en sí.

---

## 14.6 Evaluación: sin esto, no sabés si mejoró

El error más común: entrenar, mirar 3 ejemplos que salieron bien, y declarar éxito. Igual que en el [Módulo 10](../module-10-evals/README.md), la única forma válida de comparar es correr el **mismo eval suite** contra el baseline (prompting con Claude) y el modelo fine-tuneado:

```python
baseline_report = eval_suite.run(claude_prompted_classifier)
finetuned_report = eval_suite.run(lora_finetuned_classifier)

eval_suite.compare(baseline_report, finetuned_report)
# accuracy:   ↑ 0.02   (mejora marginal)
# latency_ms: ↓ 340    (esto es lo que en realidad ganaste)
# cost_usd:   ↓ 0.0018 (por esto vale la pena, no por accuracy)
```

Muchas veces el fine-tune no gana en calidad — gana en costo y latencia, con calidad *suficiente*. Esa es una victoria real, pero hay que medirla explícitamente, no asumirla.

---

## 14.7 Costos ocultos que no son el entrenamiento

- **Versionado de datos y modelo**: el dataset de entrenamiento y el checkpoint resultante son artefactos que hay que versionar igual que código ([claude.md](../CLAUDE.md) — "Modelos como artefactos versionados", sección AI-Native).
- **Drift**: el mundo cambia, el modelo fine-tuneado no. Un router de tickets entrenado en 2026 puede degradarse silenciosamente si el negocio agrega una categoría nueva de producto.
- **Reentrenamiento**: cada cambio de requisitos implica un ciclo completo de dataset → train → eval → deploy, mucho más lento que editar un prompt.
- **Infraestructura de inferencia**: correr el modelo fine-tuneado (aunque sea chico) es infraestructura que mantenés vos — a diferencia de Claude vía API, donde Anthropic opera el modelo.

---

## 14.8 Checklist antes de fine-tunear algo

- [ ] Medí el baseline con prompting + few-shot con el mismo eval suite que vas a usar para comparar (Módulo 10)
- [ ] El gap entre baseline y objetivo es de comportamiento/latencia/costo, no de conocimiento (si es conocimiento, es RAG)
- [ ] El volumen de la tarea justifica el costo de mantener un modelo propio
- [ ] Tenés (o podés conseguir) un dataset etiquetado limpio, no solo "unos ejemplos que junté"
- [ ] Definiste quién reentrena el modelo cuando el negocio cambie, y con qué frecuencia
- [ ] El modelo fine-tuneado es la pieza chica de un sistema donde Claude sigue manejando lo que requiere razonamiento

Si no podés tildar los primeros tres, todavía no es momento de fine-tunear nada.

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Framework de decisión](./EXAMPLES.md#ejemplo-1--framework-de-decisión-prompting-vs-fine-tuning) | Few-shot con Claude alcanza 0.91 de accuracy en el dataset de prueba — no hace falta entrenar nada |
| [02 — Clasificador LoRA](./EXAMPLES.md#ejemplo-2--clasificador-de-urgencia-con-lora) | Fine-tune de un modelo chico para clasificar urgencia de tickets: 0.5MB de adapter, <10ms de inferencia |
| [03 — Comparación con evals](./EXAMPLES.md#ejemplo-3--comparación-baseline-vs-fine-tuneado-con-el-harness-del-módulo-10) | Mismo eval suite corrido contra Claude y contra el modelo LoRA: accuracy similar, costo y latencia muy distintos |

---

## Ejercicio

Tomá el `triage_agent.py` del [proyecto final](../final-project/vm1-orchestrator/triage_agent.py):

1. Reuní (o simulá) 300 issues ya triageados como dataset etiquetado (automatable / needs_spec / complexity)
2. Corré `01_decision_framework.py` contra ese dataset: ¿el triage con Claude + few-shot ya supera el 90% de accuracy?
3. Si no lo supera, identificá si el gap es de conocimiento del dominio (→ agregale contexto/RAG al prompt) o de volumen/latencia (→ ahí sí evaluá un clasificador fine-tuneado)
4. Documentá la decisión con el framework de 14.1 — no entrenes nada todavía, solo llegá a la conclusión de si vale la pena

El objetivo de este ejercicio no es entrenar un modelo — es practicar el criterio para NO hacerlo quince pasos antes de lo necesario.

---

Anterior: [Módulo 13 → Multimodal](../module-13-multimodal/README.md)

**Fin del curso avanzado.**

Recorriste:
- Módulo 6: RAG y memoria semántica
- Módulo 7: Structured outputs confiables
- Módulo 8: MCP — el protocolo estándar
- Módulo 9: Streaming para UX en producción
- Módulo 10: Evals para mejorar sin adivinar
- Módulo 11: Deployment real, no demos
- Módulo 12: Agentes persistentes y background workers
- Módulo 13: Agentes multimodales — vision, documentos, audio
- Módulo 14: Fine-tuning — y por qué casi nunca es el primer paso
