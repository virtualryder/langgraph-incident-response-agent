"""
CloudWatch Tool — simulated AWS CloudWatch metrics and alarms for incident investigation.

In demo/offline mode: returns realistic metric data showing the incident signature.
In live mode: uses boto3 with AWS credentials (set AWS_* env vars).

Queries:
  - Active alarms and alarm history
  - Key metrics: error rate, response time, DB connections, CPU, memory
  - Recent metric anomalies
"""

import os
from datetime import datetime, timedelta
from typing import Optional


def query_cloudwatch(
    system_name: str,
    incident_description: str,
    detection_time: Optional[str] = None,
    lookback_minutes: int = 60,
) -> dict:
    """
    Query CloudWatch for metrics and alarms related to the incident.

    Returns a ToolFinding-compatible dict.
    """
    aws_region = os.environ.get("AWS_DEFAULT_REGION")
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")

    if aws_key and aws_region:
        return _live_cloudwatch_query(system_name, detection_time, lookback_minutes)
    else:
        return _simulated_cloudwatch_query(system_name, detection_time, lookback_minutes)


def _live_cloudwatch_query(system_name: str, detection_time: Optional[str], minutes: int) -> dict:
    """Live CloudWatch query via boto3."""
    try:
        import boto3
        cw = boto3.client("cloudwatch")

        alarms = cw.describe_alarms(StateValue="ALARM")
        alarm_list = [
            {
                "name": a["AlarmName"],
                "state": a["StateValue"],
                "reason": a["StateReason"],
                "metric": a.get("MetricName", ""),
                "threshold": a.get("Threshold"),
                "timestamp": a["StateUpdatedTimestamp"].isoformat(),
            }
            for a in alarms.get("MetricAlarms", [])
        ]

        return {
            "tool": "cloudwatch",
            "query": f"Active ALARM state alarms + metrics for {system_name}",
            "summary": f"Found {len(alarm_list)} active alarms.",
            "raw_results": {"alarms": alarm_list},
            "anomalies": [a["reason"] for a in alarm_list],
            "relevant_to_incident": bool(alarm_list),
        }
    except Exception as e:
        return _simulated_cloudwatch_query(system_name, detection_time, minutes, error=str(e))


def _simulated_cloudwatch_query(
    system_name: str,
    detection_time: Optional[str],
    minutes: int,
    error: Optional[str] = None,
) -> dict:
    """
    Realistic simulated CloudWatch data for the BEACON DB connection pool incident.

    Shows the metric signature of connection pool exhaustion:
    - DatabaseConnections spiking to maximum
    - ApplicationErrorRate jumping to ~90%
    - Response time P99 collapsing
    - RDS CPU elevated but not maxed (confirms app-layer issue, not DB overload)
    """
    now = datetime.now()

    def ts(minutes_ago: int) -> str:
        return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:00")

    active_alarms = [
        {
            "name": "BEACON-RDS-DatabaseConnections-High",
            "state": "ALARM",
            "namespace": "AWS/RDS",
            "metric": "DatabaseConnections",
            "threshold": 450,
            "current_value": 497,
            "unit": "Count",
            "reason": "Threshold Crossed: 497 connections >= 450 (maximum pool capacity). "
                      "Alarm triggered at 09:12 AM.",
            "triggered_at": ts(48),
            "alarm_arn": "arn:aws:cloudwatch:us-east-1:123456789:alarm:BEACON-RDS-DatabaseConnections-High",
        },
        {
            "name": "BEACON-App-ErrorRate-Critical",
            "state": "ALARM",
            "namespace": "BEACON/Application",
            "metric": "HTTP5xxErrorRate",
            "threshold": 5.0,
            "current_value": 89.3,
            "unit": "Percent",
            "reason": "Error rate 89.3% exceeds critical threshold of 5%. "
                      "Predominantly 503 Service Unavailable responses.",
            "triggered_at": ts(45),
        },
        {
            "name": "BEACON-App-ResponseTime-P99",
            "state": "ALARM",
            "namespace": "BEACON/Application",
            "metric": "ResponseTime",
            "threshold": 5000,
            "current_value": 30127,
            "unit": "Milliseconds",
            "reason": "P99 response time 30,127ms exceeds SLO threshold of 5,000ms. "
                      "Requests are queuing waiting for DB connections.",
            "triggered_at": ts(47),
        },
    ]

    metrics_timeline = {
        "DatabaseConnections": {
            "description": "Active RDS connections (max pool: 500)",
            "normal_baseline": "45-80",
            "data_points": [
                {"timestamp": ts(70), "value": 62,  "state": "normal"},
                {"timestamp": ts(60), "value": 71,  "state": "normal"},
                {"timestamp": ts(50), "value": 124, "state": "elevated"},
                {"timestamp": ts(40), "value": 287, "state": "warning"},
                {"timestamp": ts(30), "value": 412, "state": "critical"},
                {"timestamp": ts(20), "value": 489, "state": "alarm"},
                {"timestamp": ts(10), "value": 497, "state": "alarm"},
                {"timestamp": ts(0),  "value": 495, "state": "alarm"},
            ],
        },
        "HTTP5xxErrorRate": {
            "description": "Percentage of 5xx responses (SLO: < 1%)",
            "normal_baseline": "0.1-0.3%",
            "data_points": [
                {"timestamp": ts(70), "value": 0.2,  "state": "normal"},
                {"timestamp": ts(60), "value": 0.3,  "state": "normal"},
                {"timestamp": ts(50), "value": 4.1,  "state": "warning"},
                {"timestamp": ts(40), "value": 31.7, "state": "critical"},
                {"timestamp": ts(30), "value": 78.2, "state": "alarm"},
                {"timestamp": ts(20), "value": 89.3, "state": "alarm"},
                {"timestamp": ts(10), "value": 91.1, "state": "alarm"},
                {"timestamp": ts(0),  "value": 88.7, "state": "alarm"},
            ],
        },
        "RDS_CPUUtilization": {
            "description": "RDS instance CPU (db.r6g.2xlarge)",
            "normal_baseline": "20-35%",
            "data_points": [
                {"timestamp": ts(70), "value": 28, "state": "normal"},
                {"timestamp": ts(60), "value": 31, "state": "normal"},
                {"timestamp": ts(50), "value": 52, "state": "elevated"},
                {"timestamp": ts(40), "value": 71, "state": "warning"},
                {"timestamp": ts(30), "value": 78, "state": "warning"},
                {"timestamp": ts(20), "value": 76, "state": "warning"},
                {"timestamp": ts(10), "value": 74, "state": "warning"},
                {"timestamp": ts(0),  "value": 73, "state": "warning"},
            ],
            "note": "CPU elevated but not maxed — confirms bottleneck is connection slots, not compute",
        },
        "EC2_CPUUtilization": {
            "description": "Application server CPU (average across ASG)",
            "normal_baseline": "30-50%",
            "data_points": [
                {"timestamp": ts(70), "value": 38, "state": "normal"},
                {"timestamp": ts(60), "value": 41, "state": "normal"},
                {"timestamp": ts(50), "value": 35, "state": "normal"},
                {"timestamp": ts(40), "value": 29, "state": "normal"},
                {"timestamp": ts(30), "value": 22, "state": "normal"},
                {"timestamp": ts(20), "value": 18, "state": "normal"},
            ],
            "note": "App CPU LOWER than normal — threads are blocked waiting on DB connections, not doing compute work",
        },
    }

    anomalies = [
        "DatabaseConnections spiking from 62 (normal) to 497 (near-max) over 70 minutes — consistent with connection timeout increase causing slots to hold longer",
        "HTTP 5xx error rate at 89.3% — virtually all requests failing",
        "RDS CPU elevated (78%) but NOT maxed — bottleneck is connection count, not database compute capacity",
        "Application server CPU BELOW normal (18-22%) — threads are blocking on DB wait, not executing",
        "P99 response time 30,127ms vs SLO of 5,000ms — 6x SLO breach",
        "Alarm BEACON-RDS-DatabaseConnections-High had ZERO previous triggers in last 30 days — this is a new failure mode",
    ]

    diagnostic_insight = (
        "METRIC PATTERN CONFIRMS CONNECTION POOL EXHAUSTION: "
        "The combination of (1) near-maximum DB connections, (2) near-zero app CPU, "
        "and (3) elevated but not maxed RDS CPU is the classic signature of connection pool exhaustion. "
        "Threads are queued waiting for a connection slot — they're not doing work, just waiting. "
        "The 30s timeout (increased from 5s in commit a4f2c91) means each failed connection attempt "
        "holds a thread for 30 seconds, amplifying the problem 6x versus previous behavior."
    )

    return {
        "tool": "cloudwatch",
        "query": f"Active alarms + key metrics for {system_name} (last {minutes} minutes)",
        "summary": diagnostic_insight,
        "raw_results": {
            "active_alarms": active_alarms,
            "metrics_timeline": metrics_timeline,
            "alarms_in_alarm_count": len(active_alarms),
        },
        "anomalies": anomalies,
        "relevant_to_incident": True,
        "simulated": True,
        "key_metric": "DatabaseConnections",
        "slo_breach": True,
        "slo_details": "P99 response time: 30,127ms vs SLO of 5,000ms (6x breach)",
    }
