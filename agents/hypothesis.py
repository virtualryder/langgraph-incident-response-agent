"""
Hypothesis Agent — parallel root cause investigation via LangGraph Send().

This is the most architecturally distinctive node in the graph.

Instead of investigating one hypothesis at a time, the graph:
  1. generate_hypotheses_node: LLM generates 4-5 competing hypotheses
  2. LangGraph routes each hypothesis to investigate_hypothesis_node via Send()
  3. All hypothesis investigations run in PARALLEL
  4. synthesize_hypotheses_node: collects all results, ranks by confidence

This mirrors how real SRE teams work: split into subgroups, each investigates
a different angle, then reconvene with findings.

LangGraph Send() API: https://langchain-ai.github.io/langgraph/how-tos/map-reduce/
"""

import json
import re
from datetime import datetime
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langgraph.types import Send

from graph.state import IncidentState, Hypothesis


GENERATE_HYPOTHESES_PROMPT = """You are a principal SRE investigating a production incident.
Generate 4-5 competing root cause hypotheses. Be specific — generic hypotheses like
"server overload" are not useful. Name the exact mechanism.

INCIDENT: {incident_description}
SYSTEM: {system_name}
FISMA CATEGORY: {fisma_category_name}

TOOL EVIDENCE SUMMARY:
{tool_summary}

RELEVANT RUNBOOK/PAST INCIDENT CONTEXT:
{rag_summary}

Generate 4-5 hypotheses. For each, identify what evidence you would need to confirm or rule it out.

Return JSON array:
[
  {{
    "id": "H1",
    "title": "HikariCP connection pool undersized for Monday surge load",
    "category": "application",
    "initial_confidence": 75,
    "key_evidence_needed": "HikariCP pool stats showing total=max and idle=0",
    "quick_check": "grep 'HikariPool' logs for pool stats"
  }}
]
"""

INVESTIGATE_HYPOTHESIS_PROMPT = """You are an SRE investigating a specific root cause hypothesis.
Evaluate this hypothesis against the available evidence. Be a rigorous thinker:
weigh both supporting AND contradicting evidence. Do not confirm a hypothesis just because
some evidence is consistent — look for what would disprove it.

HYPOTHESIS: {hypothesis_title}
CATEGORY: {hypothesis_category}

GITHUB EVIDENCE:
{github_evidence}

CLOUDWATCH EVIDENCE:
{cloudwatch_evidence}

SPLUNK EVIDENCE:
{splunk_evidence}

RUNBOOK/PAST INCIDENT CONTEXT:
{rag_context}

Evaluate this hypothesis. Return JSON:
{{
  "id": "{hypothesis_id}",
  "title": "{hypothesis_title}",
  "category": "{hypothesis_category}",
  "confidence": 85,
  "status": "probable",
  "supporting_evidence": [
    "HikariPool stats show total=10, active=10, idle=0 — pool maxed",
    "Splunk error: 'Connection is not available, request timed out after 30000ms'",
    "GitHub commit a4f2c91 changed timeout 5s→30s without increasing pool size"
  ],
  "contradicting_evidence": [
    "RDS CPU only at 78%, not maxed — database has capacity, bottleneck is connections"
  ],
  "next_investigation_step": "Confirm by checking hikari.maximumPoolSize in deployed application.properties",
  "source": "synthesis"
}}

Status must be one of: confirmed | probable | possible | ruled_out | investigating
"""

SYNTHESIZE_HYPOTHESES_PROMPT = """You are the incident commander reviewing all investigated hypotheses.
Rank them by confidence and identify the most likely root cause.

INCIDENT: {incident_description}

INVESTIGATED HYPOTHESES:
{hypotheses_json}

Return JSON:
{{
  "top_hypothesis_id": "H1",
  "ranked_ids": ["H1", "H3", "H2", "H4"],
  "hypothesis_summary": "3-4 sentence narrative explaining the ranking and what the evidence collectively shows",
  "confidence_in_top": 92,
  "alternative_worth_monitoring": "H3 — if fix doesn't resolve, investigate this next"
}}
"""


def generate_hypotheses_node(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Generate competing hypotheses.

    Returns a routing decision using Send() to fan out to parallel investigation.
    This function returns the hypotheses list; the graph uses route_to_hypothesis_investigation
    to create the Send() calls.
    """
    print("[Hypothesis Agent] Generating competing hypotheses...")

    try:
        response = llm.invoke([
            SystemMessage(content="You are a principal SRE with deep systems expertise."),
            HumanMessage(content=GENERATE_HYPOTHESES_PROMPT.format(
                incident_description=state.get("incident_description", ""),
                system_name=state.get("system_name", "Unknown"),
                fisma_category_name=state.get("fisma_category_name", "Unknown"),
                tool_summary=state.get("tool_summary", "No tool data available")[:2000],
                rag_summary=state.get("rag_summary", "No runbook data available")[:1000],
            )),
        ])
        content = response.content.strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
        if json_match:
            content = json_match.group(1)
        raw_hypotheses = json.loads(content)
    except Exception as e:
        print(f"[Hypothesis Agent] Generation error: {e}")
        raw_hypotheses = _default_hypotheses()

    # Convert to Hypothesis TypedDict format for state
    hypotheses = []
    for h in raw_hypotheses[:5]:
        hypotheses.append({
            "id": h.get("id", f"H{len(hypotheses)+1}"),
            "title": h.get("title", "Unknown hypothesis"),
            "category": h.get("category", "unknown"),
            "confidence": h.get("initial_confidence", 50),
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "next_investigation_step": h.get("key_evidence_needed", ""),
            "source": "generate_hypotheses",
            "status": "investigating",
        })

    print(f"[Hypothesis Agent] Generated {len(hypotheses)} hypotheses for parallel investigation.")

    return {
        "hypotheses": hypotheses,
        "current_node": "generate_hypotheses",
    }


def route_to_hypothesis_investigation(state: IncidentState):
    """
    LangGraph routing function — fans out to parallel hypothesis investigation.

    Uses LangGraph's Send() API to invoke investigate_hypothesis_node
    once per hypothesis, all running in parallel.
    """
    hypotheses = state.get("hypotheses", [])
    if not hypotheses:
        return "synthesize_hypotheses"

    return [
        Send("investigate_hypothesis", {**state, "current_hypothesis": h})
        for h in hypotheses
    ]


def investigate_hypothesis_node(state: dict, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Investigate a single hypothesis against tool evidence.

    Receives a copy of state with "current_hypothesis" injected by Send().
    Runs in parallel with other hypothesis investigations.
    """
    hypothesis = state.get("current_hypothesis", {})
    h_id = hypothesis.get("id", "H?")
    h_title = hypothesis.get("title", "Unknown")
    print(f"[Hypothesis Agent] Investigating {h_id}: {h_title[:50]}...")

    github = state.get("github_findings", {})
    cloudwatch = state.get("cloudwatch_findings", {})
    splunk = state.get("splunk_findings", {})
    rag_results = state.get("rag_results", [])

    rag_context = "\n".join(
        f"- {r.get('content', '')[:200]}" for r in rag_results[:4]
    ) or "No runbook data available"

    try:
        response = llm.invoke([
            SystemMessage(content="You are a principal SRE investigating a root cause hypothesis. Be rigorous."),
            HumanMessage(content=INVESTIGATE_HYPOTHESIS_PROMPT.format(
                hypothesis_id=h_id,
                hypothesis_title=h_title,
                hypothesis_category=hypothesis.get("category", "unknown"),
                github_evidence=f"{github.get('summary', '')}\nAnomalies: {'; '.join(github.get('anomalies', [])[:3])}",
                cloudwatch_evidence=f"{cloudwatch.get('summary', '')}\nAnomalies: {'; '.join(cloudwatch.get('anomalies', [])[:3])}",
                splunk_evidence=f"{splunk.get('summary', '')}\nAnomalies: {'; '.join(splunk.get('anomalies', [])[:3])}",
                rag_context=rag_context,
            )),
        ])
        content = response.content.strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
        if json_match:
            content = json_match.group(1)
        investigated: Hypothesis = json.loads(content)

    except Exception as e:
        print(f"[Hypothesis Agent] Investigation error for {h_id}: {e}")
        investigated = {**hypothesis, "status": "investigating",
                        "supporting_evidence": ["Investigation incomplete due to error"],
                        "contradicting_evidence": []}

    # Return via hypotheses list (operator.add merges all parallel results)
    return {
        "hypotheses": [investigated],
        "current_node": f"investigate_hypothesis_{h_id}",
    }


def synthesize_hypotheses_node(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Synthesize all parallel hypothesis investigations into a ranking.
    """
    print("[Hypothesis Agent] Synthesizing hypothesis rankings...")

    hypotheses = state.get("hypotheses", [])

    # Filter out the initial "investigating" entries, keep investigated ones
    investigated = [h for h in hypotheses if h.get("status") != "investigating"
                    or h.get("supporting_evidence")]
    if not investigated:
        investigated = hypotheses

    try:
        response = llm.invoke([
            SystemMessage(content="You are an incident commander reviewing root cause evidence."),
            HumanMessage(content=SYNTHESIZE_HYPOTHESES_PROMPT.format(
                incident_description=state.get("incident_description", ""),
                hypotheses_json=json.dumps(investigated, indent=2)[:3000],
            )),
        ])
        content = response.content.strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
        if json_match:
            content = json_match.group(1)
        synthesis = json.loads(content)

    except Exception as e:
        print(f"[Hypothesis Agent] Synthesis error: {e}")
        synthesis = {
            "top_hypothesis_id": investigated[0]["id"] if investigated else "H1",
            "ranked_ids": [h["id"] for h in investigated],
            "hypothesis_summary": "Hypothesis ranking incomplete due to error. Review individual investigations.",
            "confidence_in_top": 60,
            "alternative_worth_monitoring": "",
        }

    # Find top hypothesis object
    top_id = synthesis.get("top_hypothesis_id")
    top_hypothesis = next((h for h in investigated if h.get("id") == top_id), investigated[0] if investigated else {})

    # Rank all hypotheses per synthesis order
    ranked_ids = synthesis.get("ranked_ids", [h["id"] for h in investigated])
    ranked = sorted(investigated, key=lambda h: ranked_ids.index(h["id"]) if h["id"] in ranked_ids else 99)

    print(f"[Hypothesis Agent] Top: {top_hypothesis.get('title', 'Unknown')} "
          f"({top_hypothesis.get('confidence', 0)}% confidence)")

    return {
        "top_hypothesis": top_hypothesis,
        "ranked_hypotheses": ranked,
        "hypothesis_summary": synthesis.get("hypothesis_summary", ""),
        "current_node": "synthesize_hypotheses",
        "audit_log": [{
            "timestamp": datetime.now().isoformat(),
            "node": "hypothesis_agent",
            "action": "hypotheses_ranked",
            "details": f"Top: {top_hypothesis.get('title', 'Unknown')} | "
                       f"Confidence: {top_hypothesis.get('confidence', 0)}% | "
                       f"Total investigated: {len(investigated)}",
        }],
    }


def _default_hypotheses() -> list[dict]:
    """Fallback hypotheses for the BEACON incident if LLM fails."""
    return [
        {"id": "H1", "title": "HikariCP connection pool undersized for load surge", "category": "application", "initial_confidence": 80},
        {"id": "H2", "title": "Config change increased timeout causing thread exhaustion", "category": "application", "initial_confidence": 75},
        {"id": "H3", "title": "Database max_connections limit reached", "category": "infrastructure", "initial_confidence": 60},
        {"id": "H4", "title": "Upstream authentication service degraded", "category": "dependency", "initial_confidence": 25},
        {"id": "H5", "title": "External DoS attack", "category": "security", "initial_confidence": 15},
    ]
