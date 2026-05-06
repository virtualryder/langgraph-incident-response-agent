"""
AI Incident Response & Root Cause Analysis Agent
Public Sector Edition — FISMA · NIST SP 800-61 · US-CERT · CAB Approval

Built with LangGraph · LangChain · LangSmith · GitHub · CloudWatch · Splunk · ChromaDB · GPT-4o

Portfolio project demonstrating:
  - FISMA incident classification with live reporting countdown
  - Parallel hypothesis investigation via LangGraph Send()
  - Real tool integration (GitHub, CloudWatch, Splunk — simulated)
  - Citizen blast radius and SLO breach assessment
  - Human-in-the-loop CAB approval gate
  - NIST SP 800-61 blameless post-mortem generation
  - Full audit trail for IG/GAO review
"""

import os
import uuid
import json
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="AI Incident Response Agent",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header { font-size: 1.9rem; font-weight: 700; color: #c53030;
                   border-bottom: 3px solid #fc8181; padding-bottom: 0.5rem; }
    .section-header { font-size: 1.1rem; font-weight: 600; color: #2c5282;
                      border-left: 4px solid #4a90d9; padding-left: 0.75rem; margin: 1rem 0; }
    .fisma-clock { background: #fff5f5; border: 2px solid #fc8181; border-radius: 8px;
                   padding: 1rem; text-align: center; }
    .fisma-clock-ok { background: #f0fff4; border-color: #68d391; }
    .fisma-clock-warn { background: #fffbeb; border-color: #f6e05e; }
    .blameless-note { background: #f0fff4; border: 1px solid #68d391; border-radius: 6px;
                      padding: 0.75rem; color: #276749; font-size: 0.9rem; }
    .audit-entry { font-family: monospace; font-size: 0.8rem; background: #1a202c;
                   color: #68d391; padding: 4px 8px; border-radius: 4px; margin: 2px 0; }
    .hypothesis-card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem; margin: 0.4rem 0; }
    .h-confirmed { border-left: 4px solid #48bb78; background: #f0fff4; }
    .h-probable  { border-left: 4px solid #f6ad55; background: #fffbeb; }
    .h-ruled-out { border-left: 4px solid #a0aec0; background: #f7fafc; opacity: 0.7; }
    .notification-overdue { background: #fff5f5; border: 1px solid #fc8181; border-radius: 4px; padding: 4px 8px; }
    .notification-ok { background: #f0fff4; border: 1px solid #68d391; border-radius: 4px; padding: 4px 8px; }
</style>
""", unsafe_allow_html=True)


# ─── Session state ─────────────────────────────────────────────────────────────
def init():
    defaults = {
        "graph": None, "checkpointer": None, "thread_id": None,
        "graph_state": None, "run_stage": "setup",
        "openai_key": os.environ.get("OPENAI_API_KEY", ""),
        "langsmith_key": os.environ.get("LANGSMITH_API_KEY", ""),
        "error_message": "",
        "cab_comments": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init()

# ─── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    with st.expander("API Keys", expanded=not st.session_state.openai_key):
        key = st.text_input("OpenAI API Key", value=st.session_state.openai_key,
                            type="password")
        if key:
            st.session_state.openai_key = key
            os.environ["OPENAI_API_KEY"] = key

        ls_key = st.text_input("LangSmith API Key (optional)", value=st.session_state.langsmith_key,
                               type="password")
        if ls_key:
            st.session_state.langsmith_key = ls_key
            os.environ["LANGSMITH_API_KEY"] = ls_key
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_PROJECT"] = "incident-response-agent"

    model = st.selectbox("Model", ["gpt-4o", "gpt-4o-mini"])
    force_reingest = st.checkbox("Re-ingest Knowledge Base")

    st.markdown("---")
    st.markdown("### Workflow")
    st.markdown("""
1. 🔺 Triage (FISMA + clock)
2. 📖 RAG (runbooks + past incidents)
3. 🔧 Tools (GitHub · CloudWatch · Splunk)
4. 🔀 **Parallel** hypothesis investigation
5. 💥 Blast radius + citizen impact
6. ⚖️ FISMA compliance package
7. 👤 **CAB approval gate**
8. 🛠️ Remediation steps
9. 📋 NIST 800-61 post-mortem
    """)

    if st.session_state.langsmith_key:
        st.success("LangSmith: ON")


# ─── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">🚨 AI Incident Response & RCA Agent — Public Sector</div>', unsafe_allow_html=True)
st.markdown("*FISMA · NIST SP 800-61 · US-CERT reporting · CAB approval gate · Blameless post-mortem*")

WORKFLOW_STEPS = [
    ("triage_agent", "🔺 Triage"),
    ("rag_agent", "📖 RAG"),
    ("tool_agent", "🔧 Tools"),
    ("generate_hypotheses", "🧠 Hypotheses"),
    ("synthesize_hypotheses", "🔀 Synthesize"),
    ("blast_radius_agent", "💥 Blast Radius"),
    ("compliance_agent", "⚖️ Compliance"),
    ("cab_review_node", "👤 CAB"),
    ("action_agent", "🛠️ Action"),
    ("postmortem_agent", "📋 Post-mortem"),
]

def render_progress(current: str | None):
    order = [s[0] for s in WORKFLOW_STEPS]
    cols = st.columns(len(WORKFLOW_STEPS))
    for i, (node_id, label) in enumerate(WORKFLOW_STEPS):
        with cols[i]:
            try:
                current_idx = order.index(current) if current in order else -1
                this_idx = order.index(node_id)
            except ValueError:
                current_idx = this_idx = -1
            if node_id == current:
                st.markdown(f"🟡 **{label}**")
            elif this_idx < current_idx:
                st.markdown(f"✅ {label}")
            else:
                st.markdown(f"⬜ {label}")


# ─── FISMA Reporting Clock ─────────────────────────────────────────────────────
def render_fisma_clock(state: dict):
    """Live countdown to US-CERT reporting deadline."""
    from utils.fisma import get_minutes_remaining

    deadline = state.get("reporting_deadline")
    fisma_cat = state.get("fisma_category")
    fisma_name = state.get("fisma_category_name", "")
    us_cert_required = state.get("us_cert_required", False)

    if not us_cert_required or not deadline:
        st.info(f"CAT {fisma_cat} — {fisma_name}: No mandatory US-CERT reporting deadline.")
        return

    minutes_left = get_minutes_remaining(deadline)
    hours_left = minutes_left // 60
    mins_left = minutes_left % 60

    if minutes_left > 60:
        clock_class = "fisma-clock fisma-clock-ok"
        icon = "🟢"
    elif minutes_left > 20:
        clock_class = "fisma-clock fisma-clock-warn"
        icon = "🟡"
    elif minutes_left > 0:
        clock_class = "fisma-clock"
        icon = "🔴"
    else:
        clock_class = "fisma-clock"
        icon = "❌"

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if minutes_left > 0:
            st.markdown(
                f'<div class="{clock_class}">'
                f'<h2>{icon} US-CERT Reporting Deadline</h2>'
                f'<h1>{hours_left}h {mins_left}m remaining</h1>'
                f'<p>CAT {fisma_cat} — {fisma_name} | Deadline: {deadline[:16].replace("T", " ")}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.error(f"❌ US-CERT REPORTING DEADLINE PASSED — CAT {fisma_cat} requires immediate action")


# ─── Incident intake form ──────────────────────────────────────────────────────
st.markdown("---")
st.markdown('<div class="section-header">Step 1 — File Incident Report</div>', unsafe_allow_html=True)

sample_dir = Path("data/sample_incidents")
sample_files = list(sample_dir.glob("*.txt")) if sample_dir.exists() else []

col1, col2 = st.columns([2, 1])
with col1:
    incident_id = st.text_input("Incident ID", value="INC-2025-0847",
                                 placeholder="INC-2025-XXXX")
    system_name = st.text_input("Affected System", value="BEACON Benefits Portal",
                                 placeholder="System or service name")
    reported_by = st.text_input("Reported By", value="Sarah Chen, On-Call SRE")

with col2:
    detection_time = st.text_input(
        "Detection Time (ISO)",
        value=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        help="When the incident was first detected"
    )

    if sample_files:
        selected = st.selectbox("Load Sample Incident", ["(none)"] + [f.name for f in sample_files])
        if selected != "(none)" and st.button("Load"):
            text = (sample_dir / selected).read_text(encoding="utf-8")
            st.session_state["loaded_description"] = text
            st.rerun()

incident_description = st.text_area(
    "Incident Description",
    value=st.session_state.get("loaded_description", (
        "BEACON citizen benefits portal returning HTTP 503 errors to all users attempting to file "
        "weekly unemployment claims. Started ~9:09 AM during Monday morning peak window. "
        "~47,000 weekly claimants affected. Application pods appear healthy but not serving traffic. "
        "Database-related errors in logs. Last deployment ~36 hours ago. No scheduled maintenance active."
    )),
    height=130,
    help="Describe the incident as reported. The agent will investigate automatically."
)

raw_logs = st.text_area(
    "Paste Log Snippets (optional)",
    placeholder="Paste any relevant log lines here — the agent will include them in its analysis.",
    height=80,
)

# ─── Run agent ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Step 2 — Run Investigation</div>', unsafe_allow_html=True)

ready = bool(incident_description and st.session_state.openai_key)
col1, col2 = st.columns([3, 1])
with col1:
    run_btn = st.button("🚨 Launch Incident Investigation", disabled=not ready,
                        type="primary", use_container_width=True)
with col2:
    if st.button("🔄 Reset", use_container_width=True):
        for k in ["graph", "graph_state", "run_stage", "error_message", "thread_id", "loaded_description"]:
            st.session_state[k] = None if k != "run_stage" else "setup"
        st.session_state.run_stage = "setup"
        st.rerun()

if run_btn and ready:
    st.session_state.run_stage = "running"
    st.session_state.thread_id = str(uuid.uuid4())[:8]

    with st.spinner("Running investigation (triage → RAG → tools → parallel hypotheses → blast radius → compliance)..."):
        try:
            from graph.graph import build_graph, run_graph
            graph, checkpointer = build_graph(
                openai_api_key=st.session_state.openai_key,
                model=model,
                force_reingest=force_reingest,
            )
            st.session_state.graph = graph
            st.session_state.checkpointer = checkpointer

            result = run_graph(
                graph=graph,
                incident_description=incident_description,
                system_name=system_name,
                incident_id=incident_id,
                detection_time=detection_time,
                reported_by=reported_by,
                raw_logs=raw_logs,
                thread_id=st.session_state.thread_id,
            )
            st.session_state.graph_state = result
            st.session_state.run_stage = "awaiting_cab"
        except Exception as e:
            st.session_state.run_stage = "error"
            st.session_state.error_message = str(e)
    st.rerun()


# ─── Awaiting CAB ──────────────────────────────────────────────────────────────
if st.session_state.run_stage == "awaiting_cab":
    state = st.session_state.graph_state or {}
    render_progress("cab_review_node")

    # FISMA clock — most prominent element
    st.markdown("---")
    render_fisma_clock(state)

    # Triage summary
    st.markdown("---")
    st.markdown('<div class="section-header">Triage Results</div>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("FISMA Category", f"CAT {state.get('fisma_category', '?')} — {state.get('fisma_category_name', '')}")
    col2.metric("Severity", state.get("severity", "Unknown"))
    col3.metric("Citizens Affected", f"~{state.get('affected_citizens_estimate', 0):,}")
    col4.metric("SLO Breach", "YES" if state.get("slo_breach") else "NO")

    st.markdown(state.get("triage_summary", ""))

    # Tool findings tabs
    st.markdown('<div class="section-header">Tool Investigation Results</div>', unsafe_allow_html=True)
    tab_gh, tab_cw, tab_sp = st.tabs(["GitHub", "CloudWatch", "Splunk"])

    with tab_gh:
        github = state.get("github_findings", {})
        st.markdown(f"**Summary:** {github.get('summary', 'N/A')}")
        anomalies = github.get("anomalies", [])
        if anomalies:
            st.markdown("**Anomalies:**")
            for a in anomalies:
                st.markdown(f"- ⚠️ {a}")
        commits = github.get("raw_results", {}).get("commits", [])
        if commits:
            with st.expander(f"Recent commits ({len(commits)})"):
                for c in commits:
                    st.code(f"{c['sha']} | {c['author']} | {c['timestamp'][:10]}\n{c['message']}")

    with tab_cw:
        cw = state.get("cloudwatch_findings", {})
        st.markdown(f"**Summary:** {cw.get('summary', 'N/A')}")
        alarms = cw.get("raw_results", {}).get("active_alarms", [])
        if alarms:
            st.markdown(f"**🔴 {len(alarms)} active alarms:**")
            for a in alarms:
                st.markdown(f"- **{a['name']}**: {a['current_value']} (threshold: {a['threshold']}) — {a['reason'][:100]}")

    with tab_sp:
        sp = state.get("splunk_findings", {})
        st.markdown(f"**Summary:** {sp.get('summary', 'N/A')}")
        patterns = sp.get("raw_results", {}).get("top_error_patterns", [])
        if patterns:
            with st.expander(f"Top {len(patterns)} error patterns"):
                for p in patterns[:3]:
                    st.markdown(f"**#{p['rank']} ({p['count']:,} occurrences):** `{p['pattern'][:80]}`")
                    st.markdown(f"  → *{p['significance']}*")

    # Hypotheses
    st.markdown('<div class="section-header">Root Cause Hypotheses (Parallel Investigation)</div>', unsafe_allow_html=True)
    st.markdown(state.get("hypothesis_summary", ""))

    hypotheses = state.get("ranked_hypotheses", state.get("hypotheses", []))
    for h in hypotheses:
        status = h.get("status", "investigating")
        card_class = {"confirmed": "h-confirmed", "probable": "h-probable"}.get(status, "h-ruled-out")
        confidence = h.get("confidence", 0)
        bar = "█" * (confidence // 10) + "░" * (10 - confidence // 10)

        with st.expander(f"**{h.get('id', '?')}: {h.get('title', '')}** — {confidence}% [{bar}]"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Supporting Evidence:**")
                for e in h.get("supporting_evidence", []):
                    st.markdown(f"- ✅ {e}")
            with col2:
                st.markdown("**Contradicting Evidence:**")
                for e in h.get("contradicting_evidence", []):
                    st.markdown(f"- ❌ {e}")
            if h.get("next_investigation_step"):
                st.info(f"Next step: {h['next_investigation_step']}")

    # Blast radius
    st.markdown('<div class="section-header">Blast Radius & Citizen Impact</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    col1.metric("Estimated Citizens Affected", f"~{state.get('affected_citizens_estimate', 0):,}")
    col2.metric("Financial Impact", f"${state.get('estimated_financial_impact_per_hour', 0):,.0f}/hr")
    col3.metric("Privacy Act Triggered", "YES ⚠️" if state.get("privacy_act_triggered") else "NO ✅")
    st.markdown(state.get("blast_radius_summary", ""))

    # Compliance / notification matrix
    st.markdown('<div class="section-header">Stakeholder Notification Matrix</div>', unsafe_allow_html=True)
    notifications = state.get("notification_matrix", [])
    if notifications:
        for n in notifications:
            overdue = n.get("overdue", False)
            mins = n.get("minutes_remaining", 0)
            badge = "🔴 OVERDUE" if overdue else (f"🟡 {mins}m" if mins < 30 else f"🟢 {mins}m")
            st.markdown(
                f"{'`OVERDUE`' if overdue else ''} **{n['recipient']}** — "
                f"{n.get('deadline_label', 'TBD')} via {n['method']} {badge}"
            )

    if state.get("fisma_report_draft"):
        with st.expander("US-CERT Report Draft"):
            st.markdown(state["fisma_report_draft"])

    # ── CAB APPROVAL GATE ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-header">👤 Change Advisory Board (CAB) Review</div>', unsafe_allow_html=True)
    st.markdown('<div class="blameless-note">CAB approval is required before any remediation action is executed on production systems. '
                'Review the investigation above, then approve or deny the remediation plan.</div>', unsafe_allow_html=True)

    top_h = state.get("top_hypothesis", {})
    if top_h:
        st.markdown(f"**Recommended action:** Address root cause — *{top_h.get('title', 'Unknown')}* "
                    f"({top_h.get('confidence', 0)}% confidence)")

    cab_comments = st.text_area("CAB Comments / Instructions", height=80,
                                placeholder="Enter approval rationale, conditions, or revision instructions...")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ CAB Approved — Execute Remediation", type="primary", use_container_width=True):
            _resume_after_cab("approved", cab_comments)
    with col2:
        if st.button("❌ CAB Denied — Do Not Proceed", use_container_width=True):
            _resume_after_cab("denied", cab_comments)

    # Audit log
    with st.expander("🔒 Audit Trail (immutable investigation record)"):
        for entry in state.get("audit_log", []):
            st.markdown(
                f'<div class="audit-entry">[{entry.get("timestamp", "")[:19]}] '
                f'{entry.get("node", "")} → {entry.get("action", "")}: {entry.get("details", "")}</div>',
                unsafe_allow_html=True
            )


def _resume_after_cab(decision: str, comments: str):
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    graph = st.session_state.graph
    try:
        graph.update_state(config=config, values={
            "cab_status": decision,
            "cab_comments": comments,
            "cab_approver": "CAB Reviewer",
            "cab_timestamp": datetime.now().isoformat(),
        })
        with st.spinner("Executing remediation and generating post-mortem..."):
            result = graph.invoke(None, config=config)
            st.session_state.graph_state = result
            st.session_state.run_stage = "complete" if decision == "approved" else "denied"
        st.rerun()
    except Exception as e:
        st.session_state.run_stage = "error"
        st.session_state.error_message = str(e)
        st.rerun()


# ─── Complete ──────────────────────────────────────────────────────────────────
if st.session_state.run_stage == "complete":
    state = st.session_state.graph_state or {}
    render_progress("postmortem_agent")
    st.success("Incident investigation complete. Post-mortem generated.")

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Post-mortem", "🛠️ Remediation Steps", "🔒 Audit Trail", "📊 LangSmith"])

    with tab1:
        postmortem = state.get("postmortem_md", "Post-mortem not generated.")
        st.markdown(postmortem)
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("Download Post-mortem (Markdown)", data=postmortem,
                               file_name=f"postmortem_{state.get('incident_id', 'INC')}.md",
                               mime="text/markdown")
        with col2:
            html = state.get("postmortem_html", "")
            if html:
                st.download_button("Download Post-mortem (HTML)", data=html,
                                   file_name=f"postmortem_{state.get('incident_id', 'INC')}.html",
                                   mime="text/html")

    with tab2:
        steps = state.get("remediation_steps", [])
        for s in steps:
            risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(s.get("risk_level", "low"), "⬜")
            with st.expander(f"Step {s.get('step_number', '?')}: {s.get('action', '')[:60]}... {risk_icon}"):
                st.markdown(f"**Rationale:** {s.get('rationale', '')}")
                st.markdown(f"**Risk:** {risk_icon} {s.get('risk_level', 'unknown').upper()}")
                st.markdown(f"**Rollback:** {s.get('rollback', 'N/A')}")
                st.markdown(f"**Verification:** {s.get('verification', 'N/A')}")
                st.markdown(f"**Est. Recovery:** {s.get('estimated_recovery_time_minutes', '?')} minutes")

    with tab3:
        st.markdown("**Complete investigation audit trail (read-only):**")
        for entry in state.get("audit_log", []):
            st.markdown(
                f'<div class="audit-entry">[{entry.get("timestamp", "")[:19]}] '
                f'{entry.get("node", "")} → {entry.get("action", "")}: {entry.get("details", "")}</div>',
                unsafe_allow_html=True
            )

    with tab4:
        if st.session_state.langsmith_key:
            st.success("LangSmith traces available.")
            st.markdown(f"Project: **incident-response-agent** → Thread: **{st.session_state.thread_id}**")
        st.markdown("""
**What LangSmith shows for this agent:**
- Send() fan-out: all parallel hypothesis investigations as separate traces
- Per-tool latency (GitHub, CloudWatch, Splunk)
- CAB interrupt event + resume
- Full state at every node boundary
- Token usage breakdown across all 9 nodes
        """)

    if st.button("Start New Incident"):
        for k in ["graph_state", "run_stage", "thread_id"]:
            st.session_state[k] = None if k != "run_stage" else "setup"
        st.session_state.run_stage = "setup"
        st.rerun()


if st.session_state.run_stage == "denied":
    state = st.session_state.graph_state or {}
    st.warning("CAB denied the remediation plan. Incident remains open.")
    st.markdown(f"**CAB Comments:** {state.get('cab_comments', 'None')}")
    st.markdown("**Next steps:** Address CAB concerns and re-submit for approval, or escalate to CISO.")
    if st.button("Restart Investigation"):
        st.session_state.run_stage = "setup"
        st.rerun()


if st.session_state.run_stage == "error":
    st.error("Investigation failed:")
    st.code(st.session_state.error_message)
    if st.button("Reset"):
        st.session_state.run_stage = "setup"
        st.session_state.error_message = ""
        st.rerun()
