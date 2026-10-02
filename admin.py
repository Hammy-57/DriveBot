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
import ui
from i18n import T, set_lang, use_request_lang
from phones import normalize_phone as _normalize
from scheduler import schedule_reminder
from db import get_session
from models import Instructor, Lesson, Student, WaitlistEntry

load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
LOCAL_TZ = ZoneInfo("Europe/Rome")

router = APIRouter(prefix="/admin", dependencies=[Depends(use_request_lang)])
security = HTTPBasic()
esc = html.escape


def require_login(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_user = secrets.compare_digest(credentials.username.encode(), ADMIN_USERNAME.encode())
    correct_pass = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def _local(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")


def normalize_phone(raw: str) -> str:
    try:
        return _normalize(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail=T("err_invalid_phone"))


def _base_url(request: Request) -> str:
    env = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return env or str(request.base_url).rstrip("/")


def _status_box() -> str:
    info = wa.status_info()
    rows = [
        ui.check_row(T("twilio_loaded"), ui.state(info["credentials"])),
        ui.check_row(T("wa_sender"), f"<code>{esc(info['from_number'] or T('not_set'))}</code>"),
        ui.check_row(f"{T('sandbox_mode')} (SANDBOX_FREEFORM)", ui.state(info["freeform"]), hint=T("sandbox_hint")),
    ]
    rows += [ui.check_row(f"{T('templates_set')}: {kind}", ui.state(bool(sid))) for kind, sid in TEMPLATE_SIDS.items()]
    test = f"""<div class="test-form"><form method="post" action="/admin/test-message">
      <div class="form-grid">{ui.field(T('send_test_label'), 'phone', placeholder='+39...', full=True, ltr=True)}</div>
      <div class="form-actions"><button type="submit" class="btn btn-primary">{esc(T('send_test'))}</button></div></form></div>"""
    return f'<div class="card"><div class="checks">{"".join(rows)}</div>{test}</div>'


def _last_error_banner() -> str:
    if not wa.last_error:
        return ""
    return ui.alert(T("last_problem"), f"<code>{esc(wa.last_error)}</code>")


def stat_cards(items) -> str:
    return ui.kpis(items)


def split_lessons(lessons):
    """(upcoming sorted soonest-first, everything else newest-first)."""
    now = datetime.now(timezone.utc)
    def aware(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    live = ("scheduled", "confirmed", "reschedule_requested")
    upcoming = sorted([l for l in lessons if l.status in live and aware(l.start_time) > now], key=lambda l: l.start_time)
    past = sorted([l for l in lessons if l not in upcoming], key=lambda l: l.start_time, reverse=True)
    return upcoming, past


def _page(title: str, body: str, home: str = "/admin/") -> str:
    return ui.page(title, body, home)


def error_page(status: int, message: str, back: str = "/admin/", lang: str | None = None) -> str:
    if lang:
        set_lang(lang)
    if status >= 500:
        message = T("err_server")
    return ui.page(T("err_title"), ui.result_view(False, T("err_title"), esc(message), back, T("back"),
                                                  code_line=T("err_code", n=status)), home=back)


def _result_page(ok: bool, title: str, detail: str, back: str, back_label: str | None = None) -> HTMLResponse:
    return HTMLResponse(ui.page(title, ui.result_view(ok, title, detail, back, back_label or T("back"))))


def apply_reminder_choice(lesson_id: int, choice: str, back: str, admin_hint: bool = False):
    """
    After creating a lesson: 'now' sends the reminder immediately, '2min' schedules it
    2 minutes from now, anything else = automatic (24h and 2h before) -> returns None.
    """
    if choice == "2min":
        run_at = schedule_reminder(lesson_id, 120).astimezone(LOCAL_TZ).strftime("%H:%M")
        detail = esc(T("reminder_scheduled_detail", time=run_at))
        if admin_hint:
            detail += " " + esc(T("hint_check"))
        return _result_page(True, T("reminder_scheduled"), detail, back)
    if choice == "now":
        with get_session() as s:
            lesson = s.get(Lesson, lesson_id)
            ok, err = send_reminder_now(s, lesson)
        if ok:
            return _result_page(True, T("reminder_sent"), esc(T("reminder_sent_lesson")), back)
        return _result_page(False, T("reminder_failed"), f"{esc(T('reminder_failed_detail'))} <code>{esc(err or '')}</code>", back)
    return None


@router.get("/", response_class=HTMLResponse)
def dashboard(user: str = Depends(require_login)):
    with get_session() as s:
        instructors = s.exec(select(Instructor)).all()

    heads = [T("name"), T("phone")]
    rows = [ui.tr(heads, [f"<a href='/admin/instructor/{i.id}'><strong>{esc(i.name)}</strong></a>",
                          f"<span class='mono' dir='ltr'>{esc(i.phone)}</span>"],
                  actions=f"<a class='btn btn-sm' href='/admin/instructor/{i.id}'>{esc(T('open'))}</a>")
            for i in instructors]

    add_form = ui.form("/admin/instructors",
                       ui.field(T("name"), "name") + ui.field(T("wa_phone_cc"), "phone", placeholder="+39...", ltr=True),
                       T("add_instructor"))
    body = (ui.header(esc(T("admin_title")), sub=T("admin_sub"))
            + ui.section(T("instructors"), ui.table(heads, rows, T("no_instructors")) + ui.panel(T("add_instructor"), add_form),
                         count=len(instructors), i=1)
            + _last_error_banner()
            + ui.section(T("system_check"), _status_box(), i=2))
    return ui.page(T("admin_title"), body)


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
            raise HTTPException(status_code=404, detail=T("err_not_found"))
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

    # ---- lessons
    lesson_heads = [T("student"), T("when_rome"), T("location"), T("status")]

    def lesson_row(l):
        buttons = ""
        if l.status in ("scheduled", "confirmed"):
            buttons += (ui.button_form(f"/admin/lesson/{l.id}/resend", T("send_now"), "ghost", confirm=False)
                        + ui.button_form(f"/admin/lesson/{l.id}/remind-later", T("send_in_2"), "ghost", confirm=False))
        if l.status in ("scheduled", "confirmed", "reschedule_requested"):
            buttons += ui.button_form(f"/admin/lesson/{l.id}/cancel", T("cancel"))
        return ui.tr(lesson_heads, [esc(name_of.get(l.student_id, "?")), f"<span class='num'>{_local(l.start_time)}</span>",
                                    esc(l.location or "–"), ui.badge(l.status)], actions=buttons, wrap=(2,))

    upcoming, past = split_lessons(lessons)
    upcoming_html = ui.table(lesson_heads, [lesson_row(l) for l in upcoming], T("no_upcoming"))
    past_html = ui.history(T("past_cancelled", n=len(past)), ui.table(lesson_heads, [lesson_row(l) for l in past])) if past else ""
    cards = ui.kpis([
        (len(upcoming), T("stat_upcoming")),
        (sum(1 for l in upcoming if l.status == "confirmed"), T("stat_confirmed")),
        (sum(1 for l in upcoming if l.status == "scheduled"), T("stat_waiting")),
        (sum(1 for l in upcoming if l.status == "reschedule_requested"), T("stat_resched")),
        (sum(1 for st in students if st.active), T("stat_students")),
    ])

    active_students = [st for st in students if st.active]
    student_options = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in active_students)
    no_students = f"<option disabled>{esc(T('add_student_first'))}</option>"
    pick = student_options or no_students

    lesson_form = ui.form(
        f"/admin/instructor/{instructor_id}/lessons",
        ui.select_field(T("student"), "student_id", pick)
        + ui.field(T("date_time"), "when", type="datetime-local")
        + ui.field(T("location_opt"), "location", placeholder="Via Roma 25, Cassino", required=False)
        + ui.select_field(T("reminder_to"), "reminder",
                          f'<option value="auto">{esc(T("rem_auto"))}</option><option value="now">{esc(T("rem_now"))}</option>'
                          f'<option value="2min">{esc(T("rem_2min"))}</option>'),
        T("schedule_lesson"))

    # ---- students
    stu_heads = [T("name"), T("phone"), T("language"), T("status")]
    student_rows = [
        ui.tr(stu_heads, [esc(st.name), f"<span class='mono' dir='ltr'>{esc(st.phone)}</span>", esc(st.language.upper()),
                          ui.badge("active" if st.active else "inactive")],
              actions=ui.button_form(f"/admin/student/{st.id}/deactivate", T("deactivate")) if st.active else "")
        for st in students
    ]
    student_form = ui.form(
        f"/admin/instructor/{instructor_id}/students",
        ui.field(T("name"), "name") + ui.field(T("wa_phone_cc"), "phone", placeholder="+39...", ltr=True)
        + ui.select_field(T("message_language"), "language",
                          f'<option value="it">{esc(T("lang_it"))}</option><option value="en">{esc(T("lang_en"))}</option>'),
        T("add_student"))

    # ---- waitlist
    wl_heads = [T("student"), T("status")]
    wl_rows = [
        ui.tr(wl_heads, [esc(name_of.get(w.student_id, "?")),
                         f"<span class='badge {'info' if w.offered else ''}'>{esc(T('offered_slot') if w.offered else T('waiting'))}</span>"],
              actions=ui.button_form(f"/admin/waitlist/{w.id}/remove", T("remove")))
        for w in waitlist
    ]
    wl_form = ui.form(f"/admin/instructor/{instructor_id}/waitlist", ui.select_field(T("student"), "student_id", pick),
                      T("add_to_waitlist"))

    link_card = (f'<div class="card reveal" style="--i:1"><div class="label-strong">{esc(T("private_page"))}</div>'
                 f'<p class="hint">{esc(T("private_hint"))}</p>'
                 + ui.linkbar(portal_link, T("copy"), T("copied"),
                              extra_html=ui.button_form(f"/admin/instructor/{instructor_id}/reset-link", T("reset_link"), small=False))
                 + "</div>")

    body = (ui.header(esc(instructor.name), crumb_href="/admin", crumb_label=T("back_instructors"),
                      extra_html=f"<span class='pill mono' dir='ltr'>{esc(instructor.phone)}</span>")
            + link_card + cards
            + ui.section(T("lessons"), upcoming_html + past_html + ui.panel(T("schedule_lesson"), lesson_form), count=len(upcoming), i=3)
            + ui.section(T("students"), ui.table(stu_heads, student_rows, T("no_students")) + ui.panel(T("add_student"), student_form),
                         count=len(active_students), i=4)
            + ui.section(T("waitlist"), ui.table(wl_heads, wl_rows, T("waitlist_empty")) + ui.panel(T("add_to_waitlist"), wl_form),
                         count=len(waitlist), i=5))
    return ui.page(f"{instructor.name} — DriveBot", body)


def _require_instructor(s, instructor_id: int) -> Instructor:
    instructor = s.get(Instructor, instructor_id)
    if instructor is None:
        raise HTTPException(status_code=404, detail=T("err_not_found"))
    return instructor


def _require_own_student(s, instructor_id: int, student_id: int) -> Student:
    student = s.get(Student, student_id)
    if student is None or student.instructor_id != instructor_id:
        raise HTTPException(status_code=404, detail=T("err_not_found"))
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
            raise HTTPException(status_code=400, detail=T("err_phone_dup"))
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
        raise HTTPException(status_code=400, detail=T("err_bad_datetime"))
    utc_dt = local_dt.astimezone(timezone.utc)
    if utc_dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail=T("err_past"))
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
    return apply_reminder_choice(lesson_id, reminder, back, admin_hint=True) or RedirectResponse(url=back, status_code=303)


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
            raise HTTPException(status_code=404, detail=T("err_not_found"))
        instructor_id = entry.instructor_id
        s.delete(entry)
        s.commit()
    return RedirectResponse(url=f"/admin/instructor/{instructor_id}", status_code=303)


@router.post("/lesson/{lesson_id}/cancel")
def cancel_lesson(lesson_id: int, user: str = Depends(require_login)):
    with get_session() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail=T("err_not_found"))
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
            raise HTTPException(status_code=404, detail=T("err_not_found"))
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
        return _result_page(True, T("sent_twilio"), esc(T("sent_twilio_detail", phone=phone)), "/admin/")
    hint = ""
    err = wa.last_error or "unknown error"
    if "63015" in err or "sandbox" in err.lower():
        hint = "<p><strong>Meaning:</strong> this phone has not joined the Sandbox (or joined more than 24h ago). From that phone, send the join code to the Sandbox number again.</p>"
    elif "20003" in err or "authenticate" in err.lower():
        hint = "<p><strong>Meaning:</strong> wrong TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN.</p>"
    elif "63007" in err or "from" in err.lower():
        hint = "<p><strong>Meaning:</strong> TWILIO_WHATSAPP_NUMBER is not a valid WhatsApp sender. Copy it from your Sandbox page.</p>"
    return _result_page(False, T("send_failed"), f"<code>{esc(err)}</code>{hint}", "/admin/")


@router.post("/lesson/{lesson_id}/resend", response_class=HTMLResponse)
def resend_reminder(lesson_id: int, user: str = Depends(require_login)):
    """Send the reminder right now (ignores the 24h window and 'already sent')."""
    with get_session() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail=T("err_not_found"))
        back = f"/admin/instructor/{lesson.instructor_id}"
        student = s.get(Student, lesson.student_id)
        ok, err = send_reminder_now(s, lesson)
        if ok:
            return _result_page(True, T("reminder_sent"), esc(T("reminder_sent_to", name=student.name, phone=student.phone)), back)
        return _result_page(False, T("send_failed"), f"<code>{esc(err or 'unknown error')}</code>", back)


@router.post("/lesson/{lesson_id}/remind-later", response_class=HTMLResponse)
def remind_later(lesson_id: int, user: str = Depends(require_login)):
    with get_session() as s:
        lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail=T("err_not_found"))
        back = f"/admin/instructor/{lesson.instructor_id}"
    return apply_reminder_choice(lesson_id, "2min", back, admin_hint=True)
