import logging
import os

from azure.communication.email import EmailClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)


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