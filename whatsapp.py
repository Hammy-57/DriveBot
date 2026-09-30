"""
Thin wrapper around Twilio's WhatsApp API.

- send_whatsapp_message(): free-form text. Only allowed inside WhatsApp's
  24h window after the person last wrote to the bot (i.e. replies).
- send_whatsapp_template(): approved template. REQUIRED for anything the
  bot sends first (reminders, waitlist offers, instructor notices).

Both functions NEVER raise. They return True if the message was sent (or
printed in DEV MODE) and False if sending failed, so one bad send can
never crash a webhook reply or the reminder loop. Callers decide what a
False means (e.g. reminders are not marked "sent" and are retried).

DEV MODE: with no Twilio credentials, messages are printed to the console.
"""
import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("drivebot")

def _env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip().strip('"').strip("'") if value else None


TWILIO_ACCOUNT_SID = _env("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _env("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = _env("TWILIO_WHATSAPP_NUMBER")  # "whatsapp:+14155238886"
if TWILIO_WHATSAPP_NUMBER and not TWILIO_WHATSAPP_NUMBER.startswith("whatsapp:"):
    TWILIO_WHATSAPP_NUMBER = "whatsapp:" + TWILIO_WHATSAPP_NUMBER

# SANDBOX_FREEFORM=true -> send reminders/offers as plain text instead of
# templates. ONLY for demos with the Twilio Sandbox (works while the student
# has messaged the sandbox in the last 24h). Never use it in production.
FREEFORM_MODE = os.getenv("SANDBOX_FREEFORM", "").strip().lower() in ("1", "true", "yes")

# Reason the most recent send failed (shown in the admin panel), or None.
last_error: str | None = None

# Deployed (public URL set) but no Twilio credentials: NOT dev mode. Sending
# must fail loudly, otherwise reminders get marked "sent" without being sent.
DEPLOYED = bool(os.getenv("PUBLIC_BASE_URL", "").strip())

_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    from twilio.rest import Client
    _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _clean(value) -> str:
    """WhatsApp template variables can't be empty or contain newlines/tabs."""
    text = " ".join(str(value).split())
    return text or "-"


def status_info() -> dict:
    return {
        "credentials": _client is not None,
        "from_number": TWILIO_WHATSAPP_NUMBER,
        "freeform": FREEFORM_MODE,
        "deployed": DEPLOYED,
    }


def _no_client() -> bool:
    """Handle the no-credentials case. Returns True only in local DEV MODE."""
    global last_error
    if DEPLOYED:
        last_error = "Twilio is not configured: TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are missing on the server."
        log.error(last_error)
        return False
    return True


def send_whatsapp_message(to_phone: str, body: str) -> bool:
    global last_error
    if _client is None:
        if not _no_client():
            return False
        print(f"[DEV MODE - no message sent] To {to_phone}: {body}")
        return True
    try:
        _client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{to_phone}",
            body=body,
        )
        last_error = None
        return True
    except Exception as exc:  # Twilio errors, network errors, anything
        last_error = str(exc)
        log.error("Free-form WhatsApp send to %s failed: %s", to_phone, exc)
        return False


def send_whatsapp_template(to_phone: str, content_sid: str | None, variables: dict,
                           fallback_text: str | None = None) -> bool:
    global last_error
    variables = {k: _clean(v) for k, v in variables.items()}
    if _client is None:
        if not _no_client():
            return False
        print(f"[DEV MODE - template not sent, no Twilio client] To {to_phone}: {variables}")
        return True
    if FREEFORM_MODE and fallback_text:
        return send_whatsapp_message(to_phone, fallback_text)
    if not content_sid:
        last_error = "No approved template ID (HX...) is configured for this message, and SANDBOX_FREEFORM is off."
        log.error("Template send to %s skipped: %s", to_phone, last_error)
        return False
    try:
        _client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{to_phone}",
            content_sid=content_sid,
            content_variables=json.dumps(variables),
        )
        last_error = None
        return True
    except Exception as exc:
        last_error = str(exc)
        log.error("Template send to %s failed: %s", to_phone, exc)
        return False
