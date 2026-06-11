"""
Módulo 6 — Ejemplo 1: Embeddings básicos y similitud coseno

Demuestra:
- Generar embeddings con sentence-transformers (local, sin costo)
- Calcular similitud coseno entre textos
- Por qué la búsqueda semántica supera a la búsqueda por keywords

Requisitos:
    pip install sentence-transformers numpy

Uso:
    python 01_embeddings_basic.py
"""

import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")  # ~80MB, se descarga una vez


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def embed(text: str) -> np.ndarray:
    return model.encode(text, normalize_embeddings=True)


if __name__ == "__main__":
    # Episodio guardado en memoria del agente
    stored_episode = "Error al procesar pago con tarjeta Visa en el checkout"

    queries = [
        "problema con cobro de crédito",          # semánticamente similar, palabras distintas
        "falla en el procesamiento de tarjetas",   # similar
        "issue con el método de pago",             # similar
        "error de conexión al servidor de base de datos",  # diferente
        "bug en el módulo de autenticación",       # diferente
    ]

    stored_vec = embed(stored_episode)

    print(f"Episodio almacenado:\n  '{stored_episode}'\n")
    print("Similitud con queries:")
    print("-" * 60)

    for q in queries:
        sim = cosine_similarity(stored_vec, embed(q))
        bar = "█" * int(sim * 30)
        marker = "← RELEVANTE" if sim > 0.5 else ""
        print(f"  {sim:.3f} {bar:<30} '{q}' {marker}")

    print()
    print("Conclusión: búsqueda semántica encuentra contexto relevante")
    print("sin necesidad de keywords exactas.")
