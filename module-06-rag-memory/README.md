# Módulo 6 — RAG y Memoria Semántica

> "La diferencia entre un agente que recuerda keywords y uno que recuerda significado es la diferencia entre buscar en un índice y pensar."

---

## Paso a paso

1. Ejecutá `examples/01_embeddings_basic.py` y compará una búsqueda por palabras con similitud semántica.
2. Ejecutá `02_rag_pipeline.py` con un conjunto pequeño de documentos; inspeccioná qué fragmentos se recuperan y por qué.
3. Medí recuperación correcta antes de usar el contexto para generar una respuesta.
4. Añadí `03_semantic_memory_agent.py` solo cuando el agente necesite aprender de interacciones previas.
5. Cuando el volumen ya no entra en SQLite+numpy, migrá a `04_vector_store_pgvector.py` — mismo pipeline, pero corriendo la similitud como índice ANN en Postgres en vez de un loop en Python.
6. Si tu set de evaluación muestra fallas de recuperación concretas, aplicá **la técnica que ataca esa falla** con `05_advanced_retrieval.py` (hybrid, rerank, HyDE, caché semántica). No las sumes todas por defecto.
7. Pasá a `06_agentic_rag.py` solo si las preguntas son compuestas o ambiguas y una búsqueda única no alcanza.

**Complejidad a evitar:** introducir una base vectorial o memoria persistente sin una pregunta repetible que la búsqueda normal no resuelva.

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

**Regla:** empezá con SQLite + numpy. Migrá a pgvector cuando tengas PostgreSQL en producción — `examples/04_vector_store_pgvector.py` es esa migración corriendo, no solo el DDL.

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

## 6.8 Cuando el RAG básico no alcanza

El pipeline de 6.3 (embedding de la pregunta → top-k por coseno) falla de formas predecibles. Antes de agregar complejidad, identificá **cuál** de estas fallas tenés, midiendo con un set de preguntas con su documento esperado ([Módulo 10](../module-10-evals/README.md)):

| Síntoma | Causa | Técnica |
|---|---|---|
| "ERR_402", "SKU-991", `apply_discount()` no encuentran su documento | Los embeddings diluyen identificadores exactos | **Hybrid search** (6.9) |
| El documento correcto está en el top-20 pero no en el top-3 | El coseno mide "mismo tema", no "responde la pregunta" | **Reranking** (6.10) |
| Preguntas cortas recuperan peor que preguntas largas | Una pregunta y un párrafo de documentación viven lejos en el espacio vectorial | **HyDE** (6.11) |
| Costo y latencia altos con preguntas repetidas | Cada pregunta paga retrieval + LLM aunque ya se haya respondido | **Caché semántica** (6.12) |
| Preguntas con varias partes o que requieren encadenar búsquedas | Una sola búsqueda con la pregunta literal no puede cubrirlas | **Agentic RAG** (6.13) |

---

## 6.9 Hybrid search: léxico + semántico

**BM25** es el algoritmo clásico de búsqueda por palabras (el que usan Elasticsearch/OpenSearch). Premia los términos raros que aparecen en el documento: justo lo que un código de error necesita. Los embeddings, en cambio, encuentran sinónimos y paráfrasis. Cada uno cubre lo que el otro no ve.

El problema es combinarlos: BM25 devuelve scores de 0 a ∞ y el coseno de -1 a 1. **Reciprocal Rank Fusion (RRF)** ignora los scores y usa solo la posición:

```
score(doc) = Σ  1 / (k + posición_en_ranking_i)        k = 60
```

```python
lexical  = [d for d, _ in bm25.search(query, 20)]
semantic = [d for d, _ in dense.search(query, 20)]
top = reciprocal_rank_fusion([lexical, semantic])[:5]
```

Un documento que aparece arriba en **ambos** rankings sube; uno que solo aparece en uno sigue entrando. En producción no implementes BM25 a mano: Postgres tiene `tsvector`/`ts_rank` (junto a pgvector en la misma base), y Qdrant, Weaviate y OpenSearch soportan búsqueda híbrida nativa.

---

## 6.10 Reranking: recuperar mucho, reordenar poco

El embedding codifica la pregunta y el documento **por separado** y compara vectores: es rápido pero impreciso. Un **reranker** (cross-encoder o LLM) lee pregunta y documento **juntos** y juzga si uno responde al otro: es preciso pero caro. Se combinan en dos etapas:

```
retrieval (barato)          rerank (caro)            LLM
10.000 chunks ──top-20──→ 20 candidatos ──top-3──→ contexto
```

Opciones, de la más barata a la más cara: cross-encoder local (`sentence_transformers.CrossEncoder`, por ejemplo `BAAI/bge-reranker-base`), API de reranking administrada, o un LLM chico que puntúe todos los candidatos en **una** llamada (el `llm_scorer` del ejemplo). Si el reranker falla, mantené el orden de retrieval: no inventes uno.

---

## 6.11 HyDE: buscar con una respuesta, no con una pregunta

*Hypothetical Document Embeddings*: en vez de embeber "¿dónde se guardan las API keys?", se le pide a un LLM chico un párrafo que **respondería** la pregunta y se busca con ese texto. Un párrafo se parece más a otro párrafo que a una pregunta.

```python
query = hyde_query(question, claude_generator(client))   # pregunta + respuesta hipotética
results = hybrid.search(query)
```

La respuesta hipotética puede contener datos inventados: **se usa solo para buscar**, nunca se muestra al usuario ni se cita. Cuesta una llamada extra por pregunta; medí si la mejora de recuperación lo justifica.

---

## 6.12 Caché semántica

Una caché por string exacto no reconoce que "¿dónde están los secretos?" y "¿dónde se guardan las credenciales?" son la misma pregunta. Una caché semántica compara embeddings de preguntas y, si la similitud supera un umbral, devuelve la respuesta guardada sin llamar al LLM.

Es una de las optimizaciones con más riesgo si se diseña mal:

| Riesgo | Mitigación |
|---|---|
| **Falso hit:** "¿cómo cancelo el plan?" ≈ "¿cómo cambio el plan?" | Umbral alto (≥ 0.92), medido sobre pares reales de preguntas |
| **Fuga entre usuarios:** la respuesta de un tenant se sirve a otro | La clave incluye `scope` (tenant, usuario o rol) |
| **Respuesta vieja** tras actualizar documentos | TTL obligatorio + `invalidate()` al reindexar |

No la uses para preguntas que dependen del usuario o del momento ("¿cuál es mi saldo?"). Es distinta del *prompt caching* de Claude ([Módulo 3](../module-03-dev-workflows/README.md#35-prompt-caching-reducir-costos-en-60-90)): ese reutiliza el procesamiento de un prefijo idéntico; esta evita la llamada entera.

---

## 6.13 Agentic RAG

En el RAG clásico **el código** decide: busca una vez, con la pregunta literal. En agentic RAG **el modelo** decide si buscar, con qué query, si lo encontrado alcanza y cuándo parar. Es el loop del Módulo 1 con una sola herramienta:

```
"¿Qué pasa si falla un cobro con ERR_402 y dónde corre ese servicio?"
  → search_docs("ERR_402 reintentos")        ┐ en paralelo
  → search_docs("servicio procesamiento pagos deploy") ┘
  → responde citando [pagos-errores] [deploy]
```

| | RAG clásico | Agentic RAG |
|---|---|---|
| Llamadas al LLM | 1 | 2–5 |
| Preguntas compuestas | Mal | Bien |
| Reformula si no encuentra | No | Sí |
| Predecibilidad | Alta | Menor: necesita límite de búsquedas y evals |

Mismas reglas que cualquier agente: límite duro de búsquedas, `tool_result` con `is_error` cuando se alcanza (sin quitar la herramienta del request), y respuesta explícita de "no está en la documentación" cuando corresponde.

---

## 6.14 Otras variantes: GraphRAG y vectorless RAG

- **GraphRAG:** extrae entidades y relaciones de los documentos a un grafo de conocimiento y recupera recorriéndolo. Sirve para preguntas que conectan muchos documentos ("¿qué servicios dependen del módulo de pagos?") y para resúmenes globales del corpus. El costo de indexación es alto (un LLM procesa todo el corpus) y hay que mantener el grafo al día.
- **Vectorless RAG:** sin embeddings. El agente navega la estructura del corpus (índice, árbol de secciones, `grep`, `list_files`) con herramientas, igual que el agente del Módulo 3 explora un repo. Para código y documentación bien estructurada suele igualar o superar al RAG vectorial, sin infraestructura extra.

**Regla:** empezá por la opción más simple que pase tus evals. Para muchos casos de agentes de desarrollo, "darle `grep` y `read_file`" ya es RAG.

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Embeddings básicos](./EXAMPLES.md#ejemplo-1--embeddings-básicos-texto--vector--similitud) | "problema con cobro" encuentra "Error al procesar pago Visa" (sim: 0.81) sin compartir palabras |
| [02 — Pipeline RAG completo](./EXAMPLES.md#ejemplo-2--pipeline-rag-completo) | 5 docs indexados; preguntas fuera del dominio reciben "No tengo esa información" |
| [03 — Memoria semántica de episodios](./EXAMPLES.md#ejemplo-3--agente-con-memoria-semántica-de-episodios-pasados) | Nueva tarea encuentra episodios relevantes de cupones y descuentos anteriores |
| [04 — Vector store en pgvector](./EXAMPLES.md#ejemplo-4--vector-store-real-en-producción-pgvector) | El mismo RAG del ejemplo 02 corriendo contra Postgres+pgvector con índice `ivfflat` |
| [05 — Retrieval avanzado](./EXAMPLES.md#ejemplo-5--retrieval-avanzado-hybrid-rerank-hyde-caché-semántica) | `ERR_402` falla con dense y funciona con hybrid; rerank, HyDE y caché semántica con hits/misses |
| [06 — Agentic RAG](./EXAMPLES.md#ejemplo-6--agentic-rag-el-modelo-decide-qué-buscar) | Pregunta compuesta → 2 búsquedas en paralelo; pregunta fuera de dominio → "no está en la documentación" |

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
