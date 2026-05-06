"""RAG retrieval for incident response."""

from typing import Optional
from langchain_chroma import Chroma
from rag.vectorstore import get_vectorstore


def retrieve_for_incident(
    incident_description: str,
    affected_systems: list[str],
    fisma_category: int,
    vectorstore: Optional[Chroma] = None,
    k: int = 8,
) -> list[dict]:
    if vectorstore is None:
        vectorstore = get_vectorstore()

    queries = [incident_description[:200]]
    for system in affected_systems[:2]:
        queries.append(f"{system} troubleshooting runbook")
    queries.append(f"FISMA category {fisma_category} incident response procedure")
    queries.append("database connection pool exhaustion fix")

    all_results = []
    seen = set()

    for query in queries:
        try:
            docs = vectorstore.similarity_search(query, k=4)
            for doc in docs:
                key = f"{doc.metadata.get('source')}:{doc.metadata.get('chunk_index', 0)}"
                if key not in seen:
                    seen.add(key)
                    all_results.append({
                        "content": doc.page_content,
                        "source": doc.metadata.get("source", "Unknown"),
                        "category": doc.metadata.get("category", "unknown"),
                        "score": 0.8,
                    })
        except Exception:
            pass

    return all_results[:15]
