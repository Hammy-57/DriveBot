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

import ui
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
DASH = "\u2013"

router = APIRouter(prefix="/admin")
security = HTTPBasic()
esc = html.escape


def require_login(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_user = secrets.compare_digest(credentials.username.encode(), ADMIN_USERNAME.encode())
    correct_pass = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


PAGE_STYLE = ""  # kept for backwards compatibility; styling now lives in ui.py


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
    return ui.badge("yes", "b-ok") if flag else ui.badge("NO", "b-bad")


def _status_box() -> str:
    info = wa.status_info()
    templates = "".join(
        f"<li><span>{esc(kind)}</span>{_yes(bool(sid))}</li>" for kind, sid in TEMPLATE_SIDS.items()
    )
    return f"""
    <div class="card">
      <h3>System check</h3>
      <ul class="checks">
        <li><span>Twilio credentials loaded</span>{_yes(info['credentials'])}</li>
        <li><span>WhatsApp sender</span><code>{esc(info['from_number'] or 'NOT SET')}</code></li>
        <li><span>Sandbox demo mode <span class="hint">(SANDBOX_FREEFORM — on = demo only, off = production)</span></span>{_yes(info['freeform'])}</li>
      </ul>
      <p class="hint" style="margin:14px 0 4px"><strong>Approved template IDs</strong></p>
      <ul class="checks">{templates}</ul>
      <form method="post" action="/admin/test-message" style="margin-top:18px">
        <div class="form-grid">
          {ui.field("Send a test WhatsApp message to", '<input name="phone" placeholder="+39..." required>', full=True, optional="(with country code)")}
        </div>
        <div class="form-actions"><button type="submit">Send test message</button></div>
      </form>
    </div>"""


def _last_error_banner() -> str:
    if not wa.last_error:
        return ""
    return (f'<div class="card danger"><h3 style="color:var(--bad)">Last WhatsApp sending problem</h3>'
            f'<p style="margin:8px 0 0"><code>{esc(wa.last_error)}</code></p></div>')


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
    cls = "small danger" if danger else "small secondary"
    return (f'<form class="inline" method="post" action="{action}">'
            f'<button class="{cls}">{label}</button></form>')


def _page(title: str, body: str) -> str:
    return ui.page(title, body, lang="en", context="Admin")


def error_page(status: int, message: str, back: str = "/admin/", it: bool = False) -> str:
    if it:
        title, back_label = "Qualcosa non ha funzionato", "Indietro"
        if status >= 500:
            message = "Errore del server. Riprova tra poco; se continua, avvisa chi ti ha attivato il servizio."
    else:
        title, back_label = "Something went wrong", "Back"
        if status >= 500:
            message = "Server error. The details were logged. Try again, and if it keeps happening check the Railway Deploy Logs."
    body = f"""
    <a class="crumb" href="{esc(back)}">{ui.ICON_BACK} {back_label}</a>
    <div class="card" style="margin-top:14px"><div class="result err">
      <div class="icon">{ui.ICON_ERR}</div>
      <div><h1>{esc(title)}</h1><p>{esc(message)}</p><p class="hint">Error {status}</p></div>
    </div></div>"""
    if it:
        return ui.page(title, body, lang="it", context="Area istruttore")
    return _page(title, body)


def _result_page(ok: bool, title: str, detail: str, back: str, back_label: str = "← Back") -> HTMLResponse:
    label = back_label.replace("←", "").strip()
    it = label.lower() == "indietro"
    body = f"""
    <a class="crumb" href="{esc(back)}">{ui.ICON_BACK} {esc(label)}</a>
    <div class="card" style="margin-top:14px"><div class="result {'ok' if ok else 'err'}">
      <div class="icon">{ui.ICON_OK if ok else ui.ICON_ERR}</div>
      <div><h1>{esc(title)}</h1><p>{detail}</p></div>
    </div></div>"""
    if it:
        return HTMLResponse(ui.page(title, body, lang="it", context="Area istruttore"))
    return HTMLResponse(_page(title, body))


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
        f"<tr><td>{ui.person(i.name)}</td><td>{esc(i.phone)}</td>"
        f"<td><div class='actions'><a class='btn small secondary' href='/admin/instructor/{i.id}' "
        f"style='color:var(--text)'>Open</a></div></td></tr>"
        for i in instructors
    )

    add_form = ui.form_card(
        "Add instructor", "/admin/instructors",
        ui.field("Name", '<input name="name" required>')
        + ui.field("WhatsApp phone", '<input name="phone" placeholder="+39..." required>', optional="(with country code)"),
        "Add instructor",
    )

    body = (
        ui.page_head("Instructors", "Manage driving instructors, their students and lesson reminders.")
        + ui.section("All instructors", ui.table(["Name", "Phone", ""], rows, "No instructors yet. Add one below."), count=len(instructors))
        + add_form
        + _last_error_banner()
        + ui.section("Setup", _status_box())
    )
    return _page("DriveBot Admin", body)


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
        f"<tr><td>{ui.person(st.name)}</td><td>{esc(st.phone)}</td><td>{esc(st.language.upper())}</td>"
        f"<td>{ui.badge('Active', 'b-ok') if st.active else ui.badge('Inactive')}</td>"
        f"<td><div class='actions'>{_button(f'/admin/student/{st.id}/deactivate', 'Deactivate') if st.active else ''}</div></td></tr>"
        for st in students
    )

    def lesson_row(l):
        live = l.status in ("scheduled", "confirmed")
        actions = ""
        if live:
            actions += _button(f"/admin/lesson/{l.id}/resend", "Send now", danger=False)
            actions += _button(f"/admin/lesson/{l.id}/remind-later", "Send in 2 min", danger=False)
        if l.status in ("scheduled", "confirmed", "reschedule_requested"):
            actions += _button(f"/admin/lesson/{l.id}/cancel", "Cancel")
        return (f"<tr><td>{ui.person(name_of.get(l.student_id, '?'))}</td>"
                f"<td class='nowrap'>{_local(l.start_time)}</td><td>{esc(l.location or DASH)}</td>"
                f"<td>{ui.badge(l.status.replace('_', ' ').capitalize(), l.status)}</td>"
                f"<td><div class='actions'>{actions}</div></td></tr>")

    upcoming, past = split_lessons(lessons)
    heads = ["Student", "When (Rome time)", "Location", "Status", ""]
    upcoming_html = ui.table(heads, "".join(lesson_row(l) for l in upcoming), "No upcoming lessons.")
    past_html = (f"<details><summary>Past and cancelled lessons ({len(past)})</summary>"
                 f"{ui.table(heads, ''.join(lesson_row(l) for l in past))}</details>") if past else ""
    cards = stat_cards([
        (len(upcoming), "upcoming lessons"),
        (sum(1 for l in upcoming if l.status == "confirmed"), "confirmed"),
        (sum(1 for l in upcoming if l.status == "scheduled"), "waiting for reply"),
        (sum(1 for l in upcoming if l.status == "reschedule_requested"), "want to reschedule"),
        (sum(1 for st in students if st.active), "active students"),
    ])

    waitlist_rows = "".join(
        f"<tr><td>{ui.person(name_of.get(w.student_id, '?'))}</td>"
        f"<td>{ui.badge('Waiting', 'b-info') if not w.offered else ui.badge('Offered a slot', 'b-warn')}</td>"
        f"<td><div class='actions'>{_button(f'/admin/waitlist/{w.id}/remove', 'Remove')}</div></td></tr>"
        for w in waitlist
    )

    active_students = [st for st in students if st.active]
    student_options = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in active_students)
    no_students = "<option disabled selected>Add a student first</option>"
    student_select = f'<select name="student_id" required>{student_options or no_students}</select>'

    link_card = f"""
    <div class="card">
      <h3>Private page for this instructor</h3>
      <p class="hint" style="margin:0">Send this link on WhatsApp. Anyone with the link can manage <em>only this instructor's</em> students and lessons.</p>
      <div class="copy-row">
        <input id="portal-link" readonly value="{esc(portal_link)}" onclick="this.select()">
        <button type="button" class="secondary" onclick="copyLink(this,'portal-link')">Copy</button>
      </div>
      <div class="form-actions">{_button(f'/admin/instructor/{instructor_id}/reset-link', 'Reset link (old link stops working)')}</div>
    </div>"""

    student_form = ui.form_card(
        "Add student", f"/admin/instructor/{instructor_id}/students",
        ui.field("Name", '<input name="name" required>')
        + ui.field("Phone", '<input name="phone" placeholder="+39..." required>', optional="(with country code)")
        + ui.field("Language", '<select name="language"><option value="it">Italian</option><option value="en">English</option></select>'),
        "Add student",
    )
    lesson_form = ui.form_card(
        "Schedule lesson", f"/admin/instructor/{instructor_id}/lessons",
        ui.field("Student", student_select)
        + ui.field("Date & time", '<input type="datetime-local" name="when" required>', optional="(Rome local time)")
        + ui.field("Location", '<input name="location" placeholder="Via Roma 25, Cassino">', optional="(optional)")
        + ui.field("Reminder to the student",
                   '<select name="reminder"><option value="auto">Automatic (24h and 2h before)</option>'
                   '<option value="now">Send right now</option><option value="2min">Send in 2 minutes</option></select>'),
        "Schedule lesson",
    )
    waitlist_form = ui.form_card(
        "Add to waitlist", f"/admin/instructor/{instructor_id}/waitlist",
        ui.field("Student", student_select, full=True),
        "Add to waitlist",
    )

    body = (
        ui.page_head(esc(instructor.name), esc(instructor.phone), back=("/admin", "All instructors"))
        + link_card
        + ui.section("Lessons", cards + upcoming_html + past_html + lesson_form)
        + ui.section("Students", ui.table(["Name", "Phone", "Lang", "Status", ""], student_rows, "No students yet."), count=len(students))
        + student_form
        + ui.section("Waitlist", ui.table(["Student", "Status", ""], waitlist_rows, "Waitlist empty."), count=len(waitlist))
        + waitlist_form
    )
    return _page(f"{instructor.name} \u2014 DriveBot Admin", body)


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
