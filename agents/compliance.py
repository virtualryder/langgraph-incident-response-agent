"""
Compliance Agent — FISMA reporting, US-CERT notification package, and stakeholder matrix.

Generates:
  - US-CERT mandatory incident report draft
  - Stakeholder notification status with countdown timers
  - Privacy Act notification if PII triggered
  - ATO impact statement if risk flagged
"""

import json
import re
from datetime import datetime
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from graph.state import IncidentState
from utils.fisma import FISMA_CATEGORIES, get_minutes_remaining


USCERT_REPORT_PROMPT = """Draft a US-CERT/CISA federal incident notification for this incident.
Follow the US-CERT Federal Incident Notification Guidelines format.

AGENCY: Bay State Department of Benefits
SYSTEM: {system_name}
INCIDENT ID: {incident_id}
FISMA CATEGORY: {fisma_category} — {fisma_category_name}
DETECTION TIME: {detection_time}
SEVERITY: {severity}

ROOT CAUSE SUMMARY: {hypothesis_summary}
BLAST RADIUS: {blast_radius_summary}
PII INVOLVED: {pii_involved}
ATO RISK: {ato_risk}

Draft the US-CERT notification. Include all required fields:
1. Incident Category and Severity
2. Affected Systems and Components
3. Detection Method and Time
4. Current Status
5. Impact Assessment
6. Actions Taken
7. Additional Information Needed

Keep it factual, concise, and in passive voice (government standard).
Max 400 words.
"""


def compliance_agent(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Generate FISMA compliance package and notification matrix.
    """
    print("[Compliance Agent] Building FISMA reporting package...")

    fisma_cat = state.get("fisma_category", 2)
    category_data = FISMA_CATEGORIES.get(fisma_cat, {})
    notification_matrix = state.get("notification_matrix", [])
    reporting_deadline = state.get("reporting_deadline")
    us_cert_required = state.get("us_cert_required", False)

    # Add Privacy Act notification if triggered
    if state.get("privacy_act_triggered") and not any(
        n.get("recipient") == "Privacy Officer / Senior Agency Official for Privacy"
        for n in notification_matrix
    ):
        notification_matrix.append({
            "recipient": "Privacy Officer / Senior Agency Official for Privacy",
            "deadline": reporting_deadline or "",
            "deadline_label": "Within 72 hours (Privacy Act)",
            "method": "email",
            "status": "pending",
            "required": True,
            "message_template": "PII may have been exposed during this incident. Privacy Officer review required.",
        })

    # Update minutes remaining for each notification
    updated_matrix = []
    for item in notification_matrix:
        minutes_left = get_minutes_remaining(item.get("deadline", ""))
        updated_matrix.append({
            **item,
            "minutes_remaining": minutes_left,
            "overdue": minutes_left == 0 and item.get("status") == "pending",
        })

    # ── Draft US-CERT report if required ─────────────────────────────────────
    fisma_report_draft = ""
    if us_cert_required:
        try:
            response = llm.invoke([
                SystemMessage(content="You are a federal ISSO drafting a mandatory incident notification."),
                HumanMessage(content=USCERT_REPORT_PROMPT.format(
                    system_name=state.get("system_name", "Unknown"),
                    incident_id=state.get("incident_id", "INC-PENDING"),
                    fisma_category=fisma_cat,
                    fisma_category_name=state.get("fisma_category_name", "Unknown"),
                    detection_time=state.get("detection_time", "Unknown"),
                    severity=state.get("severity", "Unknown"),
                    hypothesis_summary=state.get("hypothesis_summary", "Under investigation")[:500],
                    blast_radius_summary=state.get("blast_radius_summary", "Under investigation")[:300],
                    pii_involved=state.get("pii_cui_involved", False),
                    ato_risk=state.get("ato_risk", False),
                )),
            ])
            fisma_report_draft = response.content.strip()
        except Exception as e:
            fisma_report_draft = f"[US-CERT Report Draft — LLM generation failed: {e}. Manual completion required.]"

    compliance_summary_lines = [
        f"US-CERT Reporting: {'REQUIRED' if us_cert_required else 'NOT REQUIRED'} (CAT {fisma_cat})",
        f"Reporting Deadline: {reporting_deadline or 'No mandatory SLA'}",
        f"Notifications Pending: {sum(1 for n in updated_matrix if n.get('status') == 'pending')}",
        f"Privacy Act: {'TRIGGERED — 72hr notification required' if state.get('privacy_act_triggered') else 'Not triggered'}",
        f"ATO Risk: {'FLAGGED — ISSO review required' if state.get('ato_risk') else 'Not flagged'}",
    ]

    print(f"[Compliance Agent] US-CERT required: {us_cert_required} | "
          f"Notifications pending: {sum(1 for n in updated_matrix if n.get('status') == 'pending')}")

    return {
        "notification_matrix": updated_matrix,
        "fisma_report_draft": fisma_report_draft,
        "us_cert_deadline": reporting_deadline or "",
        "compliance_summary": "\n".join(compliance_summary_lines),
        "current_node": "compliance_agent",
        "audit_log": [{
            "timestamp": datetime.now().isoformat(),
            "node": "compliance_agent",
            "action": "compliance_package_built",
            "details": f"US-CERT required: {us_cert_required} | "
                       f"Notifications: {len(updated_matrix)} | "
                       f"Privacy Act: {state.get('privacy_act_triggered', False)}",
        }],
    }
