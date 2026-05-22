"""Invoice processing helpers.

Loads approval thresholds and the approved-vendor list from Azure App
Configuration (key ``hitl/invoice/*``).  Falls back to built-in defaults so
the app works locally without App Configuration configured.
"""

import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

# ── Fallback defaults (used when AZURE_APP_CONFIG_ENDPOINT is not set) ────────

FALLBACK_COST_LIMIT: float = 1000.0
FALLBACK_DAYS_LIMIT: int = 30
FALLBACK_APPROVED_VENDORS: list[str] = [
    "Microsoft", "Amazon", "Google", "Apple", "Adobe", "Salesforce",
    "Slack", "Zoom", "Stripe", "GitHub", "Atlassian", "Dropbox",
    "HubSpot", "Twilio", "SendGrid", "MongoDB", "Datadog", "PagerDuty",
    "ServiceNow", "DocuSign",
]


class InvoiceConfig:
    def __init__(
        self,
        cost_limit: float,
        days_limit: int,
        approved_vendors: list[str],
    ) -> None:
        self.cost_limit = cost_limit
        self.days_limit = days_limit
        # Store lowercase for case-insensitive matching
        self.approved_vendors_lower: set[str] = {v.lower() for v in approved_vendors}
        self.approved_vendors = approved_vendors  # original casing for display


def load_invoice_config() -> InvoiceConfig:
    """Return InvoiceConfig loaded from Azure App Configuration, with fallback."""
    endpoint = os.getenv("AZURE_APP_CONFIG_ENDPOINT")
    if endpoint:
        try:
            from azure.appconfiguration import AzureAppConfigurationClient  # noqa: PLC0415
            from azure.identity import DefaultAzureCredential  # noqa: PLC0415

            client = AzureAppConfigurationClient(endpoint, DefaultAzureCredential())
            cost_limit = float(
                client.get_configuration_setting(key="hitl/invoice/cost-limit").value
            )
            days_limit = int(
                client.get_configuration_setting(key="hitl/invoice/days-limit").value
            )
            vendors: list[str] = json.loads(
                client.get_configuration_setting(key="hitl/invoice/approved-vendors").value
            )
            logger.info("Loaded invoice config from App Configuration (%d vendors).", len(vendors))
            return InvoiceConfig(cost_limit, days_limit, vendors)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Could not load invoice config from App Configuration; using defaults."
            )
    return InvoiceConfig(FALLBACK_COST_LIMIT, FALLBACK_DAYS_LIMIT, FALLBACK_APPROVED_VENDORS)


def evaluate_invoice(
    vendor: str, amount: float, invoice_date: date, config: InvoiceConfig
) -> dict:
    """Assess whether an invoice qualifies for automatic approval.

    Returns a dict with:
      - ``can_auto_approve`` (bool)
      - ``vendor_ok``, ``amount_ok``, ``date_ok`` (bool each)
      - ``reasons`` (list[str]) — human-readable failure reasons
    """
    today = date.today()
    vendor_ok = vendor.strip().lower() in config.approved_vendors_lower
    amount_ok = amount < config.cost_limit
    date_ok = (today - invoice_date).days <= config.days_limit

    reasons: list[str] = []
    if not vendor_ok:
        reasons.append(f"'{vendor}' is not in the approved vendor list")
    if not amount_ok:
        reasons.append(f"${amount:,.2f} exceeds the ${config.cost_limit:,.0f} auto-approval limit")
    if not date_ok:
        reasons.append(f"invoice date is more than {config.days_limit} days old")

    return {
        "can_auto_approve": vendor_ok and amount_ok and date_ok,
        "vendor_ok": vendor_ok,
        "amount_ok": amount_ok,
        "date_ok": date_ok,
        "reasons": reasons,
    }
