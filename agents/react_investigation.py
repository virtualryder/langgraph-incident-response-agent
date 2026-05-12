"""
ReAct Investigation Agent — iterative, dynamic tool-calling pattern.

This is the second investigation mode alongside the parallel hypothesis pattern.
Where the parallel mode fans out to N investigators in lockstep over a pre-
fetched evidence pack, ReAct mode lets the agent **dynamically choose** which
tool to call next based on what it has already learned. The loop continues
until the agent submits a root-cause hypothesis or runs out of budget.

Why expose this as a second mode rather than replacing the parallel one?
The two patterns shine in different scenarios:

  • Parallel — best for "everything is on fire" major incidents where the
    investigation must cover several angles simultaneously and time-to-answer
    is the binding constraint. Mirrors how real SRE teams split into tracks.

  • ReAct — best for tier-1 SOC triage where a single alert needs to be
    refined into a verdict and unnecessary tool calls cost money / time.
    The agent commits to a line of investigation, follows the evidence,
    and stops when it has enough.

Architecture (this file plus graph wiring in graph/graph.py):

    react_plan_node          ◄────────────────┐
       │   (LLM picks next action via         │
       │    Pydantic structured output)        │
       │                                       │
       ▼ conditional (route_react_next)        │
       ├── submit  → react_synthesize_node    │
       └── tool    → react_execute_node ───────┘  (loop back)

Bounded by `react_budget` (default 6 tool calls) to prevent runaway loops.
The conditional router also force-submits when budget is exhausted.

Tool surface available to the agent:
  - query_github      — recent commits, open issues, PRs
  - query_cloudwatch  — alarms, metric timelines
  - query_splunk      — error patterns, log timeline
  - search_runbooks   — RAG over runbooks + past incidents
  - submit            — terminal action; commits a root-cause hypothesis
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal, Optional

# Use langchain_core.messages (forward-compatible across LangChain 0.3.x → 1.x).
# Older modules in this project use `from langchain.schema import ...`; that
# path is a deprecated shim that was removed in newer LangChain versions.
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from graph.state import IncidentState
from tools.cloudwatch_tool import query_cloudwatch as cw_query
from tools.github_tool import query_github as gh_query
from tools.splunk_tool import query_splunk as sp_query


# ── Default budget — overridable via state["react_budget"] ──────────────────

DEFAULT_REACT_BUDGET = 6


# ── Pydantic schemas for structured plan output ─────────────────────────────

class ReActAction(BaseModel):
    """The agent's decision on what to do next."""

    action: Literal[
        "query_github",
        "query_cloudwatch",
        "query_splunk",
        "search_runbooks",
        "submit",
    ] = Field(description="Which tool to call next, or 'submit' to commit a root cause.")

    focus: str = Field(
        default="",
        description=(
            "For query_* actions: a short focus phrase (5-15 words) describing what "
            "aspect of that tool's data to look at. For example: "
            "'recent timeout config changes' or 'DatabaseConnections alarm history'."
        ),
    )

    rationale: str = Field(
        description="One sentence: why this action is the right next step given what is already known."
    )

    # Fields populated only when action == "submit":
    submitted_title: Optional[str] = Field(
        default=None,
        description="Root-cause hypothesis title — required when action == 'submit'.",
    )
    submitted_category: Optional[str] = Field(
        default=None,
        description="One of: infrastructure, application, network, security, human_error, dependency.",
    )
    submitted_confidence: Optional[int] = Field(
        default=None, ge=0, le=100,
        description="Final confidence in the submitted hypothesis (0-100).",
    )
    submitted_supporting_evidence: list[str] = Field(default_factory=list)
    submitted_contradicting_evidence: list[str] = Field(default_factory=list)
    submitted_next_step: Optional[str] = Field(
        default=None,
        description="What action would confirm this root cause (e.g., 'check application.properties').",
    )


# ── Plan prompt ─────────────────────────────────────────────────────────────

PLAN_SYSTEM = """You are an SRE running a ReAct-style incident investigation.

You have access to FOUR investigation tools and ONE terminal action:

  TOOLS (call as many as you need, ONE AT A TIME):
    • query_github       — find recent commits, open issues, hotfix PRs related to the incident
    • query_cloudwatch   — pull alarm history, metric timelines
    • query_splunk       — search error patterns, log timelines
    • search_runbooks    — retrieve runbook excerpts + past incidents from the knowledge base

  TERMINAL ACTION:
    • submit             — commit a root-cause hypothesis with supporting evidence

Loop instructions:
  1. Look at the incident description, FISMA context, RAG context, and any evidence
     you've already gathered.
  2. Decide what is the SINGLE highest-value next investigation step.
  3. If you already have enough evidence to commit to a root cause, choose 'submit'.
  4. Otherwise choose one of the four query_* tools and provide a short 'focus' phrase
     describing exactly what to look at.

Guidance:
  - Pick the tool whose data is most likely to confirm or rule out your leading hypothesis.
  - Do NOT call the same tool twice with the same focus. If a tool already returned what
    you needed, move on.
  - You have a bounded budget. Submit as soon as the evidence is strong enough — do not
    keep investigating once you are confident.
  - When you submit, supporting_evidence must be specific (cite the chart entries / logs
    / commit hashes you saw). Vague claims are not useful.
  - Categories: infrastructure | application | network | security | human_error | dependency.

Return ONE ReActAction object per turn.
"""


PLAN_USER_TEMPLATE = """INCIDENT: {incident_description}
SYSTEM: {system_name}
FISMA CATEGORY: {fisma_category_name}
DETECTION TIME: {detection_time}

RUNBOOK / PAST INCIDENT CONTEXT:
{rag_summary}

EVIDENCE GATHERED SO FAR ({steps_completed}/{budget} steps used):
{evidence_trail}

Decide the next action. If you have enough evidence to commit to a root cause, choose 'submit'.
"""


def _format_trail(actions: list[dict]) -> str:
    """Pretty-print the accumulated ReAct trail for the next plan prompt."""
    if not actions:
        return "  (no investigation steps yet — this is your first turn)"
    lines: list[str] = []
    for a in actions:
        lines.append(
            f"  Step {a.get('step')}: {a.get('action')} (focus: \"{a.get('focus','')}\")"
        )
        lines.append(f"    Rationale: {a.get('rationale','')}")
        lines.append(f"    Finding: {a.get('finding_summary','')[:300]}")
        if a.get("anomalies"):
            lines.append(f"    Anomalies: {'; '.join(a['anomalies'][:3])}")
    return "\n".join(lines)


# ── Plan node ───────────────────────────────────────────────────────────────

def react_plan_node(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LLM decides the next investigation step via structured output.

    Writes `react_next_action` (a dict). The conditional edge router reads it
    and routes either to react_execute (for tool calls) or react_synthesize
    (for submit / budget-exhausted).
    """
    budget = state.get("react_budget") or DEFAULT_REACT_BUDGET
    step = state.get("react_step", 0)
    actions = state.get("react_actions", [])

    print(f"[ReAct Plan] Turn {step + 1} / {budget}")

    # If we've already used the budget, force a submit on the next router pass.
    if step >= budget:
        forced = {
            "action": "submit",
            "focus": "",
            "rationale": f"Budget exhausted ({step}/{budget} steps). Forcing commit on best available evidence.",
            "submitted_title": "Inconclusive — budget exhausted",
            "submitted_category": "unknown",
            "submitted_confidence": 40,
            "submitted_supporting_evidence": [
                f"Step {a['step']}: {a.get('finding_summary','')[:120]}"
                for a in actions
            ],
            "submitted_contradicting_evidence": [],
            "submitted_next_step": "Continue investigation manually; agent budget was exhausted.",
        }
        return {
            "react_next_action": forced,
            "current_node": "react_plan",
        }

    user = PLAN_USER_TEMPLATE.format(
        incident_description=state.get("incident_description", ""),
        system_name=state.get("system_name", "Unknown"),
        fisma_category_name=state.get("fisma_category_name", "Unknown"),
        detection_time=state.get("detection_time", "unknown"),
        rag_summary=state.get("rag_summary", "No runbook data available")[:1500],
        evidence_trail=_format_trail(actions),
        steps_completed=step,
        budget=budget,
    )

    try:
        structured_llm = llm.with_structured_output(ReActAction)
        plan: ReActAction = structured_llm.invoke([
            SystemMessage(content=PLAN_SYSTEM),
            HumanMessage(content=user),
        ])
        next_action = plan.model_dump()
    except Exception as exc:
        print(f"[ReAct Plan] Planner error: {exc}; forcing submit.")
        next_action = {
            "action": "submit",
            "focus": "",
            "rationale": f"Planner error: {exc}",
            "submitted_title": "Inconclusive — planner error",
            "submitted_category": "unknown",
            "submitted_confidence": 30,
            "submitted_supporting_evidence": [],
            "submitted_contradicting_evidence": [],
            "submitted_next_step": "Re-run investigation; LLM planner failed.",
        }

    print(
        f"[ReAct Plan] Decision: {next_action['action']} "
        f"(focus: '{next_action.get('focus','')[:60]}')"
    )

    return {
        "react_next_action": next_action,
        "current_node": "react_plan",
    }


# ── Execute node ────────────────────────────────────────────────────────────

def react_execute_node(state: IncidentState, llm: ChatOpenAI, vectorstore) -> dict[str, Any]:
    """
    Run the tool the planner picked and append the finding to the trail.
    Increments `react_step` so the budget gate works.
    """
    plan = state.get("react_next_action") or {}
    action = plan.get("action", "")
    focus = plan.get("focus", "")
    rationale = plan.get("rationale", "")

    step = state.get("react_step", 0) + 1
    incident_description = state.get("incident_description", "")
    system_name = state.get("system_name", "Unknown")
    affected = state.get("affected_systems", [])
    detection_time = state.get("detection_time")

    finding_summary = ""
    anomalies: list[str] = []
    tool_result: dict = {}

    try:
        if action == "query_github":
            tool_result = gh_query(
                f"{incident_description}\nFocus: {focus}", affected
            )
            finding_summary = tool_result.get("summary", "")
            anomalies = tool_result.get("anomalies", []) or []

        elif action == "query_cloudwatch":
            tool_result = cw_query(
                system_name, f"{incident_description}\nFocus: {focus}", detection_time
            )
            finding_summary = tool_result.get("summary", "")
            anomalies = tool_result.get("anomalies", []) or []

        elif action == "query_splunk":
            tool_result = sp_query(
                f"{incident_description}\nFocus: {focus}", affected, detection_time
            )
            finding_summary = tool_result.get("summary", "")
            anomalies = tool_result.get("anomalies", []) or []

        elif action == "search_runbooks":
            # Use the same Chroma vectorstore the RAG agent uses. The agent
            # may call this redundantly; that's fine — it gets a focused slice.
            if vectorstore is not None:
                results = vectorstore.similarity_search(focus or incident_description, k=4)
                finding_summary = "\n".join(
                    f"- {doc.page_content[:300]}" for doc in results
                ) or "(no relevant runbook content found)"
                anomalies = []
            else:
                finding_summary = "Runbook search unavailable (no vectorstore)."

        else:
            # Defensive: should never reach here because the router only
            # sends real tools to this node.
            finding_summary = f"Unknown action: {action}"
            anomalies = []

    except Exception as exc:
        finding_summary = f"Tool error: {exc}"
        anomalies = []

    trail_entry = {
        "step": step,
        "action": action,
        "focus": focus,
        "rationale": rationale,
        "finding_summary": finding_summary[:1200],
        "anomalies": anomalies[:5],
        "timestamp": datetime.now().isoformat(),
    }

    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "node": "react_execute",
        "action": f"react_tool_{action}",
        "details": f"Step {step}: focus='{focus[:60]}', anomalies={len(anomalies)}",
    }

    print(
        f"[ReAct Execute] Step {step} {action} → "
        f"{len(anomalies)} anomalies; "
        f"summary ({len(finding_summary)} chars)"
    )

    return {
        "react_actions": [trail_entry],
        "react_step": step,
        "current_node": "react_execute",
        "audit_log": [audit_entry],
    }


# ── Synthesize node — converts submitted action into the standard state shape ──

def react_synthesize_node(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    Convert the agent's submitted hypothesis into the same `top_hypothesis` /
    `ranked_hypotheses` shape the parallel path produces, so downstream nodes
    (blast_radius, compliance, CAB) need no changes.
    """
    plan = state.get("react_next_action") or {}
    actions = state.get("react_actions", [])

    title = plan.get("submitted_title") or "Inconclusive"
    category = plan.get("submitted_category") or "unknown"
    confidence = int(plan.get("submitted_confidence") or 50)
    supporting = list(plan.get("submitted_supporting_evidence") or [])
    contradicting = list(plan.get("submitted_contradicting_evidence") or [])
    next_step = plan.get("submitted_next_step") or "Confirm via manual review."

    hypothesis = {
        "id": "R1",
        "title": title,
        "category": category,
        "confidence": confidence,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "next_investigation_step": next_step,
        "source": "react_investigation",
        "status": "probable" if confidence >= 70 else "investigating",
    }

    # Narrative summary the operator pane displays alongside the trail.
    summary_lines: list[str] = [
        f"ReAct agent ran {len(actions)} investigation step(s) and committed to a root cause.",
        f"Top hypothesis: \"{title}\" ({confidence}% confidence, category: {category}).",
    ]
    if supporting:
        summary_lines.append(
            "Supporting evidence: " + "; ".join(s[:120] for s in supporting[:3])
        )
    if contradicting:
        summary_lines.append(
            "Contradicting evidence: " + "; ".join(c[:120] for c in contradicting[:3])
        )

    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "node": "react_synthesize",
        "action": "react_root_cause_submitted",
        "details": (
            f"Title: \"{title}\" | Confidence: {confidence}% | "
            f"Steps: {len(actions)} | Supporting: {len(supporting)} | "
            f"Contradicting: {len(contradicting)}"
        ),
    }

    print(
        f"[ReAct Synthesize] Top: \"{title}\" "
        f"({confidence}% confidence, {len(actions)} steps)"
    )

    return {
        "top_hypothesis": hypothesis,
        "ranked_hypotheses": [hypothesis],
        "hypothesis_summary": "\n".join(summary_lines),
        "react_summary": "\n".join(summary_lines),
        "react_complete": True,
        "current_node": "react_synthesize",
        "audit_log": [audit_entry],
    }


# ── Routers ─────────────────────────────────────────────────────────────────

def route_investigation_mode(state: IncidentState) -> str:
    """
    Routing function attached after rag_agent: pick the investigation path.
    Defaults to "parallel" for backward compatibility.
    """
    mode = state.get("investigation_mode") or "parallel"
    if mode == "react":
        return "react_plan"
    return "tool_agent"


def route_react_next(state: IncidentState) -> str:
    """
    Routing function attached after react_plan: tool call vs submit vs forced.

    The plan node ensures budget enforcement by emitting `action="submit"`
    when step >= budget, so this router just reads the planner's choice.
    """
    plan = state.get("react_next_action") or {}
    action = plan.get("action", "")
    if action == "submit":
        return "react_synthesize"
    if action in ("query_github", "query_cloudwatch", "query_splunk", "search_runbooks"):
        return "react_execute"
    # Defensive: unknown action → submit to keep the graph terminating.
    return "react_synthesize"
