"""
Post-mortem Agent — NIST SP 800-61 formatted blameless incident post-mortem.

Produces the deliverable that a government CISO and IG actually want to see:
  - Incident timeline (reconstructed from tool data)
  - 5 Whys root cause analysis
  - Contributing factors (not who — what)
  - Corrective action items with owners and due dates
  - Post-Incident Review (PIR) scheduling
  - Lessons learned
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from graph.state import IncidentState, TimelineEvent


POSTMORTEM_SYSTEM_PROMPT = """You are a senior ISSO writing a blameless post-mortem per NIST SP 800-61
Computer Security Incident Handling Guide.

Key principles:
- BLAMELESS: Focus on what happened, not who caused it
- FACTUAL: Every claim backed by tool evidence
- ACTIONABLE: Every finding has a corrective action
- PREVENTIVE: Focus on systemic improvements, not individual mistakes

Write for a government audience: clear, precise, passive voice where appropriate.
"""

POSTMORTEM_PROMPT = """Write a complete blameless post-mortem for this incident in NIST SP 800-61 format.

INCIDENT ID: {incident_id}
SYSTEM: {system_name}
FISMA CATEGORY: CAT {fisma_category} — {fisma_category_name}
SEVERITY: {severity}
DETECTION TIME: {detection_time}
TOTAL DURATION: {duration_estimate}

ROOT CAUSE: {top_hypothesis}
CONFIDENCE: {confidence}%

EVIDENCE SUMMARY:
GitHub: {github_summary}
CloudWatch: {cloudwatch_summary}
Splunk: {splunk_summary}

CITIZEN IMPACT: {citizen_impact}
FINANCIAL IMPACT: ${financial_impact:,.0f}/hour
SLO BREACH: {slo_details}

REMEDIATION STEPS TAKEN:
{remediation_summary}

CAB DECISION: {cab_status} — {cab_comments}

Generate a complete post-mortem in Markdown with these sections:
1. Incident Summary (1 paragraph, executive-level)
2. Timeline of Events (bullet list with timestamps)
3. Root Cause Analysis — 5 Whys
4. Contributing Factors (systemic, not individual)
5. Impact Assessment (citizen, financial, compliance)
6. Response Actions Taken
7. Corrective Actions (table: Action | Owner | Due Date | Priority)
8. Lessons Learned
9. Post-Incident Review (PIR) Date
10. References (GitHub PR, CloudWatch alarms, Splunk queries)

Use specific data from the evidence. Cite tool sources inline.
"""


def postmortem_agent(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Generate NIST 800-61 post-mortem report.
    """
    print("[Post-mortem Agent] Generating post-mortem report...")

    top_hypothesis = state.get("top_hypothesis", {})
    remediation_steps = state.get("remediation_steps", [])
    github = state.get("github_findings", {})
    cloudwatch = state.get("cloudwatch_findings", {})
    splunk = state.get("splunk_findings", {})

    remediation_summary = "\n".join(
        f"Step {s.get('step_number', '?')}: {s.get('action', 'N/A')} (status: {s.get('status', 'pending')})"
        for s in remediation_steps
    ) or "Remediation steps not yet executed."

    # Estimate incident duration from timeline
    detection_time = state.get("detection_time", datetime.now().isoformat())
    duration_estimate = "Under investigation"
    try:
        detected = datetime.fromisoformat(detection_time.replace("Z", "+00:00"))
        now = datetime.now(detected.tzinfo)
        delta = now - detected
        hours = int(delta.total_seconds() / 3600)
        minutes = int((delta.total_seconds() % 3600) / 60)
        duration_estimate = f"~{hours}h {minutes}m (ongoing)" if hours < 24 else f"~{delta.days} days"
    except Exception:
        pass

    try:
        response = llm.invoke([
            SystemMessage(content=POSTMORTEM_SYSTEM_PROMPT),
            HumanMessage(content=POSTMORTEM_PROMPT.format(
                incident_id=state.get("incident_id", "INC-PENDING"),
                system_name=state.get("system_name", "Unknown"),
                fisma_category=state.get("fisma_category", "Unknown"),
                fisma_category_name=state.get("fisma_category_name", "Unknown"),
                severity=state.get("severity", "Unknown"),
                detection_time=detection_time,
                duration_estimate=duration_estimate,
                top_hypothesis=top_hypothesis.get("title", "Under investigation"),
                confidence=top_hypothesis.get("confidence", 0),
                github_summary=github.get("summary", "N/A")[:500],
                cloudwatch_summary=cloudwatch.get("summary", "N/A")[:500],
                splunk_summary=splunk.get("summary", "N/A")[:500],
                citizen_impact=f"~{state.get('affected_citizens_estimate', 0):,} citizens affected",
                financial_impact=state.get("estimated_financial_impact_per_hour", 0),
                slo_details=state.get("slo_details", "Unknown"),
                remediation_summary=remediation_summary,
                cab_status=state.get("cab_status", "pending"),
                cab_comments=state.get("cab_comments", "None"),
            )),
        ])
        postmortem_md = response.content.strip()

    except Exception as e:
        print(f"[Post-mortem Agent] LLM error: {e}")
        postmortem_md = _fallback_postmortem(state, duration_estimate)

    # Schedule PIR 5 business days out
    try:
        pir_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    except Exception:
        pir_date = "TBD"

    # Extract corrective actions from post-mortem text
    corrective_actions = _extract_corrective_actions(postmortem_md)

    # Build reconstructed timeline from tool data
    timeline = _build_timeline(state)

    # Convert to HTML
    try:
        import markdown
        html_body = markdown.markdown(postmortem_md, extensions=["tables", "fenced_code"])
        postmortem_html = _wrap_html(html_body, state.get("incident_id", "INC"), state.get("system_name", ""))
    except ImportError:
        postmortem_html = f"<pre>{postmortem_md}</pre>"

    print(f"[Post-mortem Agent] Post-mortem generated: {len(postmortem_md)} chars | "
          f"PIR scheduled: {pir_date} | {len(corrective_actions)} corrective actions")

    return {
        "postmortem_md": postmortem_md,
        "postmortem_html": postmortem_html,
        "corrective_actions": corrective_actions,
        "pir_date": pir_date,
        "timeline": timeline,
        "current_node": "postmortem_agent",
        "audit_log": [{
            "timestamp": datetime.now().isoformat(),
            "node": "postmortem_agent",
            "action": "postmortem_generated",
            "details": f"PIR: {pir_date} | Corrective actions: {len(corrective_actions)}",
        }],
    }


def _build_timeline(state: IncidentState) -> list[TimelineEvent]:
    """Reconstruct incident timeline from Splunk first-occurrence data."""
    splunk = state.get("splunk_findings", {})
    raw_results = splunk.get("raw_results", {})
    splunk_timeline = raw_results.get("first_occurrence_timeline", [])

    timeline = []
    for event in splunk_timeline:
        timeline.append({
            "timestamp": event.get("timestamp", ""),
            "source": "splunk",
            "event": event.get("event", ""),
            "severity": "critical" if "ERROR" in event.get("event", "").upper()
                        else "warning" if "WARN" in event.get("event", "").upper()
                        else "normal",
            "service": state.get("system_name", "BEACON"),
        })

    # Add GitHub event
    github = state.get("github_findings", {})
    raw_commits = github.get("raw_results", {}).get("commits", [])
    for commit in raw_commits[:1]:
        timeline.append({
            "timestamp": commit.get("timestamp", ""),
            "source": "github",
            "event": f"Code change deployed: {commit.get('message', '')}",
            "severity": "warning",
            "service": "BEACON deploy pipeline",
        })

    # Sort by timestamp
    timeline.sort(key=lambda e: e.get("timestamp", ""), reverse=False)
    return timeline


def _extract_corrective_actions(postmortem_md: str) -> list[dict]:
    """Extract corrective action table rows from generated post-mortem."""
    actions = []
    in_table = False
    for line in postmortem_md.split("\n"):
        if "corrective action" in line.lower():
            in_table = True
            continue
        if in_table and line.startswith("|") and "---" not in line and "Action" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 3:
                actions.append({
                    "action": parts[0] if parts else "",
                    "owner": parts[1] if len(parts) > 1 else "TBD",
                    "due_date": parts[2] if len(parts) > 2 else "TBD",
                    "priority": parts[3] if len(parts) > 3 else "Medium",
                })
        elif in_table and line.startswith("#"):
            in_table = False
    return actions


def _fallback_postmortem(state: IncidentState, duration: str) -> str:
    incident_id = state.get("incident_id", "INC-PENDING")
    system = state.get("system_name", "Unknown System")
    hypothesis = state.get("top_hypothesis", {}).get("title", "Under investigation")

    return f"""# Incident Post-Mortem: {incident_id}

**System:** {system}
**FISMA Category:** CAT {state.get('fisma_category', 'Unknown')} — {state.get('fisma_category_name', 'Unknown')}
**Severity:** {state.get('severity', 'Unknown')}
**Duration:** {duration}

## Incident Summary
A {state.get('fisma_category_name', 'service')} incident affecting {system} resulted in
service unavailability impacting approximately {state.get('affected_citizens_estimate', 0):,} citizens.

## Root Cause
{hypothesis}

## Corrective Actions

| Action | Owner | Due Date | Priority |
|---|---|---|---|
| Increase database connection pool size | Platform Engineering | +3 days | High |
| Add HikariPool utilization alert at 70% threshold | DevOps | +5 days | High |
| Review all open GitHub issues tagged database/performance | Engineering Lead | +7 days | Medium |
| Update capacity planning runbook | SRE Team | +14 days | Medium |

## Post-Incident Review
Scheduled: {(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")}
"""


def _wrap_html(body: str, incident_id: str, system_name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Post-mortem: {incident_id} — {system_name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 960px; margin: 40px auto; padding: 0 20px; color: #1a202c; }}
        h1 {{ color: #c53030; border-bottom: 3px solid #fc8181; padding-bottom: 8px; }}
        h2 {{ color: #2c5282; border-bottom: 1px solid #bee3f8; margin-top: 28px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
        th {{ background: #2b6cb0; color: white; padding: 8px; text-align: left; }}
        td {{ padding: 8px; border: 1px solid #e2e8f0; }}
        tr:nth-child(even) {{ background: #ebf8ff; }}
        blockquote {{ border-left: 4px solid #fc8181; background: #fff5f5; padding: 12px 16px; }}
        .blameless-banner {{ background: #f0fff4; border: 1px solid #68d391; padding: 12px;
                             border-radius: 6px; margin-bottom: 24px; color: #276749; }}
    </style>
</head>
<body>
<div class="blameless-banner">
    This is a BLAMELESS post-mortem. The goal is to understand what happened and prevent recurrence.
    Individual contributors acted in good faith with the information available to them.
</div>
{body}
<footer style="margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;color:#718096;font-size:0.85em">
    <p>Generated by AI Incident Response Agent | Built with LangGraph · LangChain · LangSmith</p>
    <p>This document is AI-assisted. Review and approval by ISSO required before official filing.</p>
</footer>
</body>
</html>"""
