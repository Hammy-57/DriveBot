"""Phone-number cleanup shared by the admin panel, the instructor page and the WhatsApp bot."""
import re


def normalize_phone(raw: str) -> str:
    """
    '333 123 4567' -> '+393331234567'; '0039 333...' -> '+39333...'.
    Must match how WhatsApp/Twilio report the sender. Raises ValueError if invalid.
    """
    p = re.sub(r"[\s\-\.\(\)]", "", raw or "")
    if p.startswith("whatsapp:"):
        p = p[len("whatsapp:"):]
    if p.startswith("00"):
        p = "+" + p[2:]
    if not p.startswith("+") and re.fullmatch(r"3\d{8,9}", p):
        p = "+39" + p  # Italian mobile without country code
    if not re.fullmatch(r"\+\d{8,15}", p):
        raise ValueError(f"Invalid phone number: {raw!r}")
    return p
