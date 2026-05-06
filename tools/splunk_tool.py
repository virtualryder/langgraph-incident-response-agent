"""
Splunk Tool — simulated Splunk log search for incident investigation.

In demo/offline mode: returns realistic log excerpts matching the incident signature.
In live mode: uses Splunk SDK with token auth (set SPLUNK_HOST, SPLUNK_TOKEN env vars).

Queries:
  - Error pattern frequency analysis
  - Timeline of first occurrence
  - Service-level log aggregation
  - Stack trace extraction
"""

import os
from datetime import datetime, timedelta
from typing import Optional


def query_splunk(
    incident_description: str,
    affected_systems: list[str],
    detection_time: Optional[str] = None,
    lookback_minutes: int = 60,
) -> dict:
    """
    Query Splunk for log patterns related to the incident.

    Returns a ToolFinding-compatible dict with log patterns and timeline.
    """
    splunk_host = os.environ.get("SPLUNK_HOST")
    splunk_token = os.environ.get("SPLUNK_TOKEN")

    if splunk_host and splunk_token:
        return _live_splunk_query(splunk_host, splunk_token, incident_description, lookback_minutes)
    else:
        return _simulated_splunk_query(incident_description, affected_systems, lookback_minutes)


def _live_splunk_query(host: str, token: str, description: str, minutes: int) -> dict:
    """Live Splunk query via Splunk SDK."""
    try:
        import splunklib.client as client
        import splunklib.results as results

        service = client.connect(
            host=host,
            port=8089,
            splunkToken=token,
        )

        queries = [
            f'search index=application earliest=-{minutes}m | stats count by log_level | where log_level="ERROR"',
            f'search index=application earliest=-{minutes}m "Exception" | top limit=10 message',
        ]

        all_results = []
        for query in queries:
            job = service.jobs.create(query, exec_mode="blocking")
            reader = results.JSONResultsReader(job.results(output_mode="json"))
            all_results.extend([r for r in reader if isinstance(r, dict)])

        return {
            "tool": "splunk",
            "query": f"Error patterns + exceptions (last {minutes}m)",
            "summary": f"Retrieved {len(all_results)} log aggregations.",
            "raw_results": all_results,
            "anomalies": [],
            "relevant_to_incident": bool(all_results),
        }

    except Exception as e:
        return _simulated_splunk_query([], [], minutes, error=str(e))


def _simulated_splunk_query(
    incident_description: str,
    affected_systems: list[str],
    minutes: int,
    error: Optional[str] = None,
) -> dict:
    """
    Realistic simulated Splunk output for the BEACON DB connection pool incident.

    Shows:
    - HikariCP connection timeout errors (primary pattern)
    - PostgreSQL max_connections errors (secondary confirmation)
    - Spring transaction rollbacks (downstream effect)
    - Timeline showing when first errors appeared
    """
    now = datetime.now()

    def ts(minutes_ago: int) -> str:
        return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S")

    # Top error patterns by frequency
    error_patterns = [
        {
            "rank": 1,
            "count": 18_742,
            "first_seen": ts(52),
            "last_seen": ts(1),
            "pattern": "HikariPool-1 - Connection is not available, request timed out after 30000ms",
            "source": "beacon-app-prod-*",
            "log_level": "ERROR",
            "component": "com.zaxxer.hikari.pool.HikariPool",
            "sample_lines": [
                f"{ts(52)} ERROR [beacon-app] [thread-pool-42] HikariPool-1 - Connection is not available, request timed out after 30000ms",
                f"{ts(48)} ERROR [beacon-app] [thread-pool-17] HikariPool-1 - Connection is not available, request timed out after 30000ms",
                f"{ts(12)} ERROR [beacon-app] [thread-pool-98] HikariPool-1 - Connection is not available, request timed out after 30000ms",
            ],
            "significance": "CRITICAL — This is the primary error. 30,000ms timeout matches the config change in commit a4f2c91.",
        },
        {
            "rank": 2,
            "count": 4_891,
            "first_seen": ts(49),
            "last_seen": ts(2),
            "pattern": "FATAL: remaining connection slots are reserved for non-replication superuser connections",
            "source": "beacon-rds-prod",
            "log_level": "ERROR",
            "component": "org.postgresql.util.PSQLException",
            "sample_lines": [
                f"{ts(49)} ERROR [beacon-app] org.postgresql.util.PSQLException: FATAL: remaining connection slots are reserved for non-replication superuser connections",
                f"{ts(35)} ERROR [beacon-app] org.postgresql.util.PSQLException: FATAL: remaining connection slots are reserved for non-replication superuser connections",
            ],
            "significance": "CONFIRMS database max_connections limit reached. PostgreSQL reserves final slots for superuser — app user is being rejected.",
        },
        {
            "rank": 3,
            "count": 31_208,
            "first_seen": ts(50),
            "last_seen": ts(0),
            "pattern": "Transaction silently rolled back because it has been marked as rollback-only",
            "source": "beacon-app-prod-*",
            "log_level": "ERROR",
            "component": "org.springframework.transaction.UnexpectedRollbackException",
            "sample_lines": [
                f"{ts(50)} ERROR [beacon-app] Transaction rolled back because it has been marked as rollback-only",
                f"{ts(30)} ERROR [beacon-app] Transaction rolled back because it has been marked as rollback-only",
            ],
            "significance": "Downstream effect of connection failures — all in-flight transactions rolling back.",
        },
        {
            "rank": 4,
            "count": 47_203,
            "first_seen": ts(51),
            "last_seen": ts(0),
            "pattern": "HTTP 503 Service Unavailable — /api/v2/claims/*",
            "source": "nginx-access-prod",
            "log_level": "ERROR",
            "component": "nginx",
            "sample_lines": [
                f'{ts(51)} [error] 2025/05/06 09:09:17 [error] connect() failed (111: Connection refused) while connecting to upstream',
                f'{ts(30)} 10.0.2.45 - - [{ts(30)}] "POST /api/v2/claims/weekly HTTP/1.1" 503 185 "-" "Mozilla/5.0"',
            ],
            "significance": "User-facing impact — 47,203 failed citizen requests in the last hour.",
        },
        {
            "rank": 5,
            "count": 3,
            "first_seen": ts(55),
            "last_seen": ts(53),
            "pattern": "HikariPool-1 - Pool stats (total=10, active=10, idle=0, waiting=47)",
            "source": "beacon-app-prod-*",
            "log_level": "WARN",
            "component": "com.zaxxer.hikari.pool.HikariPool",
            "sample_lines": [
                f"{ts(55)} WARN  [beacon-app] HikariPool-1 - Pool stats (total=10, active=10, idle=0, waiting=47)",
                f"{ts(54)} WARN  [beacon-app] HikariPool-1 - Pool stats (total=10, active=10, idle=0, waiting=189)",
                f"{ts(53)} WARN  [beacon-app] HikariPool-1 - Pool stats (total=10, active=10, idle=0, waiting=412)",
            ],
            "significance": "SMOKING GUN — Pool is maxed at 10 connections (total=10, idle=0). Queue growing from 47 to 412 waiting requests in 2 minutes.",
        },
    ]

    # First occurrence timeline
    first_occurrence_timeline = [
        {"timestamp": ts(58), "event": "Normal traffic, connection pool healthy (total=10, active=6, idle=4)"},
        {"timestamp": ts(55), "event": "FIRST WARN: Pool stats show total=10, active=10, idle=0, waiting=47 — pool full"},
        {"timestamp": ts(53), "event": "Waiting queue grows to 412 — requests accumulating"},
        {"timestamp": ts(52), "event": "FIRST ERROR: HikariPool connection timeout — 30,000ms wait exhausted"},
        {"timestamp": ts(51), "event": "FIRST HTTP 503 responses appearing in nginx logs"},
        {"timestamp": ts(49), "event": "PostgreSQL max_connections error — DB rejecting new connections"},
        {"timestamp": ts(47), "event": "CloudWatch alarm BEACON-App-ErrorRate-Critical triggers"},
        {"timestamp": ts(45), "event": "PagerDuty alert sent to on-call engineer"},
        {"timestamp": ts(40), "event": "Error rate reaches 78% — majority of requests failing"},
        {"timestamp": ts(28), "event": "Emergency hotfix PR #923 opened on GitHub"},
    ]

    # Log volume trend
    log_volume = [
        {"timestamp": ts(70), "error_count": 12,    "warn_count": 45,   "info_count": 8200},
        {"timestamp": ts(60), "error_count": 18,    "warn_count": 52,   "info_count": 8650},
        {"timestamp": ts(55), "error_count": 89,    "warn_count": 1240, "info_count": 7800},
        {"timestamp": ts(50), "error_count": 4821,  "warn_count": 890,  "info_count": 2100},
        {"timestamp": ts(40), "error_count": 12847, "warn_count": 441,  "info_count": 850},
        {"timestamp": ts(30), "error_count": 18204, "warn_count": 228,  "info_count": 420},
        {"timestamp": ts(20), "error_count": 21089, "warn_count": 184,  "info_count": 310},
        {"timestamp": ts(10), "error_count": 19847, "warn_count": 176,  "info_count": 290},
    ]

    anomalies = [
        "SMOKING GUN: HikariPool stats show maximumPoolSize=10 with 0 idle connections and 400+ waiting requests — pool is undersized for current load",
        f"First pool exhaustion warning appeared at {ts(55)} — 8 minutes before first user-facing errors",
        "30,000ms connection timeout (changed from 5,000ms in recent commit) is amplifying pool exhaustion — each failed request ties up a thread for 30 seconds",
        "PostgreSQL FATAL error confirms database-level connection limit reached (not just app pool)",
        f"47,203 failed citizen requests in the last hour across /api/v2/claims/* endpoints",
        "Error volume jumped 400x in under 5 minutes — characteristic of a cascading connection pool failure, not gradual degradation",
    ]

    summary = (
        "SPLUNK CONFIRMS ROOT CAUSE: HikariCP connection pool exhaustion. "
        "Pool stats show maximumPoolSize=10 (unchanged from config) with 0 idle connections "
        "and queues of 400+ waiting requests. The 30s timeout (commit a4f2c91, 36 hours ago) "
        "means each queued request holds a thread for 30 seconds before failing, "
        "amplifying the exhaustion cascade. 47,203 citizen requests have failed in the past hour. "
        "First pool warning appeared 8 minutes before user-facing errors — "
        "an alerting gap that should be closed as a corrective action."
    )

    return {
        "tool": "splunk",
        "query": f"Error patterns, pool stats, and timeline for BEACON portal (last {minutes}m)",
        "summary": summary,
        "raw_results": {
            "top_error_patterns": error_patterns,
            "first_occurrence_timeline": first_occurrence_timeline,
            "log_volume_trend": log_volume,
            "total_errors_in_window": 47_203,
            "error_rate_current": "89.3%",
        },
        "anomalies": anomalies,
        "relevant_to_incident": True,
        "simulated": True,
        "confirmed_root_cause_evidence": "HikariPool maximumPoolSize=10 with 400+ waiting — pool undersized",
    }
