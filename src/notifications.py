"""SMS alerts via sipgate.

Credentials come from settings; alerts are skipped silently when disabled or
unconfigured, and are never sent from dry-run mode.
"""

import logging
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .settings import Settings

log = logging.getLogger(__name__)

SIPGATE_SMS_URL = "https://api.sipgate.com/v2/sessions/sms"


def send_sms_alert(settings: "Settings", message: str) -> bool:
    cfg = settings.get("sms", {})
    if not cfg.get("enabled") or not cfg.get("auth_token") or not cfg.get("recipient"):
        log.debug("SMS alert skipped (disabled or unconfigured): %s", message)
        return False
    if settings.get("dry_run", True):
        log.info("[DRY RUN] SMS alert suppressed: %s", message)
        return False

    try:
        response = requests.post(
            SIPGATE_SMS_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": cfg["auth_token"],
            },
            json={
                "smsId": cfg.get("sms_id", "s0"),
                "recipient": cfg["recipient"],
                "message": message,
            },
            timeout=15,
        )
        response.raise_for_status()
        log.info("SMS alert sent")
        return True
    except requests.RequestException as exc:
        log.error("Failed to send SMS alert: %s", exc)
        return False
