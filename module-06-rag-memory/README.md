# Módulo 6 — RAG y Memoria Semántica

> "La diferencia entre un agente que recuerda keywords y uno que recuerda significado es la diferencia entre buscar en un índice y pensar."

---

## 6.1 El límite de la memoria episódica con keywords

En el módulo 1 implementamos memoria episódica con SQLite y búsqueda por keywords. Funciona para casos simples. Falla cuando:

```
Episodio guardado: "Error al procesar pago con tarjeta Visa"
Query del agente:  "problema con cobro de crédito"
Resultado:         ❌ No encuentra — no hay keywords en común
```

La solución es **búsqueda semántica**: convertir texto en vectores numéricos que capturan el *significado*, no las palabras exactas.

---

## 6.2 Embeddings: texto → vector

Un embedding es una representación numérica del significado de un texto.

```
"Error al procesar pago con tarjeta Visa"  → [0.23, -0.41, 0.87, ...]  (768 dimensiones)
"problema con cobro de crédito"            → [0.25, -0.39, 0.84, ...]  (muy similar)
"error de red en el servidor"              → [-0.12, 0.67, -0.23, ...]  (diferente)
```

La **similitud coseno** entre dos vectores mide cuán parecidos son semánticamente:
- 1.0 = idénticos en significado
- 0.0 = sin relación
- -1.0 = opuestos

---

## 6.3 Pipeline RAG completo

RAG = Retrieval-Augmented Generation. El patrón más usado en sistemas AI de producción.

```
INDEXING (una vez, o cuando cambia el contenido)
───────────────────────────────────────────────
Documentos → Chunks → Embeddings → Vector Store

RETRIEVAL + GENERATION (por cada query)
───────────────────────────────────────────────
Query → Embedding → Top-K similares → Contexto → Claude → Respuesta
```

```
┌─────────────────────────────────────────────────────────┐
│                    INDEXING PHASE                        │
│                                                         │
│  [Doc 1]  ──→  chunk()  ──→  embed()  ──→  store()      │
│  [Doc 2]  ──→  chunk()  ──→  embed()  ──→  store()      │
│  [Doc N]  ──→  chunk()  ──→  embed()  ──→  store()      │
└─────────────────────────────────────────────────────────┘
                                                ↓
┌─────────────────────────────────────────────────────────┐
│                   QUERY PHASE                           │
│                                                         │
│  "¿Cómo proceso pagos?"                                 │
│       ↓                                                 │
│  embed(query) → cosine_similarity(all_vectors)          │
│       ↓                                                 │
│  top-3 chunks más similares                             │
│       ↓                                                 │
│  Claude + contexto recuperado → respuesta precisa       │
└─────────────────────────────────────────────────────────┘
```

---

## 6.4 Chunking: el arte de dividir documentos

El tamaño del chunk determina la calidad de la recuperación:

```python
# ❌ Chunk demasiado grande — recupera mucho ruido
chunk_size = 5000  # Todo un archivo → poco foco

# ❌ Chunk demasiado pequeño — pierde contexto
chunk_size = 50   # Media oración → sin significado

# ✓ Sweet spot para código y docs técnicos
chunk_size = 500   # Un párrafo o función completa
chunk_overlap = 50  # Overlapping para no cortar ideas
```

Estrategias según el tipo de contenido:
- **Código**: por función o clase (boundaries semánticos)
- **Documentación**: por sección (headers como separadores)
- **Conversaciones**: por turno o ventana deslizante

---

## 6.5 Vector stores: opciones

| Store | Cuándo usarlo | Cómo self-hostear |
|-------|--------------|-------------------|
| **SQLite + numpy** | Desarrollo, < 100K docs | Incluido, sin setup |
| **pgvector** | Producción con PostgreSQL ya en uso | `CREATE EXTENSION vector` |
| **Qdrant** | Producción, alta escala, búsqueda avanzada | `docker run qdrant/qdrant` |
| **Pinecone** | Managed, sin ops | API key |

**Regla:** empezá con SQLite + numpy. Migrá a pgvector cuando tengas PostgreSQL en producción.

---

## 6.6 Embeddings: proveedores

| Proveedor | Modelo recomendado | Dimensiones | Cuándo |
|-----------|-------------------|-------------|--------|
| **sentence-transformers** | `all-MiniLM-L6-v2` | 384 | Dev local, sin costo |
| **Voyage AI** | `voyage-3` | 1024 | Producción con Claude (recomendado por Anthropic) |
| **OpenAI** | `text-embedding-3-small` | 1536 | Si ya usás OpenAI en el stack |

```bash
# Para los ejemplos de este módulo
pip install sentence-transformers numpy
```

---

## 6.7 Memoria semántica para agentes

La aplicación más directa de RAG para agentes: reemplazar la búsqueda por keywords del módulo 1 con búsqueda semántica.

```python
# Antes (módulo 1): keyword search
episodes = db.query("SELECT * FROM episodes WHERE task LIKE '%pago%'")

# Ahora: semantic search
query_embedding = embed("problema con cobro de crédito")
episodes = vector_store.search(query_embedding, top_k=3)
# Encuentra "Error al procesar pago con tarjeta Visa" aunque no comparta palabras
```

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Embeddings básicos](./EXAMPLES.md#ejemplo-1--embeddings-básicos-texto--vector--similitud) | "problema con cobro" encuentra "Error al procesar pago Visa" (sim: 0.81) sin compartir palabras |
| [02 — Pipeline RAG completo](./EXAMPLES.md#ejemplo-2--pipeline-rag-completo) | 5 docs indexados; preguntas fuera del dominio reciben "No tengo esa información" |
| [03 — Memoria semántica de episodios](./EXAMPLES.md#ejemplo-3--agente-con-memoria-semántica-de-episodios-pasados) | Nueva tarea encuentra episodios relevantes de cupones y descuentos anteriores |

---

## Ejercicio

Tomá el `issue_solver.py` del módulo 3 y dale **memoria semántica de issues resueltos**:

1. Cuando resuelve un issue exitosamente, guarda el problema + solución como embedding
2. Antes de explorar el repo, busca issues similares en la memoria
3. Si encuentra uno relevante (similitud > 0.8), usa esa solución como punto de partida

Esto implementa el "aprendizaje" real del agente — con el tiempo, se vuelve más eficiente en problemas recurrentes.

---

## Para producción

```bash
# pgvector en PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT,
    metadata JSONB,
    embedding vector(384)
);
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops);

# Qdrant self-hosted
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```

---

Siguiente: [Módulo 7 → Structured Outputs](../module-07-structured-outputs/README.md)
