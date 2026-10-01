"""
Entry point. Run with:
    uvicorn main:app --reload

Twilio will POST here whenever a student replies on WhatsApp.
"""
import logging
import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from bot_logic import check_and_send_reminders, handle_incoming_message
from db import get_session, init_db
from scheduler import start_scheduler
from admin import ADMIN_PASSWORD, error_page, require_login, router as admin_router
from portal import router as portal_router

load_dotenv()

app = FastAPI(title="DriveBot")
app.include_router(admin_router)
app.include_router(portal_router)

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# Set this to your real deployed URL once you're live, e.g.
# "https://yourapp.up.railway.app" -- required for signature checking.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

log = logging.getLogger("drivebot")

def _is_ui(request: Request) -> bool:
    path = request.url.path
    return path.startswith("/admin") or path.startswith("/i/")


def _back_for(request: Request) -> str:
    parts = request.url.path.split("/")
    if request.url.path.startswith("/i/") and len(parts) > 2 and parts[2]:
        return f"/i/{parts[2]}/"
    if request.url.path.startswith("/admin/instructor/") and len(parts) > 3 and parts[3].isdigit():
        return f"/admin/instructor/{parts[3]}"
    return "/admin/"


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    # 401 must stay as-is so the browser shows its login box.
    if _is_ui(request) and exc.status_code != 401:
        return HTMLResponse(error_page(exc.status_code, str(exc.detail), _back_for(request),
                                       it=request.url.path.startswith("/i/")), status_code=exc.status_code)
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    if _is_ui(request):
        msg = "Some fields are missing or invalid. Go back and check the form."
        if request.url.path.startswith("/i/"):
            msg = "Alcuni campi mancano o non sono validi. Torna indietro e controlla."
        return HTMLResponse(error_page(422, msg, _back_for(request), it=request.url.path.startswith("/i/")), status_code=422)
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def _unhandled_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    if _is_ui(request):
        return HTMLResponse(error_page(500, "", _back_for(request), it=request.url.path.startswith("/i/")), status_code=500)
    return Response("Internal Server Error", status_code=500)


_validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None


def _is_valid_twilio_request(request: Request, form: dict) -> bool:
    """
    Returns True (allow the request) when we can't validate yet -- no
    auth token or no known public URL configured -- which is exactly
    the local-dev situation. Once both are set (i.e. you're deployed
    for real), this actually checks the X-Twilio-Signature header and
    rejects anything that didn't really come from Twilio.
    """
    if _validator is None or not PUBLIC_BASE_URL:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    url = PUBLIC_BASE_URL.rstrip("/") + "/webhook"
    return _validator.validate(url, form, signature)


@app.on_event("startup")
def on_startup():
    # Refuse to run "for real" (public URL set) with the default admin password.
    if PUBLIC_BASE_URL and ADMIN_PASSWORD == "admin":
        raise RuntimeError("Set a strong ADMIN_PASSWORD in the environment before deploying.")
    init_db()
    start_scheduler()


@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    """
    Twilio sends incoming WhatsApp messages as form-encoded POST data.
    We read the whole form (not just From/Body) because signature
    validation needs every field Twilio actually sent.
    """
    form = dict(await request.form())

    if not _is_valid_twilio_request(request, form):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    from_number = form.get("From", "")
    body = form.get("Body", "")

    try:
        with get_session() as session:
            reply_text = handle_incoming_message(session, from_number, body)
    except Exception:
        # Twilio must always get a valid answer, whatever goes wrong inside.
        log.exception("Error handling incoming message from %s", from_number)
        reply_text = "Si e' verificato un errore, riprova tra poco. / Something went wrong, please try again shortly."

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(content=str(twiml), media_type="application/xml")


@app.post("/run-reminders-now")
def run_reminders_now(user: str = Depends(require_login)):
    """Manual trigger for testing -- normally the scheduler does this."""
    with get_session() as session:
        check_and_send_reminders(session)
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "running"}
