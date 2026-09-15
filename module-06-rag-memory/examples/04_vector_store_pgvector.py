"""
Módulo 6 — Ejemplo 4: Vector store real en producción (pgvector)

El ejemplo 02 usa SQLite + numpy: perfecto para desarrollo, pero no escala
a Redis+PostgreSQL en el que corre el proyecto final. Este ejemplo indexa
y consulta el MISMO tipo de contenido contra un pgvector real, así se puede
comparar directamente contra el pipeline SQLite del ejemplo 02.

Diferencia clave vs SQLite+numpy: acá la similitud coseno la calcula el
índice `ivfflat` de Postgres (ANN), no un loop en Python — es lo que te
permite escalar de miles a millones de vectores sin cambiar de arquitectura.

Requisitos:
    pip install anthropic sentence-transformers numpy psycopg[binary]

    # Levantar Postgres con pgvector (imagen oficial de la extensión)
    docker run -d --name pgvector-demo \
        -e POSTGRES_PASSWORD=demo -e POSTGRES_DB=rag_demo \
        -p 5432:5432 ankane/pgvector

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    export DATABASE_URL="postgresql://postgres:demo@localhost:5432/rag_demo"
    python 04_vector_store_pgvector.py
"""

import os
import textwrap

import anthropic
import psycopg
from sentence_transformers import SentenceTransformer

EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")  # 384 dimensiones
EMBED_DIM = 384
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
TOP_K = 3

client = anthropic.Anthropic()

DOCS = {
    "billing.md": """
        El sistema de facturación procesa pagos con Stripe. Cuando un cobro
        falla, se reintenta hasta 3 veces con backoff exponencial antes de
        marcar la suscripción como `past_due` y notificar al usuario.
    """,
    "auth.md": """
        La autenticación usa JWT de corta duración (15 min) más un refresh
        token de 30 días guardado en una cookie httpOnly. Los tokens se
        invalidan en el logout agregando su jti a una blocklist en Redis.
    """,
    "deploys.md": """
        Los deploys van por GitHub Actions: build, tests, y si todo pasa,
        un rolling deploy en Cloud Run con health checks antes de mover
        tráfico. Rollback automático si el health check falla 3 veces.
    """,
}


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = textwrap.dedent(text).strip()
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


def setup_pgvector(conn: psycopg.Connection) -> None:
    """Crea la extensión, la tabla y el índice ANN — solo corre una vez."""
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS doc_chunks (
            id SERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding vector({EMBED_DIM})
        )
    """)
    # ivfflat necesita filas para calibrar las listas; para datasets chicos
    # de demo alcanza, en producción se crea después de la carga inicial.
    conn.execute("""
        CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx
        ON doc_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 10)
    """)
    conn.commit()


def index_documents(conn: psycopg.Connection) -> None:
    conn.execute("TRUNCATE doc_chunks")
    for source, text in DOCS.items():
        for chunk in chunk_text(text):
            embedding = EMBED_MODEL.encode(chunk).tolist()
            conn.execute(
                "INSERT INTO doc_chunks (source, content, embedding) VALUES (%s, %s, %s)",
                (source, chunk, embedding),
            )
    conn.commit()
    count = conn.execute("SELECT count(*) FROM doc_chunks").fetchone()[0]
    print(f"Indexados {count} chunks de {len(DOCS)} documentos en pgvector.\n")


def retrieve(conn: psycopg.Connection, query: str, top_k: int = TOP_K) -> list[dict]:
    query_embedding = EMBED_MODEL.encode(query).tolist()
    # <=> es el operador de distancia coseno de pgvector: menor = más similar.
    rows = conn.execute(
        """
        SELECT source, content, 1 - (embedding <=> %s) AS similarity
        FROM doc_chunks
        ORDER BY embedding <=> %s
        LIMIT %s
        """,
        (query_embedding, query_embedding, top_k),
    ).fetchall()
    return [{"source": r[0], "content": r[1], "similarity": r[2]} for r in rows]


def answer(query: str, chunks: list[dict]) -> str:
    context = "\n\n".join(f"[{c['source']}] {c['content']}" for c in chunks)
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"Contexto:\n{context}\n\nPregunta: {query}\n\n"
                        "Respondé solo con lo que dice el contexto. Si no está, decilo.",
        }],
    )
    return response.content[0].text


if __name__ == "__main__":
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)
    setup_pgvector(conn)
    index_documents(conn)

    for query in [
        "¿qué pasa si falla un cobro?",
        "¿cómo se invalida una sesión?",
        "¿cuál es la política de precios de la empresa?",  # fuera del dominio
    ]:
        print(f"Query: {query}")
        chunks = retrieve(conn, query)
        for c in chunks:
            print(f"  [{c['similarity']:.2f}] {c['source']}")
        print(f"Respuesta: {answer(query, chunks)}\n")

    conn.close()
