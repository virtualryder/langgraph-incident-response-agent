"""
Blast Radius Agent — citizen impact, SLO breach, and ATO risk assessment.

For public sector, this goes beyond "how many users are affected" to:
  - Estimated citizen impact (benefit payments, service access)
  - Privacy Act trigger check (PII exposure)
  - SLO/SLA breach status
  - Downstream service dependencies
  - Financial impact estimate
"""

import json
import re
from datetime import datetime
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from graph.state import IncidentState


BLAST_RADIUS_PROMPT = """You are a government system owner assessing the citizen impact of a production incident.

INCIDENT: {incident_description}
SYSTEM: {system_name}
FISMA CATEGORY: {fisma_category_name}
SEVERITY: {severity}
PII/CUI INVOLVED: {pii_involved}

AFFECTED SYSTEMS IDENTIFIED: {affected_systems}

TOOL FINDINGS:
- GitHub: {github_summary}
- CloudWatch: {cloudwatch_summary}
- Splunk: {splunk_summary}

TOP HYPOTHESIS: {top_hypothesis}

Estimate the blast radius. Be specific about citizen impact — this informs P1/P2 classification
and whether the Privacy Officer and public affairs must be notified.

Return JSON:
{{
  "affected_citizens_estimate": 47000,
  "citizen_impact_description": "~47,000 weekly unemployment claimants unable to file due to portal unavailability. Monday is peak filing day.",
  "affected_services": ["BEACON citizen portal", "SNAP eligibility API", "Direct deposit processing"],
  "downstream_dependencies": ["MassTaxConnect authentication", "benefits-db RDS cluster", "S3 document storage"],
  "slo_breach": true,
  "slo_details": "SLO: 99.5% availability, P99 response < 5s. Current: 10.7% availability, P99 = 30s. BREACHED.",
  "estimated_financial_impact_per_hour": 185000,
  "financial_impact_rationale": "$3.2M in weekly benefit disbursements, ~$185K/hour in delayed payments",
  "privacy_act_triggered": false,
  "privacy_act_rationale": "Availability incident — no data exfiltration detected in logs or CloudWatch",
  "blast_radius_summary": "2-3 sentence summary"
}}
"""


def blast_radius_agent(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Assess citizen impact, SLO breach, and financial consequences.
    """
    print("[Blast Radius Agent] Assessing citizen impact and SLO breach...")

    github = state.get("github_findings", {})
    cloudwatch = state.get("cloudwatch_findings", {})
    splunk = state.get("splunk_findings", {})
    top_hypothesis = state.get("top_hypothesis", {})

    try:
        response = llm.invoke([
            SystemMessage(content="You are a government system owner assessing incident impact."),
            HumanMessage(content=BLAST_RADIUS_PROMPT.format(
                incident_description=state.get("incident_description", ""),
                system_name=state.get("system_name", "Unknown"),
                fisma_category_name=state.get("fisma_category_name", "Unknown"),
                severity=state.get("severity", "Unknown"),
                pii_involved=state.get("pii_cui_involved", False),
                affected_systems=", ".join(state.get("affected_systems", [])),
                github_summary=github.get("summary", "N/A")[:400],
                cloudwatch_summary=cloudwatch.get("summary", "N/A")[:400],
                splunk_summary=splunk.get("summary", "N/A")[:400],
                top_hypothesis=top_hypothesis.get("title", "Unknown"),
            )),
        ])
        content = response.content.strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
        if json_match:
            content = json_match.group(1)
        data = json.loads(content)

    except Exception as e:
        print(f"[Blast Radius Agent] LLM error: {e}")
        data = {
            "affected_citizens_estimate": 0,
            "citizen_impact_description": "Impact assessment incomplete — manual review required",
            "affected_services": state.get("affected_systems", []),
            "downstream_dependencies": [],
            "slo_breach": cloudwatch.get("slo_breach", False),
            "slo_details": cloudwatch.get("slo_details", "Unknown"),
            "estimated_financial_impact_per_hour": 0,
            "financial_impact_rationale": "Unable to estimate",
            "privacy_act_triggered": state.get("pii_cui_involved", False),
            "privacy_act_rationale": "Based on triage PII flag",
            "blast_radius_summary": "Impact assessment incomplete.",
        }

    print(f"[Blast Radius Agent] Citizens affected: ~{data.get('affected_citizens_estimate', 0):,} | "
          f"SLO breach: {data.get('slo_breach')} | "
          f"Privacy Act: {data.get('privacy_act_triggered')}")

    return {
        "affected_citizens_estimate": data.get("affected_citizens_estimate", 0),
        "affected_services": data.get("affected_services", []),
        "slo_breach": data.get("slo_breach", False),
        "slo_details": data.get("slo_details", ""),
        "estimated_financial_impact_per_hour": data.get("estimated_financial_impact_per_hour", 0),
        "privacy_act_triggered": data.get("privacy_act_triggered", False),
        "blast_radius_summary": data.get("blast_radius_summary", ""),
        "current_node": "blast_radius_agent",
        "audit_log": [{
            "timestamp": datetime.now().isoformat(),
            "node": "blast_radius_agent",
            "action": "impact_assessed",
            "details": f"Citizens: ~{data.get('affected_citizens_estimate', 0):,} | "
                       f"SLO breach: {data.get('slo_breach')} | "
                       f"$/hr: ${data.get('estimated_financial_impact_per_hour', 0):,.0f}",
        }],
    }
