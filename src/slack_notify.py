"""
Optional Slack webhook notifications for Statuspage incidents.

When SLACK_WEBHOOK_URL is set, posts to Slack when:
- A new incident appears (was not in the previous cached check)
- An incident disappears from the active list (marked resolved on the status page)

Notifications are skipped when there is no prior cache for a service (avoids
spamming every active incident on first deploy).
"""

import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_ENV = "SLACK_WEBHOOK_URL"


def slack_webhook_enabled() -> bool:
    url = os.getenv(SLACK_WEBHOOK_ENV, "").strip()
    return bool(url)


def _get_webhook_url() -> str:
    return os.getenv(SLACK_WEBHOOK_ENV, "").strip()


def _format_affected(incident: dict) -> str:
    parts = incident.get("affected_components") or []
    if isinstance(parts, list):
        return ", ".join(parts) if parts else "—"
    return str(parts) if parts else "—"


def _post_webhook_async(payload: dict) -> None:
    url = _get_webhook_url()
    if not url:
        return

    def _send():
        try:
            r = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if r.status_code != 200:
                logger.warning(
                    "Slack webhook returned %s: %s",
                    r.status_code,
                    (r.text or "")[:500],
                )
        except Exception as e:
            logger.warning("Slack webhook request failed: %s", e, exc_info=True)

    threading.Thread(target=_send, daemon=True).start()


def notify_incident_opened(service_name: str, incident: dict) -> None:
    """Post Slack message when an incident first appears for a monitored app."""
    if not slack_webhook_enabled():
        return
    name = incident.get("name", "Unknown")[:200]
    inc_id = incident.get("id", "unknown")
    impact = incident.get("impact", "unknown")
    shortlink = incident.get("shortlink", "")
    affected = _format_affected(incident)
    started = incident.get("started_at", "—")
    text = (
        f"*Incident opened* — *{service_name}*\n"
        f"*{name}*\n"
        f"• Impact: `{impact}`\n"
        f"• ID: `{inc_id}`\n"
        f"• Started: {started}\n"
        f"• Affected: {affected[:500]}"
    )
    if shortlink and shortlink != "N/A":
        text += f"\n• <{shortlink}|Status page>"
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            }
        ]
    }
    _post_webhook_async(payload)
    logger.info(
        "Slack: queued incident opened notification for %s (%s)",
        service_name,
        inc_id,
    )


def notify_incident_resolved(service_name: str, incident: dict) -> None:
    """Post Slack message when an incident is no longer active (resolved)."""
    if not slack_webhook_enabled():
        return
    name = incident.get("name", "Unknown")[:200]
    inc_id = incident.get("id", "unknown")
    shortlink = incident.get("shortlink", "")
    text = (
        f"*Incident resolved* — *{service_name}*\n"
        f"*{name}*\n"
        f"• ID: `{inc_id}`"
    )
    if shortlink and shortlink != "N/A":
        text += f"\n• <{shortlink}|Status page>"
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            }
        ]
    }
    _post_webhook_async(payload)
    logger.info(
        "Slack: queued incident resolved notification for %s (%s)",
        service_name,
        inc_id,
    )
