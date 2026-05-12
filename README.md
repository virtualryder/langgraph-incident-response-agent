# AI Incident Response & Root Cause Analysis Agent
### Public Sector Edition

**A production-shaped AI agent that classifies an incident per FISMA, fans out parallel root-cause hypotheses across GitHub / CloudWatch / Splunk evidence, calculates citizen blast radius and the US-CERT reporting deadline, gates remediation behind a Change Advisory Board approval, and produces a NIST SP 800-61 blameless post-mortem — all with a live FISMA reporting countdown and an immutable audit trail ready for IG / GAO review.**

Built with LangGraph, OpenAI GPT-4o, and Streamlit. Deployable locally in minutes or to Railway with the `Dockerfile` and `railway.toml` included.

---

## The Problem This Solves

When a citizen-facing government system goes down, a state CIO has minutes — not hours — before three things happen simultaneously: the press notices, the legislature notices, and the FISMA reporting clock starts. Per NIST SP 800-61 Rev 2, agencies have **as little as one hour** to report certain incident categories to US-CERT, and missing that window is itself a compliance violation that lands in the next IG audit.

Meanwhile, the actual investigation looks like this:

1. **Triage** — figure out what FISMA category this is, what the reporting window is, and who needs to be notified
2. **Investigate** — pull logs from CloudWatch, error patterns from Splunk, recent commits and open issues from GitHub; weigh the evidence; converge on the most likely root cause
3. **Assess blast radius** — how many citizens are affected? Is the SLO breached? Is this a Privacy Act trigger?
4. **Draft compliance package** — US-CERT report, stakeholder notification matrix, ATO impact statement
5. **Get CAB approval** — Change Advisory Board reviews and approves the remediation plan
6. **Remediate and document** — execute the fix, then write a NIST 800-61 blameless post-mortem

This is structured work that's usually done sequentially by a team of three to five people across multiple time zones, under stress, with a clock running. The agent doesn't replace anyone — it does the parallel evidence-gathering and document drafting **in minutes instead of hours**, so the human responders spend their time on decisions instead of typing.

### Why this is an AI problem, not a runbook problem

A traditional incident runbook is a flowchart. It tells you to "check the database" or "verify the connection pool." It can't:

- Read four hours of CloudWatch metrics and notice that CPU went *down* while errors went *up* (threads blocking on DB wait, not executing)
- Cross-reference a recent GitHub commit's diff with a Splunk error pattern that started exactly 36 hours later
- Hold four competing hypotheses in working memory and update confidence as evidence accumulates
- Draft a US-CERT report that cites the specific commit, the specific alarm, and the specific error rate

That cross-evidence reasoning is exactly what LLMs are good at — and exactly what a runbook can't do. The agent's job is to weave the parallel evidence streams into a coherent narrative; the human's job is to decide what to do about it.

---

## Why This Was Built

This project demonstrates what a **responsible** AI agent for a regulated incident-response workflow looks like. The goal is not to automate the decision — the CAB approval, the remediation, and the US-CERT submission are all human responsibilities. The goal is to eliminate the documentation-and-evidence-assembly toil between "we have an alert" and "we have a complete, defensible response package ready for the CAB to review."

The architecture makes several deliberate choices that matter in public sector:

- **The LLM extracts and synthesizes. Python decides.** FISMA classification, reporting deadlines, and notification matrices are deterministic code — not LLM guesses.
- **Evidence comes from real tool surfaces, not hallucinations.** GitHub, CloudWatch, and Splunk tools query real APIs when credentials are present, with realistic simulation when they're not. The agent can't make up a commit hash; it can only cite one that exists.
- **No auto-remediation.** Remediation plans are drafted; the CAB approves; humans execute. The agent removes toil; it does not remove human authority.
- **The CAB gate is a true graph interrupt.** LangGraph pauses; the reviewer's decision is durably injected into state; the graph resumes. No background processes, no out-of-band channels — the audit trail is one coherent record.
- **Every node transition is logged.** The audit log is the IG/GAO artifact. It captures every input, every decision, every approval, and every state snapshot.

---

## What This Demonstrates

| Capability | Implementation |
|---|---|
| FISMA incident classification | CAT 1-7 per NIST SP 800-61, with live US-CERT countdown clock |
| Parallel hypothesis investigation | LangGraph `Send()` map-reduce pattern — 4-5 hypotheses investigated simultaneously |
| Real tool integration | GitHub, CloudWatch, Splunk — live mode when credentials are present, realistic simulation otherwise |
| Citizen blast radius assessment | Impact estimate, SLO breach determination, Privacy Act trigger, dollars/hour |
| Human-in-the-loop | Change Advisory Board (CAB) approval gate via `interrupt_before` |
| Compliance package generation | US-CERT report draft, stakeholder notification matrix, ATO impact statement |
| Blameless post-mortem | NIST 800-61 format with timeline, 5 Whys, and corrective actions |
| Full observability | LangSmith tracing with per-hypothesis spans, immutable audit trail |
| Deployable | Multi-stage Dockerfile + `railway.toml`; Streamlit on `$PORT`; persistent volume for audit + Chroma |

---

## How It Works

The agent is a **LangGraph graph** — a directed graph where each node is a Python function and the edges represent routing decisions. The most architecturally distinctive piece is the parallel hypothesis investigation: LangGraph's `Send()` API fans out one investigator per hypothesis, all running simultaneously across the GitHub / CloudWatch / Splunk evidence corpora.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Incident Response Agent — LangGraph                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [File Incident Report]                                                 │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────┐                                                        │
│  │triage_agent │  FISMA CAT 1-7 classification                          │
│  │             │  • US-CERT reporting deadline calculated               │
│  │ • CAT 1-7   │  • Severity P1-P4                                      │
│  │ • Countdown │  • PII/CUI flag → Privacy Act trigger                  │
│  │ • ATO risk  │  • ATO risk assessment                                 │
│  └──────┬──────┘                                                        │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────┐     ┌──────────────┐                                   │
│  │  rag_agent  │────►│  tool_agent  │                                   │
│  │             │     │              │                                   │
│  │ • Runbooks  │     │ • GitHub     │  ← Recent commits, open issues    │
│  │ • Past      │     │ • CloudWatch │  ← Active alarms, metrics         │
│  │   incidents │     │ • Splunk     │  ← Error patterns, timeline       │
│  │ • NIST refs │     └──────┬───────┘                                   │
│  └─────────────┘            │                                           │
│                             ▼                                           │
│                  ┌──────────────────────┐                               │
│                  │ generate_hypotheses  │  LLM generates 4-5            │
│                  │                      │  competing root causes        │
│                  └──────────┬───────────┘                               │
│                             │                                           │
│            ┌────────────────┼────────────────┐                          │
│            │  Send() fan-out — runs in PARALLEL                         │
│            ▼                ▼                ▼                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │investigate   │  │investigate   │  │investigate   │  ...              │
│  │hypothesis H1 │  │hypothesis H2 │  │hypothesis H3 │                   │
│  │              │  │              │  │              │                   │
│  │ Confidence + │  │ Confidence + │  │ Confidence + │                   │
│  │ Evidence     │  │ Evidence     │  │ Evidence     │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
│         └─────────────────┼─────────────────┘                           │
│                           ▼                                             │
│                ┌────────────────────┐                                   │
│                │synthesize_hypotheses│ Rank by confidence               │
│                │                    │ Select top hypothesis             │
│                └──────────┬─────────┘                                   │
│                           │                                             │
│                           ▼                                             │
│                ┌────────────────────┐                                   │
│                │ blast_radius_agent │  Citizen impact estimate          │
│                │                    │  SLO breach determination         │
│                │ • Citizens affected│  Financial impact/hour            │
│                │ • SLO breach       │  Privacy Act trigger check        │
│                │ • $/hour impact    │                                   │
│                └──────────┬─────────┘                                   │
│                           │                                             │
│                           ▼                                             │
│                ┌────────────────────┐                                   │
│                │ compliance_agent   │  US-CERT report draft             │
│                │                    │  Notification matrix              │
│                │ • US-CERT draft    │  Privacy Act notification         │
│                │ • Notify matrix    │  ATO impact statement             │
│                │ • Countdowns       │                                   │
│                └──────────┬─────────┘                                   │
│                           │                                             │
│                           ▼                                             │
│                ┌────────────────────┐                                   │
│                │  cab_review_node   │  ◄── HUMAN-IN-THE-LOOP INTERRUPT  │
│                │                    │                                   │
│                │ Change Advisory    │  Formal change package            │
│                │ Board reviews      │  presented to reviewer            │
│                │ remediation plan   │                                   │
│                │                    │                                   │
│                │ [Approve] ──────────────────────────────┐              │
│                │ [Deny] ──────────► END                  │              │
│                └────────────────────┘                    │              │
│                                                          ▼              │
│                                               ┌──────────────────┐     │
│                                               │  action_agent    │     │
│                                               │                  │     │
│                                               │ • Remediation    │     │
│                                               │   steps          │     │
│                                               │ • Rollback plan  │     │
│                                               └────────┬─────────┘     │
│                                                        │               │
│                                                        ▼               │
│                                               ┌──────────────────┐     │
│                                               │ postmortem_agent │     │
│                                               │                  │     │
│                                               │ NIST 800-61 fmt  │     │
│                                               │ • Timeline       │     │
│                                               │ • 5 Whys         │     │
│                                               │ • Corrective     │     │
│                                               │   actions        │     │
│                                               └────────┬─────────┘     │
│                                                        │               │
│                                                       END              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

**Parallel hypothesis pattern.** Each hypothesis gets its own graph execution in parallel via `Send()`. All four run simultaneously, each weighing the GitHub / CloudWatch / Splunk evidence independently. The `synthesize_hypotheses` node collects all results via `Annotated[list, operator.add]`. This mirrors how real SRE teams work during major incidents: split into parallel investigation tracks, then reconvene with findings.

**FISMA classification as deterministic policy.** Triage uses code (not LLM judgment) to map an incident's properties onto the FISMA CAT 1-7 table. Reporting windows, notification matrices, and Privacy Act triggers are all functions of category — not LLM guesses. The LLM extracts incident facts; deterministic code applies the policy.

**Live + simulation tool modes.** Every tool integration (GitHub, CloudWatch, Splunk) checks for credentials and uses the live API when present, falling back to a realistic simulation when not. This makes the demo work out-of-the-box and the production path obvious.

**CAB gate as a true graph interrupt.** `interrupt_before=["cab_review_node"]` pauses the graph. The Streamlit UI surfaces the full investigation; the reviewer's decision is written into state via `graph.update_state()`; `graph.invoke(None, config)` resumes from the pause. The audit log records the entire transition with timestamps.

**Immutable audit log.** Every node transition, tool invocation, and approval/denial appends a JSONL row. In production, this would ship to CloudWatch Logs or Splunk. The audit log is the IG/GAO artifact — it's what proves the agency followed process under regulatory review.

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

## Technology Stack

| Layer | Technology |
|---|---|
| Agent orchestration | **LangGraph** 0.2+ — `Send()` parallel nodes, `interrupt_before` human gate |
| LLM | **OpenAI GPT-4o** via LangChain |
| Vector store | **ChromaDB** — runbooks, past incidents, NIST controls |
| Tool: Code & Issues | **GitHub API** (PyGithub — live or simulated) |
| Tool: Metrics & Alarms | **AWS CloudWatch** (boto3 — live or simulated) |
| Tool: Log Analysis | **Splunk** (Splunk SDK — live or simulated) |
| Observability | **LangSmith** — per-node traces, parallel `Send()` spans |
| FISMA reference | **NIST SP 800-61 Rev 2** — categories, reporting windows, procedures |
| Frontend | **Streamlit** — FISMA countdown, hypothesis cards, CAB gate |
| Deployment | **Docker** multi-stage build + **Railway** IaC |

---

## Installation

```bash
git clone <repo-url>
cd 03-incident-response-agent

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Set OPENAI_API_KEY at minimum.
```

## Deploy to Railway

The project ships with a multi-stage `Dockerfile` and `railway.toml`, same pattern as the other agents in this portfolio:

1. Push to a GitHub repo (e.g., `incident-response-agent`).
2. In [Railway](https://railway.app/new), choose **Deploy from GitHub repo** and pick the repo.
3. Railway detects `railway.toml`, builds with the `Dockerfile`, and starts the container on a public URL. Streamlit's `/_stcore/health` is wired as the healthcheck.
4. In the service's **Variables** tab, set:
   - `OPENAI_API_KEY` — required
   - (optional) `LANGSMITH_API_KEY`, `LANGCHAIN_TRACING_V2=true` for tracing
   - (optional) `GITHUB_TOKEN`, `AWS_*` credentials, `SPLUNK_HOST` + `SPLUNK_TOKEN` to enable live tool mode
5. In **Settings → Volumes**, create a 1 GB volume mounted at `/data`. The Dockerfile sets `AUDIT_LOG_DIR=/data/audit` and `CHROMA_PERSIST_DIR=/data/chroma` so both the audit trail and the Chroma knowledge base survive redeploys.
6. Every push to the connected branch redeploys.

### Running the container locally

```bash
docker build -t incident-response-agent .

docker run --rm -p 8501:8501 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -v $(pwd)/data/audit:/data/audit \
  -v $(pwd)/data/chroma:/data/chroma \
  incident-response-agent
```

Open `http://localhost:8501`.

---

## Running

### Streamlit demo

```bash
streamlit run app.py
```

Load the sample incident at `data/sample_incidents/beacon_portal_outage.txt` and click **Launch Investigation**. No API keys required for GitHub, CloudWatch, or Splunk — all three tools run in realistic simulation mode by default.

### Live tool mode

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

## How the CAB Gate Works

LangGraph's `interrupt_before=["cab_review_node"]` creates a durable pause:

1. Graph runs through `compliance_agent` → pauses
2. Streamlit displays the full investigation: FISMA classification, tool findings, hypothesis ranking, blast radius, US-CERT report draft, notification matrix
3. CAB reviewer enters comments → clicks Approve or Deny
4. `graph.update_state()` injects `cab_status` and `cab_approver` into state
5. `graph.invoke(None, config)` resumes from the interrupt point
6. Approved → `action_agent` generates remediation steps → `postmortem_agent`
7. Denied → graph ends; incident remains open

The CAB decision is recorded in the immutable audit log alongside every node transition. The full investigation trail is available for IG / GAO review.

---

## LangSmith Observability

When `LANGSMITH_API_KEY` is set, every run produces:

- A separate trace span for each parallel `investigate_hypothesis` execution
- Per-tool latency (GitHub, CloudWatch, Splunk queries)
- Full input/output for every LLM call across all 10 nodes
- State snapshot at each node boundary
- CAB interrupt event and resume event with timestamps

The parallel hypothesis spans are especially useful — you can see that all four hypotheses were investigated simultaneously and compare their evidence across traces.

---

## Security Considerations

Incident response is itself a sensitive workflow — the agent has access to telemetry that often includes incidental PII/CUI and is used to make decisions that the agency will need to defend under audit. The architecture below mitigates the principal failure modes.

**Least-privilege LLM scope.** The LLM extracts incident facts, generates hypotheses, and drafts compliance text. It does not directly call GitHub / CloudWatch / Splunk APIs — those calls go through Python tool wrappers that the agent invokes by name. Tool credentials are never exposed to the LLM prompt.

**Deterministic compliance logic.** FISMA classification, reporting windows, and notification matrices are deterministic policy code (`utils/fisma.py`), not LLM output. A prompt regression cannot change the reporting deadline; only a code review can.

**No auto-remediation.** Remediation steps are drafted; the CAB approves; humans execute. The agent does not have credentials to make changes to production systems.

**CAB gate cannot be bypassed.** Without an explicit approve/deny decision in state, the graph cannot reach `action_agent`. The interrupt is enforced at the graph layer.

**Immutable audit log.** Every node transition, tool invocation, and CAB decision is appended to a JSONL audit log with a timestamp and the actor identity. The log is append-only at the application layer; production deployments should also enforce append-only at storage (CloudWatch Logs with retention policy, S3 with Object Lock, etc.).

**Bring-your-own credentials for live tools.** No tool credentials ship with the project. Live mode is opt-in by setting environment variables; absent them, the tools use realistic but synthetic data.

**LangSmith caveat.** LangSmith tracing is opt-in. Do not enable it on real production incident data without confirming your agreement covers the telemetry captured.

---

## Customizing for Your Environment

**Replace the simulation data with your own runbooks.** Drop your agency's runbooks into `data/knowledge_base/runbooks/` and your past incident reports into `data/knowledge_base/past_incidents/`. The RAG retriever picks them up on startup.

**Wire in your real telemetry.** Each tool module (`tools/github_tool.py`, `tools/cloudwatch_tool.py`, `tools/splunk_tool.py`) has a clean separation between the simulated and live code paths. Add credentials → live mode activates automatically. To add a new tool (PagerDuty, ServiceNow, Datadog), follow the same pattern: a class with a `query()` method, live + simulated branches, registration in `agents/tool_agent.py`.

**Adjust FISMA classification rules.** `utils/fisma.py` encodes the CAT 1-7 mapping and reporting windows. If your agency interprets the categories differently (some do), the policy lives in one place and is straightforward to adjust.

**Swap LLM providers.** The project uses `langchain-openai` today. To switch to Anthropic Claude or Bedrock, replace `ChatOpenAI` instances in the agent modules with `ChatAnthropic` or `ChatBedrock`. LangChain's structured-output and tool-binding APIs are consistent across providers.

**Add new hypothesis investigators.** The map-reduce pattern accepts any number of hypotheses. To add a new investigation lens (network forensics, third-party API monitoring, internal service mesh telemetry), add a tool wrapper, expose it to `tool_agent.py`, and the hypothesis investigator picks it up.

---

## Future Enhancements

The current build is a working portfolio-quality system. Reasonable production extensions:

- **ReAct-style secondary investigation mode.** Today the agent generates N hypotheses upfront and investigates in parallel (good for major incidents). A complementary mode where the agent dynamically chooses the next tool to call based on what it's found (good for tier-1 SOC triage on smaller alerts) would let the same codebase showcase two distinct agentic patterns.
- **Additional incident scenarios.** The current sample is the BEACON connection pool exhaustion. Adding credential compromise / impossible travel, malware on endpoint, and phishing-reported email would round out the demo across incident classes.
- **PagerDuty / ServiceNow integration.** When the CAB approves, the agent could auto-open the change ticket in the agency's ITSM (still without executing the change itself).
- **Real-time stream from SIEM.** Today the agent processes one incident at a time from a filed report. A streaming intake from Splunk Enterprise Security or Microsoft Sentinel would make this an "always-on" tier-1 triage agent.
- **Append-only audit log to a SIEM.** Today the audit log is JSONL on a Railway volume. Production deployments would ship it to CloudWatch Logs / Splunk / a dedicated audit warehouse with cryptographic chaining.
- **Multi-tenant for state vs. agency teams.** Same agent, different runbooks and FISMA rule overlays per agency, gated by SSO group membership.

---

## Why This Matters for FDE / AI Architect Roles

This project demonstrates:

1. **Advanced LangGraph patterns** — `Send()` map-reduce, not just linear chains
2. **Regulatory compliance as a first-class feature** — FISMA, NIST 800-61, Privacy Act
3. **Tool use with realistic integrations** — not mocked stubs, but API-shaped tools with live fallback
4. **Production safety** — CAB gate, rollback plans, immutable audit trail
5. **Public sector domain expertise** — US-CERT, FISMA categories, ATO risk, IG/GAO accountability
6. **Deployable** — multi-stage Docker image, Railway IaC, persistent volume strategy

When asked about this in an interview: *"I built a multi-agent LangGraph workflow that classifies incidents per FISMA, fans out parallel root cause hypotheses via Send(), queries GitHub, CloudWatch, and Splunk simultaneously, assesses citizen blast radius and SLO breach, routes through a Change Advisory Board approval gate, and produces a NIST SP 800-61 post-mortem — all with a live US-CERT reporting countdown, LangSmith observability, and Railway-deployable Docker packaging."*

---

## Repository Structure

```
03-incident-response-agent/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── Dockerfile                          # Multi-stage prod image, non-root
├── .dockerignore
├── railway.toml                        # Railway IaC: Docker build + healthcheck
├── .streamlit/config.toml              # Streamlit server settings
├── app.py                              # Streamlit frontend — FISMA clock, hypotheses, CAB gate
│
├── graph/
│   ├── state.py                        # IncidentState TypedDict — all fields including audit_log
│   └── graph.py                        # LangGraph assembly — Send() routing, CAB interrupt
│
├── agents/
│   ├── triage.py                       # FISMA classification, reporting deadline, notification matrix
│   ├── rag_agent.py                    # Runbook + past incident retrieval
│   ├── tool_agent.py                   # Orchestrates GitHub + CloudWatch + Splunk
│   ├── hypothesis.py                   # generate → Send() parallel → synthesize
│   ├── blast_radius.py                 # Citizen impact, SLO breach, financial estimate
│   ├── compliance.py                   # US-CERT report draft, notification countdowns
│   ├── action.py                       # Approved remediation steps + rollback plan
│   └── postmortem.py                   # NIST 800-61 blameless post-mortem
│
├── tools/
│   ├── github_tool.py                  # GitHub commits, issues, PRs (live + simulated)
│   ├── cloudwatch_tool.py              # Alarms, metrics timeline (live + simulated)
│   └── splunk_tool.py                  # Error patterns, log timeline (live + simulated)
│
├── rag/
│   ├── vectorstore.py                  # ChromaDB setup + knowledge base ingestion
│   └── retriever.py                    # Multi-query retrieval
│
├── utils/
│   └── fisma.py                        # FISMA CAT 1-7 definitions, reporting windows,
│                                       # notification matrix builder, countdown calculator
│
└── data/
    ├── sample_incidents/
    │   └── beacon_portal_outage.txt    # Realistic P1 incident report (ready to run)
    └── knowledge_base/
        ├── runbooks/                   # DB connection pool, nginx, application runbooks
        ├── past_incidents/             # Prior incident reports with timelines + lessons
        ├── system_docs/                # BEACON architecture documentation
        └── nist_controls/              # NIST SP 800-61 CAT 2 procedures
```

---

## License

MIT (see `LICENSE`). Fictional agency data, runbooks, and incident reports are released under the same license. No real PII, CUI, or production telemetry is present.

---

*Part of the "Production-Ready Agentic Workflow Templates" portfolio series.*
*Stack: LangGraph · LangChain · LangSmith · GitHub · CloudWatch · Splunk · ChromaDB · OpenAI GPT-4o · Streamlit · Docker · Railway*
