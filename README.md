# AI Incident Response & Root Cause Analysis Agent
### Public Sector Edition

**Production-ready agentic workflow for government incident response per NIST SP 800-61.**

Built for forward-deployed AI architects who need portfolio projects that demonstrate real enterprise complexity — FISMA compliance, parallel reasoning, tool integration, and human approval gates — not generic chatbots.

---

## What This Demonstrates

| Capability | Implementation |
|---|---|
| FISMA incident classification | CAT 1-7 per NIST SP 800-61, live US-CERT countdown clock |
| Parallel hypothesis investigation | LangGraph `Send()` map-reduce pattern |
| Real tool integration | GitHub, CloudWatch, Splunk (simulated + live mode) |
| Citizen blast radius assessment | Impact estimate, SLO breach, Privacy Act trigger |
| Human-in-the-loop | Change Advisory Board (CAB) approval gate |
| Compliance package generation | US-CERT report draft, stakeholder notification matrix |
| Blameless post-mortem | NIST 800-61 format, 5 Whys, corrective actions |
| Full observability | LangSmith tracing, immutable audit trail |

---

## Agent Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Incident Response Agent — LangGraph                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [File Incident Report]                                                 │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────┐                                                        │
│  │triage_agent │  FISMA CAT 1-7 classification                         │
│  │             │  • US-CERT reporting deadline calculated               │
│  │ • CAT 1-7   │  • Severity P1-P4                                     │
│  │ • Countdown │  • PII/CUI flag → Privacy Act trigger                 │
│  │ • ATO risk  │  • ATO risk assessment                                │
│  └──────┬──────┘                                                        │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────┐     ┌──────────────┐                                  │
│  │  rag_agent  │────►│  tool_agent  │                                  │
│  │             │     │              │                                   │
│  │ • Runbooks  │     │ • GitHub     │  ← Recent commits, open issues   │
│  │ • Past      │     │ • CloudWatch │  ← Active alarms, metrics        │
│  │   incidents │     │ • Splunk     │  ← Error patterns, timeline      │
│  │ • NIST refs │     └──────┬───────┘                                  │
│  └─────────────┘            │                                          │
│                             ▼                                          │
│                  ┌──────────────────────┐                              │
│                  │ generate_hypotheses  │  LLM generates 4-5           │
│                  │                      │  competing root causes       │
│                  └──────────┬───────────┘                              │
│                             │                                          │
│            ┌────────────────┼────────────────┐                        │
│            │  Send() fan-out — runs in PARALLEL                        │
│            ▼                ▼                ▼                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │investigate   │  │investigate   │  │investigate   │  ...            │
│  │hypothesis H1 │  │hypothesis H2 │  │hypothesis H3 │                 │
│  │              │  │              │  │              │                 │
│  │ Confidence + │  │ Confidence + │  │ Confidence + │                 │
│  │ Evidence     │  │ Evidence     │  │ Evidence     │                 │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                 │
│         └─────────────────┼─────────────────┘                         │
│                           ▼                                            │
│                ┌────────────────────┐                                  │
│                │synthesize_hypotheses│  Rank by confidence             │
│                │                    │  Select top hypothesis           │
│                └──────────┬─────────┘                                  │
│                           │                                            │
│                           ▼                                            │
│                ┌────────────────────┐                                  │
│                │ blast_radius_agent │  Citizen impact estimate         │
│                │                    │  SLO breach determination        │
│                │ • Citizens affected│  Financial impact/hour           │
│                │ • SLO breach       │  Privacy Act trigger check       │
│                │ • $/hour impact    │                                  │
│                └──────────┬─────────┘                                  │
│                           │                                            │
│                           ▼                                            │
│                ┌────────────────────┐                                  │
│                │ compliance_agent   │  US-CERT report draft            │
│                │                    │  Notification matrix             │
│                │ • US-CERT draft    │  Privacy Act notification        │
│                │ • Notify matrix    │  ATO impact statement            │
│                │ • Countdowns       │                                  │
│                └──────────┬─────────┘                                  │
│                           │                                            │
│                           ▼                                            │
│                ┌────────────────────┐                                  │
│                │  cab_review_node   │  ◄── HUMAN-IN-THE-LOOP INTERRUPT │
│                │                    │                                  │
│                │ Change Advisory    │  Formal change package           │
│                │ Board reviews      │  presented to reviewer           │
│                │ remediation plan   │                                  │
│                │                    │                                  │
│                │ [Approve] ──────────────────────────────┐             │
│                │ [Deny] ──────────► END                  │             │
│                └────────────────────┘                    │             │
│                                                          ▼             │
│                                               ┌──────────────────┐    │
│                                               │  action_agent    │    │
│                                               │                  │    │
│                                               │ • Remediation    │    │
│                                               │   steps          │    │
│                                               │ • Rollback plan  │    │
│                                               └────────┬─────────┘    │
│                                                        │              │
│                                                        ▼              │
│                                               ┌──────────────────┐    │
│                                               │ postmortem_agent │    │
│                                               │                  │    │
│                                               │ NIST 800-61 fmt  │    │
│                                               │ • Timeline       │    │
│                                               │ • 5 Whys         │    │
│                                               │ • Corrective     │    │
│                                               │   actions        │    │
│                                               └────────┬─────────┘    │
│                                                        │              │
│                                                       END             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Stack

| Layer | Technology |
|---|---|
| Agent Orchestration | **LangGraph** 0.2+ — `Send()` parallel nodes, `interrupt_before` human gate |
| LLM | **OpenAI GPT-4o** via LangChain |
| Vector Store | **ChromaDB** — runbooks, past incidents, NIST controls |
| Tool: Code & Issues | **GitHub API** (PyGithub — live or simulated) |
| Tool: Metrics & Alarms | **AWS CloudWatch** (boto3 — live or simulated) |
| Tool: Log Analysis | **Splunk** (Splunk SDK — live or simulated) |
| Observability | **LangSmith** — per-node traces including parallel Send() spans |
| FISMA Reference | **NIST SP 800-61 Rev 2** — categories, reporting windows, procedures |
| Frontend | **Streamlit** — live FISMA countdown, hypothesis cards, CAB gate |

---

## Quick Start

```bash
# 1. Navigate to this folder
cd 03-incident-response-agent

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env — add OPENAI_API_KEY at minimum

# 5. Run
streamlit run app.py
```

Load the sample incident (`data/sample_incidents/beacon_portal_outage.txt`) and click **Launch Investigation**. No API keys required for GitHub, CloudWatch, or Splunk — all three tools run in realistic simulation mode by default.

---

## Project Structure

```
03-incident-response-agent/
├── app.py                          # Streamlit frontend — FISMA clock, hypotheses, CAB gate
├── requirements.txt
├── .env.example
│
├── graph/
│   ├── state.py                    # IncidentState TypedDict — all fields including audit_log
│   └── graph.py                    # LangGraph assembly — Send() routing, CAB interrupt
│
├── agents/
│   ├── triage.py                   # FISMA classification, reporting deadline, notification matrix
│   ├── rag_agent.py                # Runbook + past incident retrieval
│   ├── tool_agent.py               # Orchestrates GitHub + CloudWatch + Splunk
│   ├── hypothesis.py               # generate → Send() parallel → synthesize
│   ├── blast_radius.py             # Citizen impact, SLO breach, financial estimate
│   ├── compliance.py               # US-CERT report draft, notification countdowns
│   ├── action.py                   # Approved remediation steps + rollback plan
│   └── postmortem.py               # NIST 800-61 blameless post-mortem
│
├── tools/
│   ├── github_tool.py              # GitHub commits, issues, PRs (live + simulated)
│   ├── cloudwatch_tool.py          # Alarms, metrics timeline (live + simulated)
│   └── splunk_tool.py              # Error patterns, log timeline (live + simulated)
│
├── rag/
│   ├── vectorstore.py              # ChromaDB setup + knowledge base ingestion
│   └── retriever.py                # Multi-query retrieval
│
├── utils/
│   └── fisma.py                    # FISMA CAT 1-7 definitions, reporting windows,
│                                   # notification matrix builder, countdown calculator
│
└── data/
    ├── sample_incidents/
    │   └── beacon_portal_outage.txt     # Realistic P1 incident report (ready to run)
    └── knowledge_base/
        ├── runbooks/                    # DB connection pool, nginx, application runbooks
        ├── past_incidents/              # Prior incident reports with timelines + lessons
        ├── system_docs/                 # BEACON architecture documentation
        └── nist_controls/              # NIST SP 800-61 CAT 2 procedures
```

---

## The Parallel Hypothesis Pattern

This is the most architecturally distinctive feature of this project — and the part that demonstrates advanced LangGraph usage beyond what most demos show.

**How it works:**

```python
# In graph/graph.py — route after generate_hypotheses
workflow.add_conditional_edges(
    "generate_hypotheses",
    route_to_hypothesis_investigation,   # returns list of Send() calls
    ["investigate_hypothesis", "synthesize_hypotheses"],
)

# In agents/hypothesis.py — fan-out function
def route_to_hypothesis_investigation(state):
    return [
        Send("investigate_hypothesis", {**state, "current_hypothesis": h})
        for h in state["hypotheses"]
    ]
```

Each hypothesis gets its own graph execution in parallel. All four run simultaneously, each weighing the GitHub, CloudWatch, and Splunk evidence independently. The `synthesize_hypotheses` node collects all results via `Annotated[list, operator.add]` — LangGraph merges the parallel writes automatically.

This mirrors how real SRE teams work during major incidents: split into parallel investigation tracks, then reconvene with findings.

---

## FISMA Reporting Clock

The UI prominently displays a countdown to the US-CERT mandatory reporting deadline, calculated from detection time and FISMA category:

| Category | Type | Reporting Window |
|---|---|---|
| CAT 1 | Unauthorized Access | **1 hour** |
| CAT 2 | Denial of Service | **2 hours** |
| CAT 3 | Malicious Code | **1 hour** |
| CAT 4 | Improper Usage | **1 hour** |
| CAT 5 | Scans / Probes | Weekly digest |
| CAT 6 | Investigation | No hard SLA |
| CAT 7 | Explained Anomaly | No report required |

Missing the CAT 1/2/3/4 reporting window is itself a compliance violation. The clock turns yellow at 30 minutes and red at 20 minutes remaining.

---

## How the CAB Gate Works

LangGraph's `interrupt_before=["cab_review_node"]` creates a durable pause:

1. Graph runs through compliance_agent → pauses
2. Streamlit displays the full investigation: FISMA classification, tool findings, hypothesis ranking, blast radius, US-CERT report draft, notification matrix
3. CAB reviewer enters comments → clicks Approve or Deny
4. `graph.update_state()` injects `cab_status` and `cab_approver` into state
5. `graph.invoke(None, config)` resumes from the interrupt point
6. Approved → action_agent generates remediation steps → postmortem_agent
7. Denied → graph ends, incident remains open

The CAB decision is recorded in the immutable audit log alongside every node transition — the full investigation trail is available for IG/GAO review.

---

## Sample Scenario

**Agency:** Bay State Department of Benefits (fictional state agency)
**System:** BEACON — Benefits Eligibility and Case Management System
**Incident:** Citizen portal returning 503 errors during Monday morning claim filing window

The three tool simulations tell a coherent evidence trail:

- **GitHub**: Commit `a4f2c91` (36 hours ago) increased HikariCP connection timeout from 5s → 30s without increasing pool size. Emergency hotfix PR #923 already open.
- **CloudWatch**: `DatabaseConnections` alarm in ALARM state (497/500 connections). App CPU *below* normal — threads are blocking on DB wait, not executing.
- **Splunk**: `HikariPool stats (total=10, active=10, idle=0, waiting=412)` — pool is maxed with 400+ requests queued. 47,203 failed citizen requests in the past hour.

The hypothesis agent should converge on **connection pool exhaustion caused by config change** with high confidence. That convergence across independent tool evidence is the demo moment.

---

## Live Tool Mode

All three tools fall back to simulation automatically. To use live APIs:

```bash
# GitHub (real repo queries)
GITHUB_TOKEN=ghp_...

# CloudWatch (real AWS metrics)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1

# Splunk (real log search)
SPLUNK_HOST=splunk.youragency.gov
SPLUNK_TOKEN=...
```

The tool modules check for these env vars and route to the live implementation automatically — no code changes needed.

---

## LangSmith Observability

When `LANGSMITH_API_KEY` is set, every run produces:
- A separate trace span for each parallel `investigate_hypothesis` execution
- Per-tool latency (GitHub, CloudWatch, Splunk queries)
- Full input/output for every LLM call across all 10 nodes
- State snapshot at each node boundary
- CAB interrupt event and resume event with timestamp

The parallel hypothesis spans are especially useful — you can see that all four hypotheses were investigated simultaneously and compare their evidence across traces.

---

## Why This Matters for FDE / AI Architect Roles

This project demonstrates:

1. **Advanced LangGraph patterns** — `Send()` map-reduce, not just linear chains
2. **Regulatory compliance as a first-class feature** — FISMA, NIST 800-61, Privacy Act
3. **Tool use with realistic integrations** — not mocked stubs, but API-shaped tools with live fallback
4. **Production safety** — CAB gate, rollback plans, immutable audit trail
5. **Public sector domain expertise** — US-CERT, FISMA categories, ATO risk, IG/GAO accountability

When asked about this in an interview: *"I built a multi-agent LangGraph workflow that classifies incidents per FISMA, fans out parallel root cause hypotheses via Send(), queries GitHub, CloudWatch, and Splunk simultaneously, assesses citizen blast radius and SLO breach, routes through a Change Advisory Board approval gate, and produces a NIST SP 800-61 post-mortem — all with a live US-CERT reporting countdown and LangSmith observability."*

---

*Part of the "Production-Ready Agentic Workflow Templates" portfolio series.*
*Stack: LangGraph · LangChain · LangSmith · GitHub · CloudWatch · Splunk · ChromaDB · OpenAI GPT-4o · Streamlit*
