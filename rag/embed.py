"""Builds a local Chroma index over course descriptions + prerequisite text,
plus prose policy pages (e.g. gen-ed requirements), for the fuzzy
natural-language questions the structured functions in agent/tools.py can't
answer (e.g. "what's a good intro course for AI", "what counts as a
social-science gen-ed").

Embeddings are local and free (sentence-transformers), not an API call - no
per-run cost, works offline once the model is downloaded once.

Usage: python -m rag.embed
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

DATA_DIR = Path(__file__).parent.parent / "data"
CHROMA_DIR = DATA_DIR / "chroma"
MODEL_NAME = "all-mpnet-base-v2"

# UNC's Focus Capacity category names don't share vocabulary with how a
# student would naturally ask about them (e.g. "Power and Society" vs.
# "social science") - the local embedding model doesn't bridge that gap on
# its own (confirmed: "quantitative reasoning" retrieves correctly since it
# shares wording with the category name; "social science" didn't, before
# this map). Only "Power and Society" is grounded in UNC's own published
# category description (ideasinaction.unc.edu/focus-capacities/power-society/
# - "social, economic, and political systems... inequalities"); the rest are
# inferred from the category name itself, not independently verified against
# each category's own page - flagged here so that's not mistaken for a
# citation of UNC's language.
CATEGORY_ALIASES = {
    "Aesthetic and Interpretive Analysis": "arts, humanities, literature, visual arts, aesthetics, art history",
    "Creative Expression, Practice, and Production": "creative arts, studio art, music, creative writing, performance, theater",
    "Engagement with the Human Past": "history",
    "Ethical and Civic Values": "ethics, philosophy, civics, moral philosophy",
    "Global Understanding and Engagement": "global studies, international studies, cultural studies, world cultures",
    "Natural Scientific Investigation": "natural science, biology, chemistry, physics, earth science",
    "Power and Society": "social science, sociology, political science, economics, social and political inequality",
    "Quantitative Reasoning": "math, statistics, quantitative, data",
    "Ways of Knowing": "philosophy, epistemology, logic",
}


def _with_aliases(text: str) -> str:
    for category, aliases in CATEGORY_ALIASES.items():
        if category in text:
            return f"{text}\n(Also commonly searched as: {aliases})"
    return text


def _course_documents() -> tuple[list[str], list[str], list[dict]]:
    ids, documents, metadatas = [], [], []
    for path in (DATA_DIR / "courses").glob("*.json"):
        for course in json.loads(path.read_text()):
            text = f"{course['code']}: {course['title']}\n{course['description']}"
            if course["requisites_text"]:
                text += f"\nRequisites: {course['requisites_text']}"

            ids.append(course["code"])
            documents.append(text)
            metadatas.append(
                {
                    "type": "course",
                    "code": course["code"],
                    "title": course["title"],
                    "credits": course["credits"] or 0,
                }
            )
    return ids, documents, metadatas


def _policy_documents() -> tuple[list[str], list[str], list[dict]]:
    ids, documents, metadatas = [], [], []
    for path in (DATA_DIR / "policy").glob("*.json"):
        page_slug = path.stem
        for i, chunk in enumerate(json.loads(path.read_text())):
            ids.append(f"{page_slug}::{i}::{chunk['heading'][:40]}")
            documents.append(_with_aliases(f"{chunk['heading']}\n{chunk['text']}"))
            metadatas.append({"type": "policy", "heading": chunk["heading"], "url": chunk["url"]})
    return ids, documents, metadatas


def build_index() -> None:
    course_ids, course_docs, course_meta = _course_documents()
    policy_ids, policy_docs, policy_meta = _policy_documents()
    ids = course_ids + policy_ids
    documents = course_docs + policy_docs
    metadatas = course_meta + policy_meta

    print(f"Embedding {len(course_docs)} courses + {len(policy_docs)} policy chunks with {MODEL_NAME}...")

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(documents, show_progress_bar=True).tolist()

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if "courses" in [c.name for c in client.list_collections()]:
        client.delete_collection("courses")
    # Chroma defaults to L2 distance, which ranks poorly for
    # sentence-transformer embeddings - cosine is the right metric here
    # (confirmed empirically: a chunk with cosine distance 0.63 to a test
    # query wasn't appearing in L2 top-6 results at all, beaten out by
    # chunks with cosine distance >1.0).
    collection = client.create_collection("courses", metadata={"hnsw:space": "cosine"})
    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    print(f"Indexed {collection.count()} documents into {CHROMA_DIR}")


if __name__ == "__main__":
    build_index()
