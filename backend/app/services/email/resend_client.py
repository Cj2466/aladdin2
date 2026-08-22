import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


def send_email(to_email: str, subject: str, body_text: str) -> bool:
    """Never raises — a missing/failed email integration disables that one
    capability without breaking the caller's own flow (an alert still
    fires in-app, a registration still succeeds and can be verified once
    a key is configured). Returns whether the email was actually sent."""
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set; skipping email.")
        return False
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.alert_email_from,
                    "to": [to_email],
                    "subject": subject,
                    "text": body_text,
                },
            )
            response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send email via Resend.")
        return False
