from typing import Optional

from twilio.rest import Client

from app.core.settings import settings

# Initialize Twilio Client once per process
_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def send_whatsapp_text(to_e164: str, body: str, media_url: Optional[str] = None):
    """
    Send a WhatsApp message via Twilio.

    Args:
        to_e164: Receiver phone in E.164 format (e.g., +14155552671). The function will add the 'whatsapp:' prefix.
        body: Text body to send.
        media_url: Optional public URL to media to attach.
    """
    # Ensure 'whatsapp:' prefix for the recipient
    to = to_e164
    if to.startswith("whatsapp:"):
        to = to.split(":", 1)[1]
    to = f"whatsapp:{to}"

    # From number should already include 'whatsapp:' in env (per .env.example)
    from_ = settings.TWILIO_WHATSAPP_NUMBER

    kwargs = {"from_": from_, "to": to, "body": body}
    if media_url:
        kwargs["media_url"] = [media_url]

    return _client.messages.create(**kwargs)

