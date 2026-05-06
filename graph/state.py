"""
Incident Response Agent — LangGraph State Definition

Central state object flowing through every node. LangGraph checkpoints this
at each boundary, enabling:
  - FISMA reporting clock tracking across nodes
  - Human CAB approval interrupt
  - Full audit trail for IG/GAO review
  - Resume after CAB decision
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, TypedDict
import operator


# ─── Sub-schemas ──────────────────────────────────────────────────────────────

class Hypothesis(TypedDict, total=False):
    """A single root cause hypothesis with supporting/contradicting evidence."""
    id: str                         # "H1", "H2", etc.
    title: str                      # "Database connection pool exhaustion"
    category: str                   # "infrastructure" | "application" | "network" | "security" | "human_error"
    confidence: int                 # 0-100
    supporting_evidence: list[str]  # Evidence that supports this hypothesis
    contradicting_evidence: list[str]
    next_investigation_step: str    # What to check to confirm or rule out
    source: str                     # "cloudwatch" | "splunk" | "github" | "rag" | "synthesis"
    status: Literal["investigating", "confirmed", "ruled_out", "probable"]


class ToolFinding(TypedDict, total=False):
    """A structured finding from one of the integrated tools."""
    tool: str           # "github" | "cloudwatch" | "splunk"
    query: str          # What was queried
    summary: str        # LLM-synthesized summary
    raw_results: list[dict]
    anomalies: list[str]
    relevant_to_incident: bool


class NotificationItem(TypedDict):
    """A required stakeholder notification."""
    recipient: str          # "CISO", "IG Office", "US-CERT", "Public Affairs"
    deadline: str           # ISO datetime or relative ("within 1 hour")
    method: str             # "email" | "phone" | "US-CERT portal" | "press release"
    message_template: str   # Draft message
    status: Literal["pending", "sent", "overdue"]
    required: bool


class TimelineEvent(TypedDict):
    """A reconstructed event in the incident timeline."""
    timestamp: str          # ISO datetime or relative
    source: str             # "splunk" | "cloudwatch" | "github" | "manual"
    event: str              # Description
    severity: str           # "normal" | "warning" | "critical"
    service: str


class RemediationStep(TypedDict):
    """A single approved remediation action."""
    step_number: int
    action: str
    rationale: str
    risk_level: Literal["low", "medium", "high"]
    rollback: str
    requires_cab: bool
    status: Literal["pending", "approved", "executing", "complete", "failed"]


# ─── Main State ───────────────────────────────────────────────────────────────

class IncidentState(TypedDict, total=False):
    """
    Central state for the Incident Response Agent graph.

    Every field is optional (total=False) to support partial state updates.
    Fields with Annotated[list, operator.add] support parallel node writes.
    """

    # ── Inputs ────────────────────────────────────────────────────────────────
    incident_id: str                # "INC-2025-0847"
    incident_description: str       # Free-text incident description from analyst
    system_name: str                # "BEACON Benefits Portal"
    detection_time: str             # ISO datetime when incident was detected
    reported_by: str                # Name/role of person filing incident
    raw_logs: str                   # Optional: pasted log lines from analyst

    # ── Triage Agent ──────────────────────────────────────────────────────────
    fisma_category: int             # 1-7 per NIST SP 800-61
    fisma_category_name: str        # "Denial of Service"
    fisma_description: str          # What this category means
    severity: Literal["P1", "P2", "P3", "P4"]
    severity_rationale: str
    pii_cui_involved: bool          # Privacy Act trigger flag
    affected_systems: list[str]     # Services/components affected
    reporting_deadline: str         # ISO datetime (detection + reporting window)
    reporting_window_hours: int     # 1, 2, or 168 depending on category
    ato_risk: bool                  # Does this threaten ATO status?
    ato_risk_rationale: str
    triage_summary: str

    # ── RAG Agent ─────────────────────────────────────────────────────────────
    rag_results: Annotated[list[dict], operator.add]
    relevant_runbooks: list[dict]   # Matched runbook excerpts with source
    similar_incidents: list[dict]   # Past incidents matching this pattern
    rag_summary: str

    # ── Tool Agent ────────────────────────────────────────────────────────────
    github_findings: ToolFinding
    cloudwatch_findings: ToolFinding
    splunk_findings: ToolFinding
    tool_summary: str               # Synthesized narrative from all 3 tools

    # ── Hypothesis Agent (parallel Send()) ───────────────────────────────────
    hypotheses: Annotated[list[Hypothesis], operator.add]
    top_hypothesis: Hypothesis
    ranked_hypotheses: list[Hypothesis]     # All hypotheses sorted by confidence
    hypothesis_summary: str

    # ── Blast Radius Agent ────────────────────────────────────────────────────
    affected_citizens_estimate: int
    affected_services: list[str]
    slo_breach: bool
    slo_details: str
    estimated_financial_impact_per_hour: float
    privacy_act_triggered: bool
    blast_radius_summary: str

    # ── Compliance Agent ──────────────────────────────────────────────────────
    us_cert_required: bool
    us_cert_deadline: str           # ISO datetime
    notification_matrix: list[NotificationItem]
    fisma_report_draft: str         # Draft US-CERT/ISAC submission
    compliance_summary: str

    # ── CAB Review (Human-in-the-Loop) ────────────────────────────────────────
    change_package: dict            # Formal CAB change request
    cab_status: Literal["pending", "approved", "denied"]
    cab_approver: str
    cab_comments: str
    cab_timestamp: str

    # ── Action Agent ──────────────────────────────────────────────────────────
    remediation_steps: list[RemediationStep]
    rollback_plan: str
    action_summary: str

    # ── Post-mortem Agent ─────────────────────────────────────────────────────
    timeline: list[TimelineEvent]
    postmortem_md: str              # NIST 800-61 formatted post-mortem
    postmortem_html: str
    corrective_actions: list[dict]  # Owner + due date for each action item
    pir_date: str                   # Post-Incident Review scheduled date

    # ── Graph control ─────────────────────────────────────────────────────────
    current_node: str
    errors: Annotated[list[str], operator.add]
    messages: Annotated[list[Any], operator.add]
    audit_log: Annotated[list[dict], operator.add]  # Immutable investigation trail
