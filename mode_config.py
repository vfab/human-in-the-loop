"""Runtime mode resolution: local stub vs. Azure.

MOCK_MODE=true     → local mode: all LLM calls return offline stub responses,
                     email delivery is logged instead of sent.  No API keys or
                     network access required.
MOCK_MODE=false    → Azure mode: requires Azure OpenAI + ACS; fails hard if
                     services are unavailable.
MOCK_MODE=dynamic  → probe Azure OpenAI at startup; use Azure mode if reachable,
                     otherwise fall back to local stub mode.
                     This is the default when MOCK_MODE is unset.

Other values are treated as "dynamic" with a warning.

Usage
-----
Call ``await resolve_mode()`` once during app startup (e.g. via FastAPI
lifespan).  After that, call ``is_local()`` anywhere in the codebase to
branch on the resolved mode.
"""

import asyncio
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Cached result: "local" | "azure" | None (unresolved)
_resolved: str | None = None


async def resolve_mode() -> str:
    """Resolve and cache the runtime mode.  Safe to call multiple times."""
    global _resolved  # noqa: PLW0603

    if _resolved is not None:
        return _resolved

    raw = os.getenv("MOCK_MODE", "dynamic").strip().lower()

    if raw == "true":
        logger.info("MOCK_MODE=true — local stub mode (offline, no API keys required).")
        _resolved = "local"

    elif raw == "false":
        logger.info("MOCK_MODE=false — Azure mode.")
        _resolved = "azure"

    else:
        if raw != "dynamic":
            logger.warning("MOCK_MODE=%r is not recognised; treating as 'dynamic'.", raw)
        _resolved = await _probe_azure()
        if _resolved == "local":
            logger.info("MOCK_MODE=dynamic — falling back to local stub mode.")

    return _resolved


def is_local() -> bool:
    """Return True when the resolved mode is 'local'.

    Raises RuntimeError if called before ``resolve_mode()`` has completed.
    """
    if _resolved is None:
        raise RuntimeError(
            "mode_config.resolve_mode() has not been called yet. "
            "Ensure it runs during application startup."
        )
    return _resolved == "local"


# ── Azure probe ────────────────────────────────────────────────────────────────

async def _probe_azure() -> str:
    """Return 'azure' if the configured Azure OpenAI endpoint is reachable, 'local' otherwise."""
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        logger.info(
            "MOCK_MODE=dynamic — AZURE_OPENAI_ENDPOINT is not set; switching to local mode."
        )
        return "local"

    # A lightweight, non-destructive probe: list deployments (GET, read-only).
    probe_url = endpoint.rstrip("/") + "/openai/deployments?api-version=2024-02-01"

    headers: dict[str, str] = {}
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key:
        headers["api-key"] = api_key
    else:
        try:
            from azure.identity import DefaultAzureCredential  # noqa: PLC0415

            cred = DefaultAzureCredential()
            loop = asyncio.get_running_loop()
            token = await loop.run_in_executor(
                None,
                lambda: cred.get_token("https://cognitiveservices.azure.com/.default"),
            )
            headers["Authorization"] = f"Bearer {token.token}"
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "MOCK_MODE=dynamic — Azure credential unavailable (%s); switching to local mode.",
                exc,
            )
            return "local"

    def _do_request() -> int:
        req = urllib.request.Request(probe_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status  # type: ignore[return-value]
        except urllib.error.HTTPError as exc:
            return exc.code  # 401/403 still means the endpoint is reachable

    try:
        loop = asyncio.get_running_loop()
        status: int = await loop.run_in_executor(None, _do_request)
        if status < 500:
            logger.info(
                "MOCK_MODE=dynamic — Azure OpenAI reachable (HTTP %d); using Azure mode.", status
            )
            return "azure"
        logger.warning(
            "MOCK_MODE=dynamic — Azure OpenAI returned HTTP %d; switching to local mode.", status
        )
        return "local"
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "MOCK_MODE=dynamic — Azure probe failed (%s); switching to local mode.", exc
        )
        return "local"
