"""
RAG Agent — search runbooks, past incidents, and NIST 800-61 controls.
"""

from typing import Any
from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from langchain.schema import HumanMessage, SystemMessage

from graph.state import IncidentState
from rag.retriever import retrieve_for_incident


def rag_agent(state: IncidentState, llm: ChatOpenAI, vectorstore: Chroma) -> dict[str, Any]:
    print("[RAG Agent] Searching runbooks and past incidents...")

    results = retrieve_for_incident(
        incident_description=state.get("incident_description", ""),
        affected_systems=state.get("affected_systems", []),
        fisma_category=state.get("fisma_category", 2),
        vectorstore=vectorstore,
    )

    if not results:
        return {
            "rag_results": [],
            "rag_summary": "No relevant runbooks or past incidents found.",
            "current_node": "rag_agent",
        }

    runbooks = [r for r in results if r.get("category") == "runbook"]
    past_incidents = [r for r in results if r.get("category") == "past_incident"]

    try:
        retrieved_text = "\n\n---\n\n".join(
            f"[{r['category'].upper()} | {r['source']}]\n{r['content']}"
            for r in results[:8]
        )
        response = llm.invoke([
            SystemMessage(content="You are an SRE reviewing runbooks and past incidents."),
            HumanMessage(content=(
                f"Incident: {state.get('incident_description', '')}\n\n"
                f"Relevant knowledge base content:\n{retrieved_text}\n\n"
                f"In 2-3 paragraphs: what runbooks apply? Any similar past incidents? Key guidance?"
            )),
        ])
        rag_summary = response.content.strip()
    except Exception as e:
        rag_summary = f"Found {len(runbooks)} runbooks and {len(past_incidents)} similar past incidents."

    print(f"[RAG Agent] {len(results)} results: {len(runbooks)} runbooks, {len(past_incidents)} past incidents")

    return {
        "rag_results": results,
        "relevant_runbooks": runbooks,
        "similar_incidents": past_incidents,
        "rag_summary": rag_summary,
        "current_node": "rag_agent",
    }
