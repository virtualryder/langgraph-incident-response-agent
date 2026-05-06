"""
GitHub Tool — simulated GitHub API for incident investigation.

In demo/offline mode: returns realistic fabricated data based on incident context.
In live mode: uses PyGithub with a personal access token (set GITHUB_TOKEN env var).

Queries:
  - Recent commits to affected service repos
  - Open issues matching incident keywords
  - Recent pull requests (especially hotfixes/reverts)
  - Workflow run failures
"""

import os
import re
from datetime import datetime, timedelta
from typing import Optional


def query_github(
    incident_description: str,
    affected_systems: list[str],
    repo: Optional[str] = None,
    hours_lookback: int = 48,
) -> dict:
    """
    Query GitHub for recent activity related to the incident.

    Returns a ToolFinding-compatible dict with commits, issues, PRs.
    """
    github_token = os.environ.get("GITHUB_TOKEN")

    if github_token and repo:
        return _live_github_query(github_token, repo, incident_description, hours_lookback)
    else:
        return _simulated_github_query(incident_description, affected_systems, hours_lookback)


def _live_github_query(token: str, repo: str, description: str, hours: int) -> dict:
    """Live GitHub API query via PyGithub."""
    try:
        from github import Github
        g = Github(token)
        gh_repo = g.get_repo(repo)
        since = datetime.now() - timedelta(hours=hours)

        commits = []
        for commit in gh_repo.get_commits(since=since):
            commits.append({
                "sha": commit.sha[:8],
                "message": commit.commit.message.split("\n")[0],
                "author": commit.commit.author.name,
                "timestamp": commit.commit.author.date.isoformat(),
                "files_changed": commit.files and len(commit.files) or 0,
            })

        issues = []
        keywords = _extract_keywords(description)
        for issue in gh_repo.get_issues(state="open", sort="updated"):
            if any(kw.lower() in issue.title.lower() for kw in keywords):
                issues.append({
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "created": issue.created_at.isoformat(),
                    "labels": [l.name for l in issue.labels],
                    "url": issue.html_url,
                })
            if len(issues) >= 5:
                break

        return {
            "tool": "github",
            "query": f"repo:{repo}, last {hours}h commits + open issues",
            "summary": f"Found {len(commits)} recent commits and {len(issues)} related open issues.",
            "raw_results": {"commits": commits[:10], "issues": issues},
            "anomalies": _detect_github_anomalies(commits),
            "relevant_to_incident": bool(commits or issues),
        }

    except Exception as e:
        return _simulated_github_query([], [], hours, error=str(e))


def _simulated_github_query(
    incident_description: str,
    affected_systems: list[str],
    hours: int,
    error: Optional[str] = None,
) -> dict:
    """
    Realistic simulated GitHub findings for the BEACON Benefits Portal incident.

    Scenario: DB connection pool exhaustion after a config change.
    The evidence trail points to a recent commit that increased timeout
    without proportionally increasing pool size.
    """
    now = datetime.now()

    commits = [
        {
            "sha": "a4f2c91",
            "message": "fix(db): increase HikariCP connection timeout to 30s — BEACON-4821",
            "author": "jmartinez",
            "timestamp": (now - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%S"),
            "files_changed": 2,
            "files": ["src/main/resources/application.properties", "src/main/resources/application-prod.properties"],
            "diff_summary": "+hikari.connectionTimeout=30000  (was 5000)\n+hikari.maximumPoolSize=10  (unchanged)",
        },
        {
            "sha": "b7d3e22",
            "message": "chore: bump spring-boot-starter-data-jpa to 3.3.2",
            "author": "automation-bot",
            "timestamp": (now - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S"),
            "files_changed": 1,
            "files": ["pom.xml"],
            "diff_summary": "Dependency version bump only.",
        },
        {
            "sha": "c1a9f44",
            "message": "feat: add weekly claim filing surge capacity warning — BEACON-4799",
            "author": "schen",
            "timestamp": (now - timedelta(hours=120)).strftime("%Y-%m-%dT%H:%M:%S"),
            "files_changed": 4,
            "files": ["MonitoringConfig.java", "AlertConfig.java"],
            "diff_summary": "Added CloudWatch alarm for connection pool utilization > 80%.",
        },
    ]

    issues = [
        {
            "number": 847,
            "title": "Database connection pool exhaustion during Monday morning filing surge",
            "state": "open",
            "created": (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S"),
            "updated": (now - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S"),
            "labels": ["bug", "performance", "database", "P2"],
            "body_preview": (
                "During peak filing windows (Monday 8-10 AM), the connection pool "
                "reaches capacity and new requests are queued or rejected. "
                "Current pool size: 10. Estimated concurrent users at peak: 12,000. "
                "Recommendation: increase maximumPoolSize to 50 and evaluate read replica."
            ),
            "url": "https://github.com/baystate-dta/beacon-portal/issues/847",
            "comments": 12,
        },
        {
            "number": 923,
            "title": "HOTFIX: Increase connection pool size — emergency deploy",
            "state": "open",
            "created": (now - timedelta(minutes=28)).strftime("%Y-%m-%dT%H:%M:%S"),
            "updated": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S"),
            "labels": ["hotfix", "emergency", "in-review"],
            "body_preview": (
                "Emergency hotfix for INC-2025-0847. "
                "Changes: hikari.maximumPoolSize 10 → 50, "
                "hikari.minimumIdle 2 → 10. "
                "Tested in staging. Awaiting CAB approval for prod deploy."
            ),
            "url": "https://github.com/baystate-dta/beacon-portal/pull/923",
            "comments": 3,
        },
    ]

    workflow_runs = [
        {
            "workflow": "Deploy to Production",
            "status": "failure",
            "conclusion": "failure",
            "timestamp": (now - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%S"),
            "triggered_by": "push to main (commit a4f2c91)",
            "error": "Health check failed: DB connection refused (3/3 retries)",
        },
        {
            "workflow": "Deploy to Production",
            "status": "success",
            "conclusion": "success",
            "timestamp": (now - timedelta(hours=38)).strftime("%Y-%m-%dT%H:%M:%S"),
            "triggered_by": "push to main (commit b7d3e22)",
        },
    ]

    anomalies = [
        "Commit a4f2c91 increased connection timeout 6x (5s → 30s) without increasing pool size — may cause thread exhaustion under load",
        "Issue #847 (connection pool exhaustion) was open for 90 days before this incident — unresolved known issue",
        "Emergency PR #923 opened 28 minutes ago — team is already working on hotfix",
        "Deploy pipeline failed after commit a4f2c91 — health check caught DB issue but deploy was force-merged",
    ]

    summary = (
        "CRITICAL FINDING: Commit a4f2c91 (36 hours ago, author: jmartinez) increased "
        "HikariCP connection timeout from 5s to 30s without increasing pool size (still 10). "
        "This means each connection now holds the slot 6x longer under failure conditions, "
        "causing pool exhaustion during the Monday morning filing surge. "
        "This matches open Issue #847 which documented this risk 90 days ago. "
        "An emergency hotfix PR (#923) is already open and awaiting CAB approval."
    )

    return {
        "tool": "github",
        "query": f"Recent commits + open issues for BEACON portal (last {hours}h)",
        "summary": summary,
        "raw_results": {
            "commits": commits,
            "issues": issues,
            "workflow_runs": workflow_runs,
        },
        "anomalies": anomalies,
        "relevant_to_incident": True,
        "simulated": True,
        "key_commit": "a4f2c91",
        "key_issue": 847,
        "hotfix_pr": 923,
    }


def _extract_keywords(text: str) -> list[str]:
    """Extract incident-relevant keywords for issue search."""
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "and", "or", "not"}
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    return [w for w in words if w not in stop_words][:8]


def _detect_github_anomalies(commits: list[dict]) -> list[str]:
    """Detect anomalous patterns in recent commits."""
    anomalies = []
    keywords = ["hotfix", "emergency", "revert", "rollback", "fix", "urgent"]
    for commit in commits:
        msg = commit.get("message", "").lower()
        if any(kw in msg for kw in keywords):
            anomalies.append(f"High-urgency commit detected: '{commit['message'][:80]}'")
    return anomalies
