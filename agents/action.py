"""
Action Agent — safe, approved remediation steps after CAB approval.

Generates a prioritized remediation plan with:
  - Immediate containment actions
  - Root cause fix steps
  - Rollback plan
  - Verification steps

Every high-risk action is flagged and will not execute without CAB approval.
"""

import json
import re
from datetime import datetime
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from graph.state import IncidentState


ACTION_PROMPT = """You are a principal SRE writing a safe remediation plan for a government production system.

INCIDENT: {incident_description}
CONFIRMED ROOT CAUSE: {top_hypothesis}
CONFIDENCE: {confidence}%

CAB COMMENTS: {cab_comments}

TOOL FINDINGS SUMMARY:
{tool_summary}

HOTFIX AVAILABLE: {hotfix_available}

Write a step-by-step remediation plan. For each step:
- Be specific (exact config values, commands, steps)
- Assign risk level (low/medium/high)
- Include rollback for medium/high risk steps
- Flag whether CAB approval is required

Return JSON array:
[
  {{
    "step_number": 1,
    "action": "Increase HikariCP maximumPoolSize from 10 to 50 in application-prod.properties",
    "rationale": "Current pool size of 10 is exhausted under Monday surge load of ~12,000 concurrent users",
    "risk_level": "medium",
    "rollback": "Revert application-prod.properties to previous value and redeploy",
    "requires_cab": true,
    "estimated_recovery_time_minutes": 15,
    "verification": "Monitor HikariPool stats in Splunk — idle connections should return, error rate should drop below 1%",
    "status": "approved"
  }},
  {{
    "step_number": 2,
    "action": "Monitor for 30 minutes post-deploy before closing incident",
    "rationale": "Confirm fix holds under continued load",
    "risk_level": "low",
    "rollback": "N/A",
    "requires_cab": false,
    "estimated_recovery_time_minutes": 30,
    "verification": "CloudWatch alarm BEACON-App-ErrorRate-Critical returns to OK state",
    "status": "approved"
  }}
]
"""


def action_agent(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Generate approved remediation steps post-CAB review.
    """
    print("[Action Agent] Generating remediation plan...")

    top_hypothesis = state.get("top_hypothesis", {})
    github = state.get("github_findings", {})
    hotfix_available = bool(github.get("hotfix_pr"))

    try:
        response = llm.invoke([
            SystemMessage(content="You are a principal SRE writing safe remediation steps for a government system."),
            HumanMessage(content=ACTION_PROMPT.format(
                incident_description=state.get("incident_description", ""),
                top_hypothesis=top_hypothesis.get("title", "Unknown"),
                confidence=top_hypothesis.get("confidence", 0),
                cab_comments=state.get("cab_comments", "None"),
                tool_summary=state.get("tool_summary", "")[:800],
                hotfix_available=f"Yes — PR #{github.get('hotfix_pr', 'N/A')} awaiting merge" if hotfix_available else "No",
            )),
        ])
        content = response.content.strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
        if json_match:
            content = json_match.group(1)
        steps = json.loads(content)

    except Exception as e:
        print(f"[Action Agent] LLM error: {e}")
        steps = _default_remediation(top_hypothesis, hotfix_available)

    rollback_plan = "\n".join(
        f"Step {s.get('step_number', '?')}: {s.get('rollback', 'N/A')}"
        for s in steps if s.get("rollback") and s.get("rollback") != "N/A"
    ) or "No rollback plan generated — manual review required."

    total_recovery_minutes = sum(s.get("estimated_recovery_time_minutes", 0) for s in steps)

    action_summary = (
        f"{len(steps)} remediation steps generated. "
        f"Estimated recovery time: {total_recovery_minutes} minutes. "
        f"{'Emergency hotfix PR available on GitHub.' if hotfix_available else 'No hotfix PR available — manual fix required.'}"
    )

    print(f"[Action Agent] {len(steps)} steps | ~{total_recovery_minutes} min recovery")

    return {
        "remediation_steps": steps,
        "rollback_plan": rollback_plan,
        "action_summary": action_summary,
        "current_node": "action_agent",
        "audit_log": [{
            "timestamp": datetime.now().isoformat(),
            "node": "action_agent",
            "action": "remediation_plan_generated",
            "details": f"{len(steps)} steps | ~{total_recovery_minutes} min | CAB approved: {state.get('cab_status')}",
        }],
    }


def _default_remediation(top_hypothesis: dict, hotfix_available: bool) -> list[dict]:
    """Fallback remediation plan."""
    steps = [
        {
            "step_number": 1,
            "action": "Merge emergency hotfix PR #923 to increase connection pool size",
            "rationale": "Hotfix increases maximumPoolSize from 10 to 50",
            "risk_level": "medium",
            "rollback": "git revert and redeploy previous artifact",
            "requires_cab": True,
            "estimated_recovery_time_minutes": 15,
            "verification": "Monitor Splunk for HikariPool idle connections > 0",
            "status": "approved",
        } if hotfix_available else {
            "step_number": 1,
            "action": "Update hikari.maximumPoolSize=50 in application-prod.properties and redeploy",
            "rationale": "Current pool size of 10 is exhausted under load",
            "risk_level": "medium",
            "rollback": "Revert application-prod.properties and redeploy",
            "requires_cab": True,
            "estimated_recovery_time_minutes": 20,
            "verification": "Monitor Splunk for HikariPool idle connections > 0",
            "status": "approved",
        },
        {
            "step_number": 2,
            "action": "Monitor CloudWatch and Splunk for 30 minutes post-deploy",
            "rationale": "Confirm fix holds under continued load",
            "risk_level": "low",
            "rollback": "N/A",
            "requires_cab": False,
            "estimated_recovery_time_minutes": 30,
            "verification": "CloudWatch alarm BEACON-App-ErrorRate-Critical returns to OK",
            "status": "approved",
        },
    ]
    return steps
