import logging
import os

from azure.communication.email import EmailClient
from azure.identity import DefaultAzureCredential

from mode_config import is_local

logger = logging.getLogger(__name__)


def _is_local_mode() -> bool:
    """Return local-mode status without requiring app lifespan initialization.

    In unit tests and one-off scripts, mode_config.resolve_mode() may not have
    executed yet. In that case, default to non-local behavior.
    """
    try:
        return is_local()
    except RuntimeError:
        return False


def resolve_email_recipient() -> tuple[str, str]:
    recipient = os.getenv("EMAIL_RECIPIENT")
    if recipient:
        return recipient, "EMAIL_RECIPIENT"

    recipient = os.getenv("GMAIL_SMTP_USER")
    if recipient:
        return recipient, "GMAIL_SMTP_USER fallback"

    recipient = os.getenv("SMTP_USER")
    if recipient:
        return recipient, "SMTP_USER fallback"

    raise ValueError("Missing recipient config. Set EMAIL_RECIPIENT.")


def get_email_client() -> EmailClient:
    endpoint = os.getenv("ACS_ENDPOINT")
    if endpoint:
        # Prefer managed identity for Azure-hosted workloads.
        return EmailClient(endpoint=endpoint, credential=DefaultAzureCredential())

    connection_string = os.getenv("ACS_CONNECTION_STRING")
    if connection_string:
        return EmailClient.from_connection_string(connection_string)

    raise ValueError("Missing ACS config. Set ACS_ENDPOINT or ACS_CONNECTION_STRING.")


def send_email_via_acs(subject: str, body: str, recipient: str | None = None) -> str:
    if _is_local_mode():
        try:
            recipient_address = recipient or resolve_email_recipient()[0]
        except ValueError:
            recipient_address = "local-dev@localhost"
        logger.info(
            "[LOCAL EMAIL STUB] To: %s | Subject: %s\n%s",
            recipient_address,
            subject,
            body,
        )
        return recipient_address

    recipient_address = recipient or resolve_email_recipient()[0]
    sender_address = os.getenv("ACS_EMAIL_SENDER_ADDRESS")
    if not sender_address:
        raise ValueError("Missing ACS sender config. Set ACS_EMAIL_SENDER_ADDRESS.")

    message = {
        "senderAddress": sender_address,
        "content": {
            "subject": subject,
            "plainText": body,
        },
        "recipients": {
            "to": [{"address": recipient_address}],
        },
    }

    client = get_email_client()
    poller = client.begin_send(message)
    result = poller.result()
    logger.info("Email send status: %s", getattr(result, "status", "unknown"))
    return recipient_address