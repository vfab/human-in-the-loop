"""Support ticket escalation helpers.

Loads auto-resolve categories and escalation keywords from Azure App
Configuration (keys ``hitl/support/*``).  Falls back to built-in defaults.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# ── Category registry ─────────────────────────────────────────────────────────

# All supported ticket categories: key → human-readable label
TICKET_CATEGORIES: dict[str, str] = {
    "password_reset":     "Password / login help",
    "how_to":             "How-to / usage question",
    "order_status":       "Order or shipment status",
    "account_info":       "Account details update",
    "billing_dispute":    "Disputed or incorrect charge",
    "refund_request":     "Refund or return request",
    "technical_bug":      "Software bug or data error",
    "account_suspension": "Account locked or suspended",
    "cancellation":       "Cancel subscription or service",
    "security_concern":   "Potential breach or fraud",
    "complaint":          "Formal complaint",
}

# ── Fallback defaults ─────────────────────────────────────────────────────────

FALLBACK_AUTO_RESOLVE_CATEGORIES: list[str] = [
    "password_reset",
    "how_to",
    "order_status",
    "account_info",
]

FALLBACK_ESCALATION_KEYWORDS: list[str] = [
    "cancel", "refund", "lawsuit", "lawyer", "attorney",
    "breach", "hacked", "fraud", "scam",
    "supervisor", "manager", "escalate",
    "data loss", "outage", "critical", "legal",
]


# ── Config loader ─────────────────────────────────────────────────────────────

def load_support_config() -> dict:
    """Return support routing config from Azure App Configuration, with fallback.

    Keys read:
      - ``hitl/support/auto-resolve-categories``  (JSON array of category keys)
      - ``hitl/support/escalation-keywords``       (JSON array of strings)
    """
    endpoint = os.getenv("AZURE_APP_CONFIG_ENDPOINT")
    if endpoint:
        try:
            from azure.appconfiguration import AzureAppConfigurationClient  # noqa: PLC0415
            from azure.identity import DefaultAzureCredential  # noqa: PLC0415

            client = AzureAppConfigurationClient(endpoint, DefaultAzureCredential())
            auto_cats: list[str] = json.loads(
                client.get_configuration_setting(key="hitl/support/auto-resolve-categories").value
            )
            esc_keywords: list[str] = json.loads(
                client.get_configuration_setting(key="hitl/support/escalation-keywords").value
            )
            logger.info(
                "Loaded support config from App Configuration (%d categories, %d keywords).",
                len(auto_cats),
                len(esc_keywords),
            )
            return {
                "auto_resolve_categories": set(auto_cats),
                "escalation_keywords": esc_keywords,
            }
        except Exception:  # noqa: BLE001
            logger.warning(
                "Could not load support config from App Configuration; using defaults."
            )
    return {
        "auto_resolve_categories": set(FALLBACK_AUTO_RESOLVE_CATEGORIES),
        "escalation_keywords": FALLBACK_ESCALATION_KEYWORDS,
    }


def detect_escalation_keywords(text: str, config: dict) -> list[str]:
    """Return any escalation keywords found in *text* (case-insensitive)."""
    lower = text.lower()
    return [kw for kw in config["escalation_keywords"] if kw in lower]


def parse_agent_classification(raw: str) -> tuple[str, int, str]:
    """Extract (category, complexity, resolution) from the agent's structured output.

    Expected format::

        CATEGORY: <key>
        COMPLEXITY: <1-5>
        RESOLUTION:
        <free-form text>

    Returns defaults on parse failure.
    """
    category = "complaint"
    complexity = 3
    resolution_lines: list[str] = []
    in_resolution = False

    for line in raw.strip().splitlines():
        if line.startswith("CATEGORY:"):
            cat_raw = line.split(":", 1)[1].strip().lower()
            if cat_raw in TICKET_CATEGORIES:
                category = cat_raw
        elif line.startswith("COMPLEXITY:"):
            try:
                complexity = max(1, min(5, int(line.split(":", 1)[1].strip())))
            except ValueError:
                pass
        elif line.startswith("RESOLUTION:"):
            in_resolution = True
        elif in_resolution:
            resolution_lines.append(line)

    resolution = "\n".join(resolution_lines).strip() or raw.strip()
    return category, complexity, resolution
