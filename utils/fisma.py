"""
FISMA Incident Category Definitions — NIST SP 800-61 Rev 2

Reference: https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r2.pdf
US-CERT Federal Incident Notification Guidelines

These definitions drive:
  - Mandatory US-CERT reporting timelines
  - Severity classification
  - Notification matrix triggers
  - ATO risk flags
"""

from datetime import datetime, timedelta
from typing import Optional


# ─── FISMA Category Definitions ───────────────────────────────────────────────

FISMA_CATEGORIES = {
    1: {
        "name": "Unauthorized Access",
        "description": (
            "An individual gains logical or physical access without permission "
            "to a federal agency network, system, application, data, or other resource."
        ),
        "reporting_window_hours": 1,
        "examples": [
            "Compromised credentials used to access system",
            "Privilege escalation beyond authorized level",
            "Physical access to restricted area",
            "Unauthorized access to PII/CUI data",
        ],
        "ato_risk": True,
        "pii_risk": True,
        "us_cert_required": True,
    },
    2: {
        "name": "Denial of Service (DoS)",
        "description": (
            "An attack that successfully prevents or impairs the normal authorized "
            "functionality of networks, systems, or applications by exhausting resources. "
            "Includes both external attacks and accidental resource exhaustion."
        ),
        "reporting_window_hours": 2,
        "examples": [
            "Citizen portal unavailable due to traffic flood",
            "Database connection pool exhausted under load",
            "CPU/memory exhaustion causing system unresponsiveness",
            "API gateway overloaded by malformed requests",
        ],
        "ato_risk": False,
        "pii_risk": False,
        "us_cert_required": True,
    },
    3: {
        "name": "Malicious Code",
        "description": (
            "Successful installation of malicious software (e.g., virus, worm, Trojan horse, "
            "or other code-based malicious entity) that infects an operating system or application."
        ),
        "reporting_window_hours": 1,
        "examples": [
            "Ransomware detected on workstation",
            "Malware found in application dependency",
            "Backdoor discovered in deployed code",
            "Supply chain compromise detected",
        ],
        "ato_risk": True,
        "pii_risk": True,
        "us_cert_required": True,
    },
    4: {
        "name": "Improper Usage",
        "description": (
            "A person violates acceptable computing use policies. Includes misuse of "
            "agency systems for personal gain, data exfiltration by insiders, or "
            "policy violations by authorized users."
        ),
        "reporting_window_hours": 1,
        "examples": [
            "Employee accessing records without business need",
            "Data downloaded to unauthorized device",
            "System used for non-official purposes",
            "Sharing credentials with unauthorized personnel",
        ],
        "ato_risk": True,
        "pii_risk": True,
        "us_cert_required": True,
    },
    5: {
        "name": "Scans / Probes / Attempted Access",
        "description": (
            "A security tool, person, or application actively searches for "
            "vulnerabilities or open ports but has not yet successfully compromised "
            "any system. Includes network scans, vulnerability scans, and brute force attempts."
        ),
        "reporting_window_hours": 168,  # Weekly
        "examples": [
            "Port scan detected from external IP",
            "Brute force login attempts on VPN",
            "Vulnerability scanner detected against .gov asset",
            "SQL injection probes in web logs",
        ],
        "ato_risk": False,
        "pii_risk": False,
        "us_cert_required": False,  # Report in weekly digest
    },
    6: {
        "name": "Investigation",
        "description": (
            "An unconfirmed incident that is potentially malicious or anomalous activity "
            "deemed by the reporting entity to warrant further review."
        ),
        "reporting_window_hours": None,  # No hard SLA
        "examples": [
            "Unusual login patterns requiring investigation",
            "Anomalous network traffic of unclear origin",
            "Unexplained performance degradation",
            "User-reported suspicious behavior",
        ],
        "ato_risk": False,
        "pii_risk": False,
        "us_cert_required": False,
    },
    7: {
        "name": "Explained Anomaly",
        "description": (
            "Activity that was initially reported as suspicious but has been confirmed "
            "to be benign (e.g., authorized pen testing, system maintenance, "
            "or misconfigured monitoring alert)."
        ),
        "reporting_window_hours": None,
        "examples": [
            "Authorized penetration test flagged as intrusion",
            "Scheduled maintenance window triggered false alert",
            "Misconfigured monitoring threshold",
        ],
        "ato_risk": False,
        "pii_risk": False,
        "us_cert_required": False,
    },
}

# FISMA severity to priority mapping
SEVERITY_MAP = {
    "P1": "Critical — system unavailable, citizen services impacted at scale",
    "P2": "High — significant degradation, partial service unavailability",
    "P3": "Medium — noticeable impact, workaround available",
    "P4": "Low — minimal impact, informational",
}

# Stakeholder notification matrix by FISMA category + severity
NOTIFICATION_MATRIX = {
    "P1": [
        {"recipient": "CISO",              "window_minutes": 15,   "method": "phone"},
        {"recipient": "System Owner",       "window_minutes": 15,   "method": "phone"},
        {"recipient": "CIO",               "window_minutes": 30,   "method": "phone"},
        {"recipient": "US-CERT / CISA",    "window_minutes": 60,   "method": "portal"},
        {"recipient": "Inspector General", "window_minutes": 120,  "method": "email"},
        {"recipient": "Public Affairs",    "window_minutes": 120,  "method": "email"},
        {"recipient": "Help Desk",         "window_minutes": 15,   "method": "ticket"},
    ],
    "P2": [
        {"recipient": "CISO",              "window_minutes": 30,   "method": "email"},
        {"recipient": "System Owner",       "window_minutes": 30,   "method": "phone"},
        {"recipient": "US-CERT / CISA",    "window_minutes": 120,  "method": "portal"},
        {"recipient": "Help Desk",         "window_minutes": 15,   "method": "ticket"},
    ],
    "P3": [
        {"recipient": "System Owner",       "window_minutes": 60,   "method": "email"},
        {"recipient": "Help Desk",         "window_minutes": 30,   "method": "ticket"},
    ],
    "P4": [
        {"recipient": "Help Desk",         "window_minutes": 240,  "method": "ticket"},
    ],
}


def get_reporting_deadline(detection_time: str, fisma_category: int) -> Optional[str]:
    """
    Calculate US-CERT reporting deadline from detection time and FISMA category.

    Returns ISO datetime string, or None if no mandatory reporting window.
    """
    category = FISMA_CATEGORIES.get(fisma_category)
    if not category or not category.get("reporting_window_hours"):
        return None

    try:
        detected = datetime.fromisoformat(detection_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        detected = datetime.now()

    deadline = detected + timedelta(hours=category["reporting_window_hours"])
    return deadline.isoformat()


def get_minutes_remaining(deadline: str) -> int:
    """Calculate minutes remaining until reporting deadline."""
    try:
        dl = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        now = datetime.now(dl.tzinfo)
        delta = dl - now
        return max(0, int(delta.total_seconds() / 60))
    except Exception:
        return 0


def build_notification_matrix(severity: str, detection_time: str, fisma_category: int) -> list[dict]:
    """Build stakeholder notification matrix with concrete deadlines."""
    notifications = []
    base_items = NOTIFICATION_MATRIX.get(severity, NOTIFICATION_MATRIX["P3"])

    try:
        detected = datetime.fromisoformat(detection_time.replace("Z", "+00:00"))
    except Exception:
        detected = datetime.now()

    category_data = FISMA_CATEGORIES.get(fisma_category, {})

    for item in base_items:
        deadline_dt = detected + timedelta(minutes=item["window_minutes"])
        notifications.append({
            "recipient": item["recipient"],
            "deadline": deadline_dt.isoformat(),
            "deadline_label": f"By {deadline_dt.strftime('%H:%M')} ({item['window_minutes']} min)",
            "method": item["method"],
            "status": "pending",
            "required": True,
        })

    # Add Privacy Act notification if PII involved
    if category_data.get("pii_risk"):
        privacy_deadline = detected + timedelta(hours=72)
        notifications.append({
            "recipient": "Privacy Officer / Senior Agency Official for Privacy",
            "deadline": privacy_deadline.isoformat(),
            "deadline_label": "Within 72 hours (Privacy Act)",
            "method": "email",
            "status": "pending",
            "required": True,
        })

    return notifications


def classify_severity_from_impact(
    citizen_impact: int,
    services_down: int,
    pii_involved: bool,
) -> str:
    """Heuristic severity classification based on blast radius."""
    if pii_involved and citizen_impact > 1000:
        return "P1"
    if citizen_impact > 10000 or services_down >= 3:
        return "P1"
    if citizen_impact > 1000 or services_down >= 2:
        return "P2"
    if citizen_impact > 100 or services_down >= 1:
        return "P3"
    return "P4"
