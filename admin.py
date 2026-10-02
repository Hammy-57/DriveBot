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
from i18n import LANGS, RTL, T, current, current_path, set_lang, use_request_lang
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


PAGE_STYLE = """
<style>
  :root { --bg:#17181c; --text:#e8e9ec; --line:#2a2b30; --h2line:#35363c; --accent:#f5c451; --muted:#9a9ca3;
          --card:#1e1f24; --inbg:#111216; --inline:#3a3b41; --chip:#2a2b30; --statbg:#1e1f25; --statline:#2c2d34;
          --stat:#f5c542; color-scheme: dark; }
  :root[data-theme="light"] { --bg:#f6f6f8; --text:#1c1d21; --line:#e3e4e9; --h2line:#d9dae0; --accent:#a86f00;
          --muted:#6b6e78; --card:#ffffff; --inbg:#ffffff; --inline:#c9cad2; --chip:#ececf0; --statbg:#ffffff;
          --statline:#e0e1e6; --stat:#a86f00; color-scheme: light; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background:var(--bg); color:var(--text);
         max-width: 860px; margin: 0 auto; padding: 24px 16px 60px; line-height: 1.45; }
  h1 { font-size: 1.3rem; margin: 0 0 4px; }
  h2 { font-size: 1.05rem; margin: 32px 0 10px; border-bottom: 1px solid var(--h2line); padding-bottom: 6px; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0 18px; font-size: 0.92rem; }
  th, td { text-align: start; padding: 7px 8px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 500; font-size: 0.8rem; }
  form.inline { display: inline; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 16px 18px; margin: 14px 0; }
  input, select { background:var(--inbg); border:1px solid var(--inline); color:var(--text); padding:7px 9px; border-radius:5px; font-size:0.92rem; }
  label { display:block; font-size:0.82rem; color:var(--muted); margin: 10px 0 3px; }
  button { background:#f5c451; color:#17181c; border:none; padding:8px 16px; border-radius:5px;
           font-weight:600; cursor:pointer; margin-top:12px; font-size:0.9rem; }
  button.danger { background:#e05555; color:#fff; }
  button.small { padding:4px 10px; font-size:0.8rem; margin-top:0; }
  .status { font-size:0.78rem; padding:2px 8px; border-radius:10px; background:var(--chip); }
  .top-link { font-size: 0.85rem; }
  .ctlbar { display:flex; gap:8px; justify-content:flex-end; align-items:center; margin-bottom:14px; }
  .ctlbar form { margin:0; }
  .ctlbar select { padding:4px 8px; font-size:0.82rem; }
  button.ctl { background:var(--chip); color:var(--text); border:1px solid var(--inline); margin-top:0; padding:3px 9px; font-size:0.95rem; font-weight:500; }
  .stats{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
  .stat{background:var(--statbg);border:1px solid var(--statline);border-radius:10px;padding:10px 16px;min-width:110px}
  .stat b{display:block;font-size:24px;color:var(--stat)}
  .stat span{font-size:12px;color:var(--muted)}
  details{margin:8px 0}summary{cursor:pointer;color:var(--muted);padding:6px 0}
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
        raise HTTPException(status_code=400, detail=T("err_invalid_phone"))


def _base_url(request: Request) -> str:
    env = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return env or str(request.base_url).rstrip("/")


def _yes(flag: bool) -> str:
    if flag:
        return f"<span style='color:#5fd38d'>{esc(T('yes'))}</span>"
    return f"<span style='color:#ff6b6b'>{esc(T('no'))}</span>"


def _status_box() -> str:
    info = wa.status_info()
    templates = "".join(f"<li>{esc(kind)}: {_yes(bool(sid))}</li>" for kind, sid in TEMPLATE_SIDS.items())
    return f"""
    <div class="card">
      <strong>{esc(T('system_check'))}</strong>
      <ul style="line-height:1.7">
        <li>{esc(T('twilio_loaded'))}: {_yes(info['credentials'])}</li>
        <li>{esc(T('wa_sender'))}: <code>{esc(info['from_number'] or 'NOT SET')}</code></li>
        <li>{esc(T('sandbox_mode'))} (SANDBOX_FREEFORM): {_yes(info['freeform'])} ({esc(T('sandbox_hint'))})</li>
        <li>{esc(T('templates_set'))}:<ul>{templates}</ul></li>
      </ul>
      <form method="post" action="/admin/test-message">
        <label>{esc(T('send_test_label'))}</label>
        <input name="phone" placeholder="+39..." dir="ltr" required>
        <button type="submit">{esc(T('send_test'))}</button>
      </form>
    </div>"""


def _last_error_banner() -> str:
    if not wa.last_error:
        return ""
    return (f'<div class="card" style="border-color:#ff6b6b"><strong style="color:#ff6b6b">{esc(T("last_problem"))}</strong>'
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


def _status_chip(status: str) -> str:
    return f"<span class='status'>{esc(T('status_' + status))}</span>"


_THEME_HEAD_JS = 'try{var t=localStorage.getItem("theme");if(t)document.documentElement.setAttribute("data-theme",t)}catch(e){}'
_THEME_JS = (
    'function themeIcon(){var b=document.getElementById("themeBtn");'
    'if(b)b.textContent=document.documentElement.getAttribute("data-theme")==="light"?"\\u{1F319}":"\\u2600\\uFE0F"}'
    'function toggleTheme(){var r=document.documentElement,n=r.getAttribute("data-theme")==="light"?"dark":"light";'
    'r.setAttribute("data-theme",n);try{localStorage.setItem("theme",n)}catch(e){}themeIcon()}'
    'themeIcon();'
)


def _controls() -> str:
    lang, path = current.get(), current_path.get()
    options = "".join(
        f'<option value="{code}"{" selected" if code == lang else ""}>{esc(name)}</option>' for code, name in LANGS.items()
    )
    label = esc(T("language"))
    theme = esc(T("theme"))
    return (f'<div class="ctlbar"><form method="get" action="/set-lang">'
            f'<input type="hidden" name="next" value="{esc(path)}">'
            f'<select name="lang" title="{label}" aria-label="{label}" onchange="this.form.submit()">{options}</select>'
            f'<noscript><button class="small" type="submit">OK</button></noscript></form>'
            f'<button type="button" class="ctl" id="themeBtn" onclick="toggleTheme()" title="{theme}" aria-label="{theme}"></button></div>')


def _page(title: str, body: str) -> str:
    lang = current.get()
    direction = "rtl" if lang in RTL else "ltr"
    return (f'<!DOCTYPE html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer">'
            f'<title>{esc(title)}</title><script>{_THEME_HEAD_JS}</script>{PAGE_STYLE}</head>'
            f'<body>{_controls()}{body}<script>{_THEME_JS}</script></body></html>')


def error_page(status: int, message: str, back: str = "/admin/", lang: str | None = None) -> str:
    if lang:
        set_lang(lang)
    if status >= 500:
        message = T("err_server")
    return _page(T("err_title"), f"""
    <p class="top-link"><a href="{esc(back)}">{esc(T('back'))}</a></p>
    <h1 style="color:#ff6b6b">❌ {esc(T('err_title'))}</h1>
    <div class="card"><p>{esc(message)}</p><p style="color:var(--muted);font-size:13px">{esc(T('err_code', n=status))}</p></div>""")


def _result_page(ok: bool, title: str, detail: str, back: str, back_label: str | None = None) -> HTMLResponse:
    color = "#5fd38d" if ok else "#ff6b6b"
    return HTMLResponse(_page(title, f"""
    <p class="top-link"><a href="{esc(back)}">{esc(back_label or T('back'))}</a></p>
    <h1 style="color:{color}">{'✅' if ok else '❌'} {esc(title)}</h1>
    <div class="card"><p>{detail}</p></div>"""))


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

    rows = "".join(
        f"<tr><td>{esc(i.name)}</td><td dir='ltr'>{esc(i.phone)}</td>"
        f"<td><a href='/admin/instructor/{i.id}'>{esc(T('open'))} →</a></td></tr>"
        for i in instructors
    ) or f"<tr><td colspan='3'>{esc(T('no_instructors'))}</td></tr>"

    return _page(T("admin_title"), f"""
    <h1>🚗 {esc(T('admin_title'))}</h1>
    <h2>{esc(T('instructors'))}</h2>
    <table><tr><th>{esc(T('name'))}</th><th>{esc(T('phone'))}</th><th></th></tr>{rows}</table>
    <div class="card">
      <strong>{esc(T('add_instructor'))}</strong>
      <form method="post" action="/admin/instructors">
        <label>{esc(T('name'))}</label><input name="name" required>
        <label>{esc(T('wa_phone_cc'))}</label><input name="phone" placeholder="+39..." dir="ltr" required>
        <button type="submit">{esc(T('add_instructor'))}</button>
      </form>
    </div>
    {_last_error_banner()}
    <h2>{esc(T('setup'))}</h2>{_status_box()}""")


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

    student_rows = "".join(
        f"<tr><td>{esc(st.name)}</td><td dir='ltr'>{esc(st.phone)}</td><td>{esc(st.language)}</td>"
        f"<td><span class='status'>{esc(T('active') if st.active else T('inactive'))}</span></td>"
        f"<td>{_button(f'/admin/student/{st.id}/deactivate', esc(T('deactivate'))) if st.active else '-'}</td></tr>"
        for st in students
    ) or f"<tr><td colspan='5'>{esc(T('no_students'))}</td></tr>"

    def lesson_row(l):
        live = l.status in ("scheduled", "confirmed")
        send_buttons = (_button(f'/admin/lesson/{l.id}/resend', esc(T('send_now')), danger=False)
                        + _button(f'/admin/lesson/{l.id}/remind-later', esc(T('send_in_2')), danger=False)) if live else ""
        cancel_button = (_button(f'/admin/lesson/{l.id}/cancel', esc(T('cancel')))
                         if l.status in ("scheduled", "confirmed", "reschedule_requested") else "-")
        return (f"<tr><td>{esc(name_of.get(l.student_id, '?'))}</td>"
                f"<td>{_local(l.start_time)}</td><td>{esc(l.location or '-')}</td>"
                f"<td>{_status_chip(l.status)}</td><td>{send_buttons} {cancel_button}</td></tr>")

    upcoming, past = split_lessons(lessons)
    head = (f"<tr><th>{esc(T('student'))}</th><th>{esc(T('when_rome'))}</th><th>{esc(T('location'))}</th>"
            f"<th>{esc(T('status'))}</th><th></th></tr>")
    upcoming_body = "".join(lesson_row(l) for l in upcoming) or f"<tr><td colspan=5>{esc(T('no_upcoming'))}</td></tr>"
    upcoming_html = f"<table>{head}{upcoming_body}</table>"
    past_html = (f"<details><summary>{esc(T('past_cancelled', n=len(past)))}</summary><table>{head}"
                 f"{''.join(lesson_row(l) for l in past)}</table></details>") if past else ""
    cards = stat_cards([
        (len(upcoming), T("stat_upcoming")),
        (sum(1 for l in upcoming if l.status == "confirmed"), T("stat_confirmed")),
        (sum(1 for l in upcoming if l.status == "scheduled"), T("stat_waiting")),
        (sum(1 for l in upcoming if l.status == "reschedule_requested"), T("stat_resched")),
        (sum(1 for st in students if st.active), T("stat_students")),
    ])

    waitlist_rows = "".join(
        f"<tr><td>{esc(name_of.get(w.student_id, '?'))}</td>"
        f"<td>{esc(T('waiting') if not w.offered else T('offered_slot'))}</td>"
        f"<td>{_button(f'/admin/waitlist/{w.id}/remove', esc(T('remove')))}</td></tr>"
        for w in waitlist
    ) or f"<tr><td colspan='3'>{esc(T('waitlist_empty'))}</td></tr>"

    active_students = [st for st in students if st.active]
    student_options = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in active_students)
    no_students = f"<option disabled>{esc(T('add_student_first'))}</option>"

    return _page(f"{instructor.name} — DriveBot", f"""
    <p class="top-link"><a href="/admin">{esc(T('back_instructors'))}</a></p>
    <h1>{esc(instructor.name)}</h1>
    <p style="color:var(--muted)" dir="ltr">{esc(instructor.phone)}</p>
    <div class="card">
      <strong>{esc(T('private_page'))}</strong>
      <p>{esc(T('private_hint'))}</p>
      <input readonly value="{esc(portal_link)}" onclick="this.select()" dir="ltr" style="width:100%">
      {_button(f'/admin/instructor/{instructor_id}/reset-link', esc(T('reset_link')))}
    </div>

    <h2>{esc(T('students'))}</h2>
    <table><tr><th>{esc(T('name'))}</th><th>{esc(T('phone'))}</th><th>{esc(T('language'))}</th><th>{esc(T('status'))}</th><th></th></tr>{student_rows}</table>
    <div class="card">
      <strong>{esc(T('add_student'))}</strong>
      <form method="post" action="/admin/instructor/{instructor_id}/students">
        <label>{esc(T('name'))}</label><input name="name" required>
        <label>{esc(T('wa_phone_cc'))}</label><input name="phone" placeholder="+39..." dir="ltr" required>
        <label>{esc(T('message_language'))}</label>
        <select name="language"><option value="it">{esc(T('lang_it'))}</option><option value="en">{esc(T('lang_en'))}</option></select>
        <button type="submit">{esc(T('add_student'))}</button>
      </form>
    </div>

    <h2>{esc(T('lessons'))}</h2>
    {cards}{upcoming_html}{past_html}
    <div class="card">
      <strong>{esc(T('schedule_lesson'))}</strong>
      <form method="post" action="/admin/instructor/{instructor_id}/lessons">
        <label>{esc(T('student'))}</label>
        <select name="student_id" required>{student_options or no_students}</select>
        <label>{esc(T('date_time'))}</label>
        <input type="datetime-local" name="when" required>
        <label>{esc(T('location_opt'))}</label>
        <input name="location" placeholder="Via Roma 25, Cassino">
        <label>{esc(T('reminder_to'))}</label>
        <select name="reminder">
          <option value="auto">{esc(T('rem_auto'))}</option>
          <option value="now">{esc(T('rem_now'))}</option>
          <option value="2min">{esc(T('rem_2min'))}</option>
        </select>
        <button type="submit">{esc(T('schedule_lesson'))}</button>
      </form>
    </div>

    <h2>{esc(T('waitlist'))}</h2>
    <table><tr><th>{esc(T('student'))}</th><th>{esc(T('status'))}</th><th></th></tr>{waitlist_rows}</table>
    <div class="card">
      <strong>{esc(T('add_to_waitlist'))}</strong>
      <form method="post" action="/admin/instructor/{instructor_id}/waitlist">
        <label>{esc(T('student'))}</label>
        <select name="student_id" required>{student_options or no_students}</select>
        <button type="submit">{esc(T('add_to_waitlist'))}</button>
      </form>
    </div>""")


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
