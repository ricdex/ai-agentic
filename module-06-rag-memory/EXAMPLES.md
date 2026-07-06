# Módulo 6 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Embeddings básicos: texto → vector → similitud

**Archivo:** `examples/01_embeddings_basic.py`

Demuestra cómo convertir texto en vectores y calcular similitud semántica. La base de todo sistema RAG.

```python
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")  # modelo liviano, 384 dimensiones

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# Frases de prueba: algunas semánticamente similares, otras no
sentences = [
    "Error al procesar pago con tarjeta Visa",
    "problema con cobro de crédito",          # similar a la primera
    "falla en el sistema de pagos",            # similar a la primera
    "error de red en el servidor",             # diferente
    "timeout en la base de datos",             # diferente
    "La función login no valida el email",     # diferente
]

print("Generando embeddings...")
embeddings = model.encode(sentences)
print(f"Shape de cada embedding: {embeddings[0].shape}  # 384 dimensiones\n")

# Comparar la primera frase contra todas las demás
query = sentences[0]
query_emb = embeddings[0]

print(f"Query: '{query}'\n")
print(f"{'Similitud':>10}  Frase")
print("-" * 70)

results = []
for i, (sent, emb) in enumerate(zip(sentences[1:], embeddings[1:]), 1):
    sim = cosine_similarity(query_emb, emb)
    results.append((sim, sent))

for sim, sent in sorted(results, reverse=True):
    bar = "█" * int(sim * 20)
    print(f"  {sim:.3f}  {bar:<20}  {sent}")
```

**Output esperado:**

```
Generando embeddings...
Shape de cada embedding: (384,)  # 384 dimensiones

Query: 'Error al procesar pago con tarjeta Visa'

Similitud  Frase
----------------------------------------------------------------------
  0.847  ████████████████░░░░  falla en el sistema de pagos
  0.812  ████████████████░░░░  problema con cobro de crédito
  0.341  ███████░░░░░░░░░░░░░  error de red en el servidor
  0.287  █████░░░░░░░░░░░░░░░  timeout en la base de datos
  0.198  ████░░░░░░░░░░░░░░░░  La función login no valida el email
```

**Qué muestra:**
- "falla en el sistema de pagos" (0.847) y "problema con cobro de crédito" (0.812) son muy similares al query aunque no comparten palabras
- "error de red" (0.341) comparte "error" pero habla de otra cosa → similitud media
- "login no valida el email" (0.198) es conceptualmente diferente → similitud baja
- Un threshold de ~0.75 separa bien los resultados relevantes de los irrelevantes

---

## Ejemplo 2 — Pipeline RAG completo

**Archivo:** `examples/02_rag_pipeline.py`

Indexa documentación técnica y responde preguntas usando solo el contenido recuperado.

```python
import numpy as np
import anthropic
from sentence_transformers import SentenceTransformer

client = anthropic.Anthropic()
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# ── FASE 1: Indexing ─────────────────────────────────────────────

DOCS = [
    {
        "id": "doc-1",
        "title": "Manejo de pagos",
        "content": "Los pagos se procesan con Stripe. El monto se congela al confirmar la orden. Soportamos tarjetas de crédito y débito. Las transacciones fallidas se reintentan automáticamente hasta 3 veces con backoff exponencial."
    },
    {
        "id": "doc-2",
        "title": "Sistema de cupones",
        "content": "Los cupones de descuento se validan antes de congelar el precio. Un cupón puede ser porcentual (10% off) o fijo ($5 off). Los cupones vencen a medianoche UTC del día de expiración. Un cupón no puede combinarse con otro."
    },
    {
        "id": "doc-3",
        "title": "Manejo de inventario",
        "content": "El stock se reserva al agregar al carrito y se decrementa al confirmar el pago. Si el pago falla, el stock reservado se libera en 30 minutos. El inventario usa Redis con bloqueo optimista."
    },
    {
        "id": "doc-4",
        "title": "Notificaciones",
        "content": "Las notificaciones son asíncronas vía Celery. Se envían emails por: confirmación de orden, cambio de estado, y fallo de pago. Los webhooks de terceros se procesan en cola separada."
    },
    {
        "id": "doc-5",
        "title": "Autenticación",
        "content": "Se usa JWT con expiración de 24 horas. El refresh token dura 30 días. Las sesiones inválidas se blacklistean en Redis. Los endpoints de admin requieren 2FA."
    },
]

print("Indexando documentos...")
for doc in DOCS:
    doc["embedding"] = embed_model.encode(doc["content"])
print(f"✓ {len(DOCS)} documentos indexados\n")

# ── FASE 2: Retrieval ────────────────────────────────────────────

def retrieve(query: str, top_k: int = 2) -> list[dict]:
    query_emb = embed_model.encode(query)
    scored = []
    for doc in DOCS:
        sim = float(np.dot(query_emb, doc["embedding"]) /
                    (np.linalg.norm(query_emb) * np.linalg.norm(doc["embedding"])))
        scored.append((sim, doc))
    scored.sort(reverse=True)
    return [(sim, doc) for sim, doc in scored[:top_k]]

# ── FASE 3: Generation ───────────────────────────────────────────

def answer(query: str) -> str:
    results = retrieve(query, top_k=2)

    context = "\n\n".join([
        f"[{doc['title']}]\n{doc['content']}"
        for _, doc in results
    ])

    print(f"Query: {query}")
    print(f"Documentos recuperados:")
    for sim, doc in results:
        print(f"  • {doc['title']} (similitud: {sim:.3f})")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system="""Respondé la pregunta SOLO usando el contexto provisto.
Si la respuesta no está en el contexto, decí "No tengo esa información en la documentación."
No inventes información.""",
        messages=[{
            "role": "user",
            "content": f"Contexto:\n{context}\n\nPregunta: {query}"
        }]
    )

    answer_text = response.content[0].text
    print(f"Respuesta: {answer_text}\n")
    return answer_text


queries = [
    "¿Cuántas veces se reintenta un pago fallido?",
    "¿Puede un usuario usar dos cupones en la misma compra?",
    "¿Qué pasa con el stock si el pago falla?",
    "¿Cuál es el algoritmo de ordenamiento más eficiente?",  # fuera del dominio
]

print("=" * 50)
for q in queries:
    answer(q)
    print("-" * 50)
```

**Output esperado:**

```
Indexando documentos...
✓ 5 documentos indexados

==================================================
Query: ¿Cuántas veces se reintenta un pago fallido?
Documentos recuperados:
  • Manejo de pagos (similitud: 0.891)
  • Manejo de inventario (similitud: 0.612)
Respuesta: Las transacciones fallidas se reintentan automáticamente hasta 3 veces con backoff exponencial.

--------------------------------------------------
Query: ¿Puede un usuario usar dos cupones en la misma compra?
Documentos recuperados:
  • Sistema de cupones (similitud: 0.923)
  • Manejo de pagos (similitud: 0.534)
Respuesta: No. Un cupón no puede combinarse con otro — solo se puede usar un cupón por compra.

--------------------------------------------------
Query: ¿Qué pasa con el stock si el pago falla?
Documentos recuperados:
  • Manejo de inventario (similitud: 0.876)
  • Manejo de pagos (similitud: 0.698)
Respuesta: Si el pago falla, el stock reservado se libera automáticamente en 30 minutos.

--------------------------------------------------
Query: ¿Cuál es el algoritmo de ordenamiento más eficiente?
Documentos recuperados:
  • Autenticación (similitud: 0.187)
  • Notificaciones (similitud: 0.162)
Respuesta: No tengo esa información en la documentación.

--------------------------------------------------
```

**Qué muestra:**
- Las primeras 3 preguntas tienen respuestas precisas directamente de los documentos correctos
- La cuarta pregunta (fuera del dominio) recupera documentos irrelevantes (similitud < 0.2) y el agente dice que no sabe
- El threshold implícito: similitud < 0.3 es señal de que la query está fuera del dominio

---

## Ejemplo 3 — Agente con memoria semántica de episodios pasados

**Archivo:** `examples/03_semantic_memory_agent.py`

Reemplaza la búsqueda por keywords del módulo 1 con búsqueda semántica. El agente aprende de errores pasados.

```python
import numpy as np
import anthropic
import time
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass

client = anthropic.Anthropic()
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

@dataclass
class Episode:
    task: str
    outcome: str
    learned: str
    embedding: np.ndarray
    timestamp: float

class SemanticMemory:
    def __init__(self):
        self.episodes: list[Episode] = []

    def save(self, task: str, outcome: str, learned: str):
        emb = embed_model.encode(task)
        self.episodes.append(Episode(task, outcome, learned, emb, time.time()))

    def recall(self, current_task: str, top_k: int = 2, threshold: float = 0.75) -> list[Episode]:
        if not self.episodes:
            return []
        query_emb = embed_model.encode(current_task)
        scored = []
        for ep in self.episodes:
            sim = float(np.dot(query_emb, ep.embedding) /
                        (np.linalg.norm(query_emb) * np.linalg.norm(ep.embedding)))
            if sim >= threshold:
                scored.append((sim, ep))
        scored.sort(reverse=True)
        return [ep for _, ep in scored[:top_k]]


memory = SemanticMemory()

# Cargar episodios pasados (en prod: desde DB persistente)
memory.save(
    task="Implementar sistema de cupones de descuento",
    outcome="Exitoso después de 3 iteraciones",
    learned="Validar cupón ANTES de congelar precio. Si el cupón vence entre el ingreso y el pago, retornar error 409 con mensaje claro."
)
memory.save(
    task="Optimizar queries de la tabla orders",
    outcome="Exitoso. Latencia -60%",
    learned="Índice compuesto en (user_id, created_at DESC) es crítico para queries por usuario ordenados por fecha."
)
memory.save(
    task="Implementar descuentos por volumen en el carrito",
    outcome="Exitoso",
    learned="El descuento se aplica por cada OrderItem, no sobre el total. Validar que quantity > umbral antes de aplicar."
)
memory.save(
    task="Fix: race condition en el sistema de inventario",
    outcome="Resuelto con Lua script en Redis",
    learned="No usar locks de Python para operaciones de Redis. Usar scripts Lua para atomicidad garantizada."
)

# Nueva tarea
new_task = "Agregar código de descuento referido por amigo"

print(f"Tarea actual: {new_task}\n")

relevant = memory.recall(new_task)
print(f"Episodios relevantes encontrados: {len(relevant)}")
for ep in relevant:
    print(f"\n  Tarea pasada: {ep.task}")
    print(f"  Outcome: {ep.outcome}")
    print(f"  Aprendido: {ep.learned}")

# El agente usa estos episodios como contexto
memory_context = "\n".join([
    f"- [{ep.task}] → {ep.learned}"
    for ep in relevant
]) if relevant else "Sin episodios relevantes."

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=300,
    system=f"""Sos un agente de desarrollo con memoria de implementaciones pasadas.
Usá los episodios pasados como guía para evitar errores conocidos.

Episodios relevantes:
{memory_context}""",
    messages=[{"role": "user", "content": f"¿Qué consideraciones importantes tengo que tener para: {new_task}?"}]
)

print(f"\nRespuesta del agente (con memoria):\n{response.content[0].text}")
```

**Output esperado:**

```
Tarea actual: Agregar código de descuento referido por amigo

Episodios relevantes encontrados: 2

  Tarea pasada: Implementar sistema de cupones de descuento
  Outcome: Exitoso después de 3 iteraciones
  Aprendido: Validar cupón ANTES de congelar precio. Si el cupón vence entre el ingreso y el pago, retornar error 409 con mensaje claro.

  Tarea pasada: Implementar descuentos por volumen en el carrito
  Outcome: Exitoso
  Aprendido: El descuento se aplica por cada OrderItem, no sobre el total. Validar que quantity > umbral antes de aplicar.

Respuesta del agente (con memoria):
Basado en implementaciones anteriores de descuentos, las consideraciones principales son:

1. **Validar el código de referido ANTES de congelar el precio** — igual que con cupones. Si el código se valida tarde, el precio podría congelarse sin el descuento aplicado.

2. **El descuento del referido probablemente aplica al total de la orden**, no por item (a diferencia del descuento por volumen). Definir esto explícitamente antes de implementar.

3. **Manejar el caso de expiración**: si el código de referido tiene fecha límite, retornar 409 con mensaje claro si venció entre el ingreso y el pago.

4. **Unicidad**: ¿puede el mismo código usarse múltiples veces? ¿Hay límite de usos? Definir antes de implementar.
```

**Qué muestra:**
- "código de referido" y "código de descuento" comparten significado semántico con "cupones" → episodio recuperado correctamente
- "descuentos por volumen" también es relevante → recuperado
- "race condition en inventario" y "optimizar queries" no son recuperados (similitud < 0.75)
- La respuesta del agente incorpora el conocimiento de los episodios pasados (validar antes de congelar, manejo de expiración)

---

Ver el [README principal](./README.md) para los conceptos de embeddings, chunking y opciones de vector stores.
