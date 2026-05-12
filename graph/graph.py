"""
Incident Response Agent — LangGraph graph assembly.

Graph topology:
  triage_agent
       │
  rag_agent + tool_agent  (sequential — rag feeds hypothesis context)
       │
  generate_hypotheses_node
       │
  [Send() fan-out — parallel hypothesis investigation]
  investigate_hypothesis × N  (all run simultaneously)
       │
  synthesize_hypotheses_node  (collects parallel results)
       │
  blast_radius_agent
       │
  compliance_agent
       │
  cab_review_node         ← HUMAN-IN-THE-LOOP INTERRUPT
       │
       ├─[denied]──► END
       │
       └─[approved]──► action_agent
                              │
                        postmortem_agent
                              │
                             END

Key LangGraph features demonstrated:
  - Send() for parallel hypothesis investigation (map-reduce pattern)
  - interrupt_before for human CAB approval gate
  - operator.add for safe parallel state merging
  - MemorySaver checkpointing for durable incident investigation
"""

import os
import functools
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from graph.state import IncidentState
from agents.triage import triage_agent
from agents.tool_agent import tool_agent
from agents.hypothesis import (
    generate_hypotheses_node,
    investigate_hypothesis_node,
    synthesize_hypotheses_node,
    route_to_hypothesis_investigation,
)
from agents.react_investigation import (
    react_plan_node,
    react_execute_node,
    react_synthesize_node,
    route_investigation_mode,
    route_react_next,
)
from agents.blast_radius import blast_radius_agent
from agents.compliance import compliance_agent
from agents.action import action_agent
from agents.postmortem import postmortem_agent
from rag.vectorstore import ingest_knowledge_base


# ─── Node factory functions ───────────────────────────────────────────────────

def make_triage_node(llm):
    def node(state): return triage_agent(state, llm)
    node.__name__ = "triage_agent"
    return node

def make_rag_node(llm, vectorstore):
    from agents.rag_agent import rag_agent
    def node(state): return rag_agent(state, llm, vectorstore)
    node.__name__ = "rag_agent"
    return node

def make_tool_node(llm):
    def node(state): return tool_agent(state, llm)
    node.__name__ = "tool_agent"
    return node

def make_generate_hypotheses_node(llm):
    def node(state): return generate_hypotheses_node(state, llm)
    node.__name__ = "generate_hypotheses"
    return node

def make_investigate_hypothesis_node(llm):
    def node(state): return investigate_hypothesis_node(state, llm)
    node.__name__ = "investigate_hypothesis"
    return node

def make_synthesize_node(llm):
    def node(state): return synthesize_hypotheses_node(state, llm)
    node.__name__ = "synthesize_hypotheses"
    return node

def make_react_plan_node(llm):
    def node(state): return react_plan_node(state, llm)
    node.__name__ = "react_plan"
    return node

def make_react_execute_node(llm, vectorstore):
    def node(state): return react_execute_node(state, llm, vectorstore)
    node.__name__ = "react_execute"
    return node

def make_react_synthesize_node(llm):
    def node(state): return react_synthesize_node(state, llm)
    node.__name__ = "react_synthesize"
    return node

def make_blast_radius_node(llm):
    def node(state): return blast_radius_agent(state, llm)
    node.__name__ = "blast_radius_agent"
    return node

def make_compliance_node(llm):
    def node(state): return compliance_agent(state, llm)
    node.__name__ = "compliance_agent"
    return node

def make_action_node(llm):
    def node(state): return action_agent(state, llm)
    node.__name__ = "action_agent"
    return node

def make_postmortem_node(llm):
    def node(state): return postmortem_agent(state, llm)
    node.__name__ = "postmortem_agent"
    return node


# ─── Human review node ────────────────────────────────────────────────────────

def cab_review_node(state: IncidentState) -> dict[str, Any]:
    """
    Human-in-the-Loop: Change Advisory Board review gate.

    LangGraph pauses here via interrupt_before=["cab_review_node"].
    The Streamlit UI presents the full investigation package.
    CAB reviewer approves or denies the remediation plan.
    """
    cab_status = state.get("cab_status", "pending")
    print(f"[CAB Review Node] Status: {cab_status}")
    return {"current_node": "cab_review_node"}


def route_after_cab(state: IncidentState) -> str:
    """Route after CAB review — approved → action, denied → END."""
    if state.get("cab_status") == "approved":
        return "action_agent"
    return END


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_graph(
    openai_api_key: str | None = None,
    tavily_api_key: str | None = None,
    model: str = "gpt-4o",
    temperature: float = 0.0,
    force_reingest: bool = False,
    enable_checkpointing: bool = True,
) -> tuple[Any, MemorySaver | None]:
    """
    Build and compile the Incident Response Agent LangGraph.

    Returns (compiled_graph, checkpointer).
    """
    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key
    if tavily_api_key:
        os.environ["TAVILY_API_KEY"] = tavily_api_key

    # LangSmith tracing
    if os.environ.get("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", "incident-response-agent")
        print("[Graph] LangSmith tracing enabled.")

    # Initialize LLM
    llm = ChatOpenAI(model=model, temperature=temperature)

    # Initialize RAG
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = ingest_knowledge_base(embeddings=embeddings, force_reingest=force_reingest)

    # Build nodes
    workflow = StateGraph(IncidentState)

    workflow.add_node("triage_agent",          make_triage_node(llm))
    workflow.add_node("rag_agent",             make_rag_node(llm, vectorstore))
    workflow.add_node("tool_agent",            make_tool_node(llm))
    workflow.add_node("generate_hypotheses",   make_generate_hypotheses_node(llm))
    workflow.add_node("investigate_hypothesis", make_investigate_hypothesis_node(llm))
    workflow.add_node("synthesize_hypotheses", make_synthesize_node(llm))

    # ReAct iterative-investigation mode (parallel + react paths converge at blast_radius)
    workflow.add_node("react_plan",            make_react_plan_node(llm))
    workflow.add_node("react_execute",         make_react_execute_node(llm, vectorstore))
    workflow.add_node("react_synthesize",      make_react_synthesize_node(llm))

    workflow.add_node("blast_radius_agent",    make_blast_radius_node(llm))
    workflow.add_node("compliance_agent",      make_compliance_node(llm))
    workflow.add_node("cab_review_node",       cab_review_node)
    workflow.add_node("action_agent",          make_action_node(llm))
    workflow.add_node("postmortem_agent",      make_postmortem_node(llm))

    # Entry point
    workflow.set_entry_point("triage_agent")

    # Linear: triage → rag → [mode router]
    workflow.add_edge("triage_agent", "rag_agent")

    # Mode router: pick the parallel map-reduce path OR the ReAct iterative path
    workflow.add_conditional_edges(
        "rag_agent",
        route_investigation_mode,
        {"tool_agent": "tool_agent", "react_plan": "react_plan"},
    )

    # ── PARALLEL path ────────────────────────────────────────────────────────
    workflow.add_edge("tool_agent", "generate_hypotheses")

    # Fan-out: generate_hypotheses → [investigate_hypothesis × N] via Send()
    workflow.add_conditional_edges(
        "generate_hypotheses",
        route_to_hypothesis_investigation,
        ["investigate_hypothesis", "synthesize_hypotheses"],
    )

    # Fan-in: all investigate_hypothesis → synthesize_hypotheses
    workflow.add_edge("investigate_hypothesis", "synthesize_hypotheses")

    # Parallel path joins blast_radius
    workflow.add_edge("synthesize_hypotheses", "blast_radius_agent")

    # ── REACT path ───────────────────────────────────────────────────────────
    # react_plan → conditional → react_execute (loop) OR react_synthesize
    workflow.add_conditional_edges(
        "react_plan",
        route_react_next,
        {"react_execute": "react_execute", "react_synthesize": "react_synthesize"},
    )
    # After a tool call, loop back to plan
    workflow.add_edge("react_execute", "react_plan")
    # When the agent submits, synthesize → joins parallel path at blast_radius
    workflow.add_edge("react_synthesize", "blast_radius_agent")

    # ── Both paths converged at blast_radius from here on ───────────────────
    workflow.add_edge("blast_radius_agent", "compliance_agent")
    workflow.add_edge("compliance_agent", "cab_review_node")

    # CAB → action or END
    workflow.add_conditional_edges(
        "cab_review_node",
        route_after_cab,
        {"action_agent": "action_agent", END: END},
    )

    # action → postmortem → END
    workflow.add_edge("action_agent", "postmortem_agent")
    workflow.add_edge("postmortem_agent", END)

    # Compile
    checkpointer = None
    if enable_checkpointing:
        checkpointer = MemorySaver()
        compiled = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["cab_review_node"],
        )
    else:
        compiled = workflow.compile()

    print("[Graph] Incident Response Agent graph compiled.")
    print("[Graph] Modes: parallel (default) → tool_agent + Send() fan-out; react → iterative ReAct loop.")
    print("[Graph] Common downstream: blast_radius → compliance → CAB(interrupt) → action → postmortem")

    return compiled, checkpointer


def run_graph(
    graph,
    incident_description: str,
    system_name: str,
    incident_id: str,
    detection_time: str,
    reported_by: str = "On-call engineer",
    raw_logs: str = "",
    thread_id: str = "incident-1",
    investigation_mode: str = "parallel",
    react_budget: int = 6,
) -> dict[str, Any]:
    """
    Start a graph run and return state after CAB interrupt.

    Parameters
    ----------
    investigation_mode : "parallel" (default — Send() fan-out across all 3 tools)
                         or "react" (iterative ReAct loop with dynamic tool choice).
    react_budget       : Max tool calls before forced submit in ReAct mode.
    """
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: IncidentState = {
        "incident_id": incident_id,
        "incident_description": incident_description,
        "system_name": system_name,
        "detection_time": detection_time,
        "reported_by": reported_by,
        "raw_logs": raw_logs,
        "cab_status": "pending",
        "hypotheses": [],
        "rag_results": [],
        "errors": [],
        "messages": [],
        "audit_log": [],
        "current_node": "start",
        # ReAct-mode bootstrap (no-op for parallel mode)
        "investigation_mode": investigation_mode,
        "react_actions": [],
        "react_step": 0,
        "react_budget": react_budget,
        "react_next_action": {},
        "react_complete": False,
    }

    return graph.invoke(initial_state, config=config)
