"""
Tool Agent — orchestrates GitHub, CloudWatch, and Splunk queries.

Runs all three tools and synthesizes findings into a coherent
evidence summary for the hypothesis agent.
"""

from typing import Any
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from graph.state import IncidentState
from tools.github_tool import query_github
from tools.cloudwatch_tool import query_cloudwatch
from tools.splunk_tool import query_splunk


SYNTHESIS_PROMPT = """You are a senior SRE investigating a production incident at a government agency.
You have just received findings from three investigative tools. Synthesize them into a coherent
evidence narrative that will feed into root cause hypothesis generation.

INCIDENT: {incident_description}
SYSTEM: {system_name}

GITHUB FINDINGS:
{github_summary}
Key anomalies: {github_anomalies}

CLOUDWATCH FINDINGS:
{cloudwatch_summary}
Key anomalies: {cloudwatch_anomalies}

SPLUNK FINDINGS:
{splunk_summary}
Key anomalies: {splunk_anomalies}

Write a 3-4 paragraph synthesis that:
1. Identifies what the tools collectively confirm (the signal)
2. Identifies the most suspicious finding and why
3. Notes any conflicting evidence across tools
4. States what is still unknown and needs investigation

Write for a technical incident commander who needs to decide on root cause in the next 10 minutes.
Be direct. Lead with the most important finding.
"""


def tool_agent(state: IncidentState, llm: ChatOpenAI) -> dict[str, Any]:
    """
    LangGraph node: Query GitHub, CloudWatch, and Splunk.

    All three tool calls run sequentially here. In a production system
    these could be parallelized via asyncio or LangGraph's Send() API.
    """
    print("[Tool Agent] Querying GitHub, CloudWatch, and Splunk...")

    incident_description = state.get("incident_description", "")
    system_name = state.get("system_name", "Unknown System")
    affected_systems = state.get("affected_systems", [])
    detection_time = state.get("detection_time")

    # ── Query all three tools ─────────────────────────────────────────────────
    print("[Tool Agent] → Querying GitHub...")
    github = query_github(incident_description, affected_systems)

    print("[Tool Agent] → Querying CloudWatch...")
    cloudwatch = query_cloudwatch(system_name, incident_description, detection_time)

    print("[Tool Agent] → Querying Splunk...")
    splunk = query_splunk(incident_description, affected_systems, detection_time)

    # ── Synthesize findings ───────────────────────────────────────────────────
    try:
        response = llm.invoke([
            SystemMessage(content="You are a senior SRE and incident commander."),
            HumanMessage(content=SYNTHESIS_PROMPT.format(
                incident_description=incident_description,
                system_name=system_name,
                github_summary=github.get("summary", "No findings"),
                github_anomalies="\n".join(f"- {a}" for a in github.get("anomalies", [])),
                cloudwatch_summary=cloudwatch.get("summary", "No findings"),
                cloudwatch_anomalies="\n".join(f"- {a}" for a in cloudwatch.get("anomalies", [])),
                splunk_summary=splunk.get("summary", "No findings"),
                splunk_anomalies="\n".join(f"- {a}" for a in splunk.get("anomalies", [])),
            )),
        ])
        tool_summary = response.content.strip()
    except Exception as e:
        print(f"[Tool Agent] Synthesis error: {e}")
        tool_summary = "\n\n".join([
            f"GITHUB: {github.get('summary', 'N/A')}",
            f"CLOUDWATCH: {cloudwatch.get('summary', 'N/A')}",
            f"SPLUNK: {splunk.get('summary', 'N/A')}",
        ])

    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "node": "tool_agent",
        "action": "tools_queried",
        "details": f"GitHub: {len(github.get('anomalies', []))} anomalies | "
                   f"CloudWatch: {len(cloudwatch.get('anomalies', []))} anomalies | "
                   f"Splunk: {len(splunk.get('anomalies', []))} anomalies",
    }

    print(f"[Tool Agent] Tools complete. Anomalies: "
          f"GitHub={len(github.get('anomalies', []))}, "
          f"CW={len(cloudwatch.get('anomalies', []))}, "
          f"Splunk={len(splunk.get('anomalies', []))}")

    return {
        "github_findings": github,
        "cloudwatch_findings": cloudwatch,
        "splunk_findings": splunk,
        "tool_summary": tool_summary,
        "current_node": "tool_agent",
        "audit_log": [audit_entry],
    }
