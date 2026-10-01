"""
Web admin panel: add instructors, students, lessons and waitlist entries
without touching the database. Server-rendered HTML, HTTP Basic Auth
(ADMIN_USERNAME / ADMIN_PASSWORD from .env). Everything user-typed is
HTML-escaped. Cancelling here uses the same function as a student
cancelling by WhatsApp, so the waitlist flow is identical.
"""
import html
import os
import re
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import select

import whatsapp as wa
from bot_logic import TEMPLATE_SIDS, offer_next_waitlist, send_reminder_now
from phones import normalize_phone as _normalize
from scheduler import schedule_reminder
from db import get_session
from models import Instructor, Lesson, Student, WaitlistEntry

load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
LOCAL_TZ = ZoneInfo("Europe/Rome")

router = APIRouter(prefix="/admin")
security = HTTPBasic()
esc = html.escape


def require_login(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_user = secrets.compare_digest(credentials.username.encode(), ADMIN_USERNAME.encode())
    correct_pass = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


PAGE_STYLE = """
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background:#17181c; color:#e8e9ec;
         max-width: 860px; margin: 0 auto; padding: 24px 16px 60px; line-height: 1.45; }
  h1 { font-size: 1.3rem; margin: 0 0 4px; }
  h2 { font-size: 1.05rem; margin: 32px 0 10px; border-bottom: 1px solid #35363c; padding-bottom: 6px; }
  a { color: #f5c451; text-decoration: none; }
  a:hover { text-decoration: underline; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0 18px; font-size: 0.92rem; }
  th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #2a2b30; }
  th { color: #9a9ca3; font-weight: 500; font-size: 0.8rem; }
  form.inline { display: inline; }
  .card { background: #1e1f24; border: 1px solid #2a2b30; border-radius: 6px; padding: 16px 18px; margin: 14px 0; }
  input, select { background:#111216; border:1px solid #3a3b41; color:#e8e9ec; padding:7px 9px; border-radius:5px; font-size:0.92rem; }
  label { display:block; font-size:0.82rem; color:#9a9ca3; margin: 10px 0 3px; }
  button { background:#f5c451; color:#17181c; border:none; padding:8px 16px; border-radius:5px;
           font-weight:600; cursor:pointer; margin-top:12px; font-size:0.9rem; }
  button.danger { background:#e05555; color:#fff; }
  button.small { padding:4px 10px; font-size:0.8rem; margin-top:0; }
  .status { font-size:0.78rem; padding:2px 8px; border-radius:10px; background:#2a2b30; }
  .top-link { font-size: 0.85rem; }

.stats{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.stat{background:#1e1f25;border:1px solid #2c2d34;border-radius:10px;padding:10px 16px;min-width:110px}
.stat b{display:block;font-size:24px;color:#f5c542}
.stat span{font-size:12px;color:#9a9ca3}
details{margin:8px 0}summary{cursor:pointer;color:#9a9ca3;padding:6px 0}
</style>
"""


def _local(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")


def normalize_phone(raw: str) -> str:
    try:
        return _normalize(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phone number: {raw!r}. Use the format +393331234567.")


def _base_url(request: Request) -> str:
    env = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return env or str(request.base_url).rstrip("/")


def _yes(flag: bool) -> str:
    return "<span style='color:#5fd38d'>yes</span>" if flag else "<span style='color:#ff6b6b'>NO</span>"


def _status_box() -> str:
    info = wa.status_info()
    templates = "".join(
        f"<li>{esc(kind)}: {_yes(bool(sid))}</li>" for kind, sid in TEMPLATE_SIDS.items()
    )
    return f"""
    <div class="card">
      <strong>System check</strong>
      <ul style="line-height:1.7">
        <li>Twilio credentials loaded: {_yes(info['credentials'])}</li>
        <li>WhatsApp sender: <code>{esc(info['from_number'] or 'NOT SET')}</code></li>
        <li>Sandbox demo mode (SANDBOX_FREEFORM): {_yes(info['freeform'])} (on = demo only, off = production)</li>
        <li>Approved template IDs set:<ul>{templates}</ul></li>
      </ul>
      <form method="post" action="/admin/test-message">
        <label>Send a test WhatsApp message to (with country code)</label>
        <input name="phone" placeholder="+39..." required>
        <button type="submit">Send test</button>
      </form>
    </div>"""


def _last_error_banner() -> str:
    if not wa.last_error:
        return ""
    return (f'<div class="card" style="border-color:#ff6b6b"><strong style="color:#ff6b6b">Last WhatsApp sending problem</strong>'
            f'<p><code>{esc(wa.last_error)}</code></p></div>')


def stat_cards(items) -> str:
    return '<div class="stats">' + "".join(f'<div class="stat"><b>{v}</b><span>{esc(lbl)}</span></div>' for v, lbl in items) + "</div>"


def split_lessons(lessons):
    """(upcoming sorted soonest-first, everything else newest-first)."""
    now = datetime.now(timezone.utc)
    def aware(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    live = ("scheduled", "confirmed", "reschedule_requested")
    upcoming = sorted([l for l in lessons if l.status in live and aware(l.start_time) > now], key=lambda l: l.start_time)
    past = sorted([l for l in lessons if l not in upcoming], key=lambda l: l.start_time, reverse=True)
    return upcoming, past


def _button(action: str, label: str, danger: bool = True) -> str:
    cls = "small danger" if danger else "small"
    return (f'<form class="inline" method="post" action="{action}">'
            f'<button class="{cls}">{label}</button></form>')


def _page(title: str, body: str) -> str:
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)}</title>{PAGE_STYLE}</head><body>{body}</body></html>')


def error_page(status: int, message: str, back: str = "/admin/", it: bool = False) -> str:
    if it:
        title, back_label = "Qualcosa non ha funzionato", "← Indietro"
        if status >= 500:
            message = "Errore del server. Riprova tra poco; se continua, avvisa chi ti ha attivato il servizio."
    else:
        title, back_label = "Something went wrong", "← Back"
        if status >= 500:
            message = "Server error. The details were logged. Try again, and if it keeps happening check the Railway Deploy Logs."
    return _page(title, f"""
    <p class="top-link"><a href="{esc(back)}">{back_label}</a></p>
    <h1 style="color:#ff6b6b">❌ {esc(title)}</h1>
    <div class="card"><p>{esc(message)}</p><p style="color:#9a9ca3;font-size:13px">Error {status}</p></div>""")


def _result_page(ok: bool, title: str, detail: str, back: str, back_label: str = "← Back") -> HTMLResponse:
    color = "#5fd38d" if ok else "#ff6b6b"
    return HTMLResponse(_page(title, f"""
    <p class="top-link"><a href="{esc(back)}">{back_label}</a></p>
    <h1 style="color:{color}">{'✅' if ok else '❌'} {esc(title)}</h1>
    <div class="card"><p>{detail}</p></div>"""))


def apply_reminder_choice(lesson_id: int, choice: str, back: str, it: bool = False):
    """
    After creating a lesson: 'now' sends the reminder immediately, '2min' schedules it
    2 minutes from now, anything else = automatic (24h and 2h before) -> returns None.
    """
    lbl = "← Indietro" if it else "← Back"
    if choice == "2min":
        run_at = schedule_reminder(lesson_id, 120).astimezone(LOCAL_TZ).strftime("%H:%M")
        if it:
            return _result_page(True, "Promemoria programmato", f"Lezione aggiunta. Il promemoria partira' alle {run_at} (tra circa 2 minuti).", back, lbl)
        return _result_page(True, "Reminder scheduled", f"Lesson added. The reminder will be sent at {run_at} Rome time (in about 2 minutes). "
                            "If it doesn't arrive, check <em>System check</em> on the admin home page and Railway's Deploy Logs. "
                            "Note: if the server restarts before then, it is skipped.", back, lbl)
    if choice == "now":
        with get_session() as s:
            lesson = s.get(Lesson, lesson_id)
            ok, err = send_reminder_now(s, lesson)
        if ok:
            return _result_page(True, "Promemoria inviato" if it else "Reminder sent",
                                "Lezione aggiunta e promemoria inviato." if it else "Lesson added and the reminder was sent. The student can reply SI or NO.", back, lbl)
        return _result_page(False, "Invio non riuscito" if it else "Lesson added, but the reminder failed",
                            ("La lezione e' stata aggiunta, ma il promemoria non e' partito: " if it else "The lesson was saved, but sending failed: ") + f"<code>{esc(err or '')}</code>", back, lbl)
    return None


@router.get("/", response_class=HTMLResponse)
def dashboard(user: str = Depends(require_login)):
    with get_session() as s:
        instructors = s.exec(select(Instructor)).all()

    rows = "".join(
        f"<tr><td>{esc(i.name)}</td><td>{esc(i.phone)}</td>"
        f"<td><a href='/admin/instructor/{i.id}'>Open →</a></td></tr>"
        for i in instructors
    ) or "<tr><td colspan='3'>No instructors yet. Add one below.</td></tr>"

    return _page("DriveBot Admin", f"""
    <h1>🚗 DriveBot Admin</h1>
    <h2>Instructors</h2>
    <table><tr><th>Name</th><th>Phone</th><th></th></tr>{rows}</table>
    <div class="card">
      <strong>Add instructor</strong>
      <form method="post" action="/admin/instructors">
        <label>Name</label><input name="name" required>
        <label>WhatsApp phone (with country code)</label><input name="phone" placeholder="+39..." required>
        <button type="submit">Add instructor</button>
      </form>
    </div>
    {_last_error_banner()}
    <h2>Setup</h2>{_status_box()}""")


@router.post("/instructors")
def create_instructor(name: str = Form(...), phone: str = Form(...), user: str = Depends(require_login)):
    phone = normalize_phone(phone)
    with get_session() as s:
        instructor = Instructor(name=name.strip(), phone=phone, access_token=secrets.token_urlsafe(16))
        s.add(instructor)
        s.commit()
        s.refresh(instructor)
        new_id = instructor.id
    return RedirectResponse(url=f"/admin/instructor/{new_id}", status_code=303)


@router.get("/instructor/{instructor_id}", response_class=HTMLResponse)
def instructor_page(instructor_id: int, request: Request, user: str = Depends(require_login)):
    with get_session() as s:
        instructor = s.get(Instructor, instructor_id)
        if instructor is None:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if not instructor.access_token:
            instructor.access_token = secrets.token_urlsafe(16)
            s.add(instructor)
            s.commit()
            s.refresh(instructor)
        portal_link = f"{_base_url(request)}/i/{instructor.access_token}/"

        students = s.exec(select(Student).where(Student.instructor_id == instructor_id)).all()
        lessons = s.exec(
            select(Lesson).where(Lesson.instructor_id == instructor_id).order_by(Lesson.start_time.desc())
        ).all()
        waitlist = s.exec(select(WaitlistEntry).where(WaitlistEntry.instructor_id == instructor_id)).all()

    name_of = {st.id: st.name for st in students}

    student_rows = "".join(
        f"<tr><td>{esc(st.name)}</td><td>{esc(st.phone)}</td><td>{esc(st.language)}</td>"
        f"<td><span class='status'>{'active' if st.active else 'inactive'}</span></td>"
        f"<td>{_button(f'/admin/student/{st.id}/deactivate', 'Deactivate') if st.active else '-'}</td></tr>"
        for st in students
    ) or "<tr><td colspan='5'>No students yet.</td></tr>"

    def lesson_row(l):
        return (f"<tr><td>{esc(name_of.get(l.student_id, '?'))}</td>"
                f"<td>{_local(l.start_time)}</td><td>{esc(l.location or '-')}</td>"
                f"<td><span class='status'>{esc(l.status)}</span></td>"
                f"<td>{_button(f'/admin/lesson/{l.id}/resend', 'Send now', danger=False) + _button(f'/admin/lesson/{l.id}/remind-later', 'Send in 2 min', danger=False) if l.status in ('scheduled', 'confirmed') else ''} "
                f"{_button(f'/admin/lesson/{l.id}/cancel', 'Cancel') if l.status in ('scheduled', 'confirmed', 'reschedule_requested') else '-'}</td></tr>")

    upcoming, past = split_lessons(lessons)
    head = "<tr><th>Student</th><th>When (Rome time)</th><th>Location</th><th>Status</th><th></th></tr>"
    upcoming_html = f"<table>{head}{''.join(lesson_row(l) for l in upcoming) or '<tr><td colspan=5>No upcoming lessons.</td></tr>'}</table>"
    past_html = (f"<details><summary>Past and cancelled lessons ({len(past)})</summary><table>{head}"
                 f"{''.join(lesson_row(l) for l in past)}</table></details>") if past else ""
    cards = stat_cards([
        (len(upcoming), "upcoming lessons"),
        (sum(1 for l in upcoming if l.status == "confirmed"), "confirmed"),
        (sum(1 for l in upcoming if l.status == "scheduled"), "waiting for reply"),
        (sum(1 for l in upcoming if l.status == "reschedule_requested"), "want to reschedule"),
        (sum(1 for st in students if st.active), "active students"),
    ])

    waitlist_rows = "".join(
        f"<tr><td>{esc(name_of.get(w.student_id, '?'))}</td>"
        f"<td>{'waiting' if not w.offered else 'offered a slot'}</td>"
        f"<td>{_button(f'/admin/waitlist/{w.id}/remove', 'Remove')}</td></tr>"
        for w in waitlist
    ) or "<tr><td colspan='3'>Waitlist empty.</td></tr>"

    active_students = [st for st in students if st.active]
    student_options = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in active_students)
    no_students = "<option disabled>Add a student first</option>"

    return _page(f"{instructor.name} — DriveBot Admin", f"""
    <p class="top-link"><a href="/admin">← All instructors</a></p>
    <h1>{esc(instructor.name)}</h1>
    <p style="color:#9a9ca3">{esc(instructor.phone)}</p>
    <div class="card">
      <strong>Private page for this instructor</strong>
      <p>Send him this link on WhatsApp. Anyone with the link can manage <em>only this instructor's</em> students and lessons.</p>
      <input readonly value="{esc(portal_link)}" onclick="this.select()" style="width:100%">
      {_button(f'/admin/instructor/{instructor_id}/reset-link', 'Reset link (old link stops working)')}
    </div>

    <h2>Students</h2>
    <table><tr><th>Name</th><th>Phone</th><th>Lang</th><th>Status</th><th></th></tr>{student_rows}</table>
    <div class="card">
      <strong>Add student</strong>
      <form method="post" action="/admin/instructor/{instructor_id}/students">
        <label>Name</label><input name="name" required>
        <label>Phone (with country code)</label><input name="phone" placeholder="+39..." required>
        <label>Language</label>
        <select name="language"><option value="it">Italian</option><option value="en">English</option></select>
        <button type="submit">Add student</button>
      </form>
    </div>

    <h2>Lessons</h2>
    {cards}{upcoming_html}{past_html}
    <div class="card">
      <strong>Schedule lesson</strong>
      <form method="post" action="/admin/instructor/{instructor_id}/lessons">
        <label>Student</label>
        <select name="student_id" required>{student_options or no_students}</select>
        <label>Date &amp; time (Rome local time)</label>
        <input type="datetime-local" name="when" required>
        <label>Location (optional)</label>
        <input name="location" placeholder="Via Roma 25, Cassino">
        <label>Reminder to the student</label>
        <select name="reminder">
          <option value="auto">Automatic (24h and 2h before)</option>
          <option value="now">Send right now</option>
          <option value="2min">Send in 2 minutes</option>
        </select>
        <button type="submit">Schedule lesson</button>
      </form>
    </div>

    <h2>Waitlist</h2>
    <table><tr><th>Student</th><th>Status</th><th></th></tr>{waitlist_rows}</table>
    <div class="card">
      <strong>Add to waitlist</strong>
      <form method="post" action="/admin/instructor/{instructor_id}/waitlist">
        <label>Student</label>
        <select name="student_id" required>{student_options or no_students}</select>
        <button type="submit">Add to waitlist</button>
      </form>
    </div>""")


def _require_instructor(s, instructor_id: int) -> Instructor:
    instructor = s.get(Instructor, instructor_id)
    if instructor is None:
        raise HTTPException(status_code=404, detail="Instructor not found")
    return instructor


def _require_own_student(s, instructor_id: int, student_id: int) -> Student:
    student = s.get(Student, student_id)
    if student is None or student.instructor_id != instructor_id:
        raise HTTPException(status_code=400, detail="That student does not belong to this instructor")
    return student


@router.post("/instructor/{instructor_id}/students")
def create_student(instructor_id: int, name: str = Form(...), phone: str = Form(...),
                   language: str = Form("it"), user: str = Depends(require_login)):
    phone = normalize_phone(phone)
    if language not in ("it", "en"):
        language = "it"
    with get_session() as s:
        _require_instructor(s, instructor_id)
        # The bot finds a student by phone number, so it must be unique.
        if s.exec(select(Student).where(Student.phone == phone)).first() is not None:
            raise HTTPException(status_code=400, detail=f"{phone} is already registered as a student")
        s.add(Student(name=name.strip(), phone=phone, instructor_id=instructor_id, language=language))
        s.commit()
    return RedirectResponse(url=f"/admin/instructor/{instructor_id}", status_code=303)


@router.post("/instructor/{instructor_id}/lessons")
def create_lesson(instructor_id: int, student_id: int = Form(...), when: str = Form(...),
                  location: str = Form(""), reminder: str = Form("auto"), user: str = Depends(require_login)):
    # datetime-local sends "YYYY-MM-DDTHH:MM" (some browsers add seconds); it is Rome local time
    local_dt = None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            local_dt = datetime.strptime(when, fmt).replace(tzinfo=LOCAL_TZ)
            break
        except ValueError:
            continue
    if local_dt is None:
        raise HTTPException(status_code=400, detail="Invalid date/time")
    utc_dt = local_dt.astimezone(timezone.utc)
    if utc_dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="That date/time is in the past")
    with get_session() as s:
        _require_instructor(s, instructor_id)
        _require_own_student(s, instructor_id, student_id)
        lesson = Lesson(instructor_id=instructor_id, student_id=student_id,
                        start_time=utc_dt, location=(location.strip() or None))
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        lesson_id = lesson.id
    back = f"/admin/instructor/{instructor_id}"
    return apply_reminder_choice(lesson_id, reminder, back) or RedirectResponse(url=back, status_code=303)


@router.post("/instructor/{instructor_id}/waitlist")
def create_waitlist(instructor_id: int, student_id: int = Form(...), user: str = Depends(require_login)):
    with get_session() as s:
        _require_instructor(s, instructor_id)
        _require_own_student(s, instructor_id, student_id)
        already = s.exec(select(WaitlistEntry).where(
            WaitlistEntry.instructor_id == instructor_id, WaitlistEntry.student_id == student_id)).first()
        if already is None:
            s.add(WaitlistEntry(instructor_id=instructor_id, student_id=student_id))
            s.commit()
    return RedirectResponse(url=f"/admin/instructor/{instructor_id}", status_code=303)


@router.post("/waitlist/{entry_id}/remove")
def remove_waitlist(entry_id: int, user: str = Depends(require_login)):
    with get_session() as s:
        entry = s.get(WaitlistEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry not found")
        instructor_id = entry.instructor_id
        s.delete(entry)
        s.commit()
    return RedirectResponse(url=f"/admin/instructor/{instructor_id}", status_code=303)


@router.post("/lesson/{lesson_id}/cancel")
def cancel_lesson(lesson_id: int, user: str = Depends(require_login)):
    with get_session() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found")
        lesson.status = "cancelled"
        lesson.awaiting_reply = False
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        offer_next_waitlist(s, lesson)  # exact same function the bot itself uses
        instructor_id = lesson.instructor_id
    return RedirectResponse(url=f"/admin/instructor/{instructor_id}", status_code=303)


@router.post("/student/{student_id}/deactivate")
def deactivate_student(student_id: int, user: str = Depends(require_login)):
    with get_session() as s:
        student = s.get(Student, student_id)
        if student is None:
            raise HTTPException(status_code=404, detail="Student not found")
        student.active = False
        s.add(student)
        s.commit()
        instructor_id = student.instructor_id
    return RedirectResponse(url=f"/admin/instructor/{instructor_id}", status_code=303)


@router.post("/instructor/{instructor_id}/reset-link")
def reset_link(instructor_id: int, user: str = Depends(require_login)):
    with get_session() as s:
        instructor = _require_instructor(s, instructor_id)
        instructor.access_token = secrets.token_urlsafe(16)
        s.add(instructor)
        s.commit()
    return RedirectResponse(url=f"/admin/instructor/{instructor_id}", status_code=303)


@router.post("/test-message", response_class=HTMLResponse)
def test_message(phone: str = Form(...), user: str = Depends(require_login)):
    phone = normalize_phone(phone)
    ok = wa.send_whatsapp_message(phone, "✅ DriveBot: test message. If you can read this, Twilio is connected correctly.")
    if ok:
        return _result_page(True, "Sent to Twilio", f"Twilio accepted the message for {esc(phone)}. Check that phone's WhatsApp.", "/admin/")
    hint = ""
    err = wa.last_error or "unknown error"
    if "63015" in err or "sandbox" in err.lower():
        hint = "<p><strong>Meaning:</strong> this phone has not joined the Sandbox (or joined more than 24h ago). From that phone, send the join code to the Sandbox number again.</p>"
    elif "20003" in err or "authenticate" in err.lower():
        hint = "<p><strong>Meaning:</strong> wrong TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN.</p>"
    elif "63007" in err or "from" in err.lower():
        hint = "<p><strong>Meaning:</strong> TWILIO_WHATSAPP_NUMBER is not a valid WhatsApp sender. Copy it from your Sandbox page.</p>"
    return _result_page(False, "Send failed", f"<code>{esc(err)}</code>{hint}", "/admin/")


@router.post("/lesson/{lesson_id}/resend", response_class=HTMLResponse)
def resend_reminder(lesson_id: int, user: str = Depends(require_login)):
    """Send the reminder right now (ignores the 24h window and 'already sent')."""
    with get_session() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found")
        back = f"/admin/instructor/{lesson.instructor_id}"
        student = s.get(Student, lesson.student_id)
        ok, err = send_reminder_now(s, lesson)
        if ok:
            return _result_page(True, "Reminder sent", f"Sent to {esc(student.name)} ({esc(student.phone)}). They can reply SI or NO.", back)
        return _result_page(False, "Send failed", f"<code>{esc(err or 'unknown error')}</code>", back)


@router.post("/lesson/{lesson_id}/remind-later", response_class=HTMLResponse)
def remind_later(lesson_id: int, user: str = Depends(require_login)):
    with get_session() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found")
        back = f"/admin/instructor/{lesson.instructor_id}"
    return apply_reminder_choice(lesson_id, "2min", back)
