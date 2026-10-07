"""Queries the Chroma course index built by rag/embed.py."""

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from rag.embed import CHROMA_DIR, MODEL_NAME

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def search(question: str, k: int = 5) -> list[dict]:
    if not Path(CHROMA_DIR).exists():
        raise RuntimeError("No index found - run `python -m rag.embed` first")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection("courses")

    query_embedding = _get_model().encode([question]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=k)

    return [
        {"metadata": meta, "document": doc, "distance": dist}
        for meta, doc, dist in zip(
            results["metadatas"][0], results["documents"][0], results["distances"][0]
        )
    ]
