"""
Triage Agent — FISMA classification, severity assessment, and reporting clock.

This is the first node in the graph. It determines:
  - FISMA incident category (1-7 per NIST SP 800-61)
  - Severity (P1-P4)
  - PII/CUI involvement flag (Privacy Act trigger)
  - ATO risk assessment
  - US-CERT mandatory reporting deadline
  - Notification matrix (who must be notified and when)
"""

import json
import re
from datetime import datetime
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from graph.state import IncidentState
from utils.fisma import (
    FISMA_CATEGORIES,
    get_reporting_deadline,
    build_notification_matrix,
    classify_severity_from_impact,
)


TRIAGE_SYSTEM_PROMPT = """You are a federal agency ISSO (Information System Security Officer)
with 15 years of experience classifying security incidents per NIST SP 800-61 and FISMA.

Your job is to quickly triage incoming incidents with precision:
1. Classify the FISMA category (1-7) based on the incident description
2. Assign severity (P1-P4) based on impact
3. Flag PII/CUI involvement (triggers Privacy Act requirements)
4. Assess ATO risk (does this threaten the system's Authority to Operate?)
5. Identify affected systems

Be conservative: if uncertain between two categories, choose the higher severity.
A CAT 1 (Unauthorized Access) misclassified as CAT 2 (DoS) could result in a missed
mandatory 1-hour US-CERT reporting deadline — a compliance violation itself.
"""

TRIAGE_PROMPT = """Triage this incident report.

INCIDENT DESCRIPTION:
{incident_description}

SYSTEM: {system_name}
REPORTED BY: {reported_by}
DETECTION TIME: {detection_time}

FISMA CATEGORIES:
1 = Unauthorized Access (report within 1 hour)
2 = Denial of Service (report within 2 hours)
3 = Malicious Code (report within 1 hour)
4 = Improper Usage (report within 1 hour)
5 = Scans/Probes (weekly report, no immediate SLA)
6 = Investigation (no mandatory SLA)
7 = Explained Anomaly (no report required)

Return JSON:
{{
  "fisma_category": 2,
  "fisma_category_name": "Denial of Service",
  "confidence": 85,
  "severity": "P1",
  "severity_rationale": "Citizen portal completely unavailable, 47K weekly filers affected",
  "pii_cui_involved": false,
  "pii_rationale": "Service unavailability — no data exfiltration indicated",
  "ato_risk": false,
  "ato_risk_rationale": "Availability incident, not confidentiality or integrity. ATO not threatened unless prolonged.",
  "affected_systems": ["BEACON Benefits Portal", "SNAP eligibility API", "Authentication service"],
  "triage_summary": "2-3 sentence summary of what happened and why it's classified this way"
}}
"""


def triage_agent(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Classify the incident and start the FISMA reporting clock.
    """
    print("[Triage Agent] Classifying incident...")

    incident_description = state.get("incident_description", "")
    system_name = state.get("system_name", "Unknown System")
    reported_by = state.get("reported_by", "Unknown")
    detection_time = state.get("detection_time", datetime.now().isoformat())

    if not incident_description:
        return {
            "current_node": "triage_agent",
            "errors": ["No incident description provided"],
        }

    # ── LLM Classification ────────────────────────────────────────────────────
    try:
        response = llm.invoke([
            SystemMessage(content=TRIAGE_SYSTEM_PROMPT),
            HumanMessage(content=TRIAGE_PROMPT.format(
                incident_description=incident_description,
                system_name=system_name,
                reported_by=reported_by,
                detection_time=detection_time,
            )),
        ])
        content = response.content.strip()
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
        if json_match:
            content = json_match.group(1)
        triage_data = json.loads(content)

    except Exception as e:
        print(f"[Triage Agent] LLM error, using defaults: {e}")
        triage_data = {
            "fisma_category": 2,
            "fisma_category_name": "Denial of Service",
            "severity": "P1",
            "severity_rationale": "System unavailability with citizen impact",
            "pii_cui_involved": False,
            "pii_rationale": "Cannot determine from description",
            "ato_risk": False,
            "ato_risk_rationale": "Cannot determine from description",
            "affected_systems": [system_name],
            "triage_summary": f"Incident on {system_name} classified as potential DoS pending investigation.",
        }

    fisma_cat = triage_data.get("fisma_category", 2)
    category_data = FISMA_CATEGORIES.get(fisma_cat, FISMA_CATEGORIES[6])
    severity = triage_data.get("severity", "P2")

    # ── Calculate reporting deadline ──────────────────────────────────────────
    reporting_deadline = get_reporting_deadline(detection_time, fisma_cat)
    reporting_window_hours = category_data.get("reporting_window_hours") or 0

    # ── Build notification matrix ─────────────────────────────────────────────
    notification_matrix = build_notification_matrix(severity, detection_time, fisma_cat)

    # ── Build audit log entry ─────────────────────────────────────────────────
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "node": "triage_agent",
        "action": "incident_classified",
        "details": f"FISMA CAT {fisma_cat} ({triage_data.get('fisma_category_name')}) | {severity} | "
                   f"ATO Risk: {triage_data.get('ato_risk')} | PII: {triage_data.get('pii_cui_involved')}",
    }

    print(f"[Triage Agent] CAT {fisma_cat} ({category_data['name']}) | {severity} | "
          f"Reporting deadline: {reporting_deadline or 'No mandatory SLA'}")

    return {
        "fisma_category": fisma_cat,
        "fisma_category_name": triage_data.get("fisma_category_name", category_data["name"]),
        "fisma_description": category_data["description"],
        "severity": severity,
        "severity_rationale": triage_data.get("severity_rationale", ""),
        "pii_cui_involved": triage_data.get("pii_cui_involved", False),
        "affected_systems": triage_data.get("affected_systems", [system_name]),
        "reporting_deadline": reporting_deadline,
        "reporting_window_hours": reporting_window_hours,
        "ato_risk": triage_data.get("ato_risk", False),
        "ato_risk_rationale": triage_data.get("ato_risk_rationale", ""),
        "notification_matrix": notification_matrix,
        "triage_summary": triage_data.get("triage_summary", ""),
        "us_cert_required": category_data.get("us_cert_required", False),
        "current_node": "triage_agent",
        "audit_log": [audit_entry],
    }
