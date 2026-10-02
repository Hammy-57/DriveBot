"""
Private page for ONE instructor: /i/<secret-token>/

No password to remember: the long random link is the key. It shows and
edits only that instructor's own students, lessons and waitlist, and every
action re-checks ownership, so one instructor can never touch another's
data. The admin can reset a link at any time (old link stops working).
Cancelling a lesson here uses the same function as cancelling by WhatsApp,
so the waitlist offer still goes out automatically.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from admin import (LOCAL_TZ, _button, _local, _page, _status_chip, apply_reminder_choice, esc, normalize_phone,
                   split_lessons, stat_cards)
from bot_logic import offer_next_waitlist
from db import get_session
from i18n import T, use_request_lang
from models import Instructor, Lesson, Student, WaitlistEntry

router = APIRouter(prefix="/i/{token}", dependencies=[Depends(use_request_lang)])

def _instructor(s, token: str) -> Instructor:
    inst = None
    if token and len(token) >= 16:
        inst = s.exec(select(Instructor).where(Instructor.access_token == token)).first()
    if inst is None:
        raise HTTPException(status_code=404, detail=T("err_not_found"))
    return inst


def _own_student(s, inst: Instructor, student_id: int) -> Student:
    st = s.get(Student, student_id)
    if st is None or st.instructor_id != inst.id:
        raise HTTPException(status_code=404, detail=T("err_not_found"))
    return st


@router.get("/", response_class=HTMLResponse)
def portal_home(token: str):
    with get_session() as s:
        inst = _instructor(s, token)
        students = s.exec(select(Student).where(Student.instructor_id == inst.id)).all()
        lessons = s.exec(select(Lesson).where(Lesson.instructor_id == inst.id).order_by(Lesson.start_time.desc())).all()
        waitlist = s.exec(select(WaitlistEntry).where(WaitlistEntry.instructor_id == inst.id)).all()

    base = f"/i/{token}"
    name_of = {st.id: st.name for st in students}

    student_rows = "".join(
        f"<tr><td>{esc(st.name)}</td><td dir='ltr'>{esc(st.phone)}</td><td>{'IT' if st.language == 'it' else 'EN'}</td>"
        f"<td>{_button(f'{base}/student/{st.id}/deactivate', esc(T('remove'))) if st.active else esc(T('inactive'))}</td></tr>"
        for st in students
    ) or f"<tr><td colspan='4'>{esc(T('no_students'))}</td></tr>"

    def lesson_row(l):
        cancel = (_button(f'{base}/lesson/{l.id}/cancel', esc(T('cancel')))
                  if l.status in ('scheduled', 'confirmed', 'reschedule_requested') else '-')
        return (f"<tr><td>{esc(name_of.get(l.student_id, '?'))}</td><td>{_local(l.start_time)}</td>"
                f"<td>{esc(l.location or '-')}</td><td>{_status_chip(l.status)}</td><td>{cancel}</td></tr>")

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
        f"<td>{_button(f'{base}/waitlist/{w.id}/remove', esc(T('remove')))}</td></tr>"
        for w in waitlist
    ) or f"<tr><td colspan='3'>{esc(T('waitlist_empty'))}</td></tr>"

    opts = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in students if st.active)
    no_opts = f"<option disabled>{esc(T('add_student_first'))}</option>"

    return _page(f"{inst.name} — DriveBot", f"""
    <h1>🚗 {T('hello', name=esc(inst.name))}</h1>
    <p style="color:var(--muted)">{esc(T('portal_intro'))}</p>
    <p style="color:var(--muted);font-size:0.85rem">{esc(T('tip_whatsapp'))}</p>

    <h2>{esc(T('lessons'))}</h2>
    {cards}{upcoming_html}{past_html}
    <div class="card"><strong>{esc(T('new_lesson'))}</strong>
      <form method="post" action="{base}/lessons">
        <label>{esc(T('student'))}</label><select name="student_id" required>{opts or no_opts}</select>
        <label>{esc(T('date_time'))}</label><input type="datetime-local" name="when" required>
        <label>{esc(T('location_opt'))}</label><input name="location" placeholder="Via Roma 25, Cassino">
        <label>{esc(T('reminder_to'))}</label>
        <select name="reminder">
          <option value="auto">{esc(T('rem_auto'))}</option>
          <option value="now">{esc(T('rem_now'))}</option>
          <option value="2min">{esc(T('rem_2min'))}</option>
        </select>
        <button type="submit">{esc(T('schedule_lesson'))}</button>
      </form></div>

    <h2>{esc(T('students'))}</h2>
    <table><tr><th>{esc(T('name'))}</th><th>{esc(T('phone'))}</th><th>{esc(T('language'))}</th><th></th></tr>{student_rows}</table>
    <div class="card"><strong>{esc(T('new_student'))}</strong>
      <form method="post" action="{base}/students">
        <label>{esc(T('name'))}</label><input name="name" required>
        <label>{esc(T('wa_phone_cc'))}</label><input name="phone" placeholder="+39..." dir="ltr" required>
        <label>{esc(T('message_language'))}</label>
        <select name="language"><option value="it">{esc(T('lang_it'))}</option><option value="en">{esc(T('lang_en'))}</option></select>
        <button type="submit">{esc(T('add_student'))}</button>
      </form>
      <p style="color:var(--muted);font-size:13px">{esc(T('consent_note'))}</p></div>

    <h2>{esc(T('waitlist'))}</h2>
    <table><tr><th>{esc(T('student'))}</th><th>{esc(T('status'))}</th><th></th></tr>{waitlist_rows}</table>
    <div class="card"><strong>{esc(T('add_to_waitlist'))}</strong>
      <form method="post" action="{base}/waitlist">
        <label>{esc(T('student'))}</label><select name="student_id" required>{opts or no_opts}</select>
        <button type="submit">{esc(T('add'))}</button>
      </form></div>""")


def _back(token: str) -> RedirectResponse:
    return RedirectResponse(url=f"/i/{token}/", status_code=303)


@router.post("/students")
def add_student(token: str, name: str = Form(...), phone: str = Form(...), language: str = Form("it")):
    phone = normalize_phone(phone)
    with get_session() as s:
        inst = _instructor(s, token)
        if s.exec(select(Student).where(Student.phone == phone)).first() is not None:
            raise HTTPException(status_code=400, detail=T("err_phone_dup"))
        s.add(Student(name=name.strip(), phone=phone, instructor_id=inst.id,
                      language=language if language in ("it", "en") else "it"))
        s.commit()
    return _back(token)


@router.post("/lessons")
def add_lesson(token: str, student_id: int = Form(...), when: str = Form(...), location: str = Form(""),
               reminder: str = Form("auto")):
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
        inst = _instructor(s, token)
        _own_student(s, inst, student_id)
        lesson = Lesson(instructor_id=inst.id, student_id=student_id, start_time=utc_dt, location=(location.strip() or None))
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        lesson_id = lesson.id
    return apply_reminder_choice(lesson_id, reminder, f"/i/{token}/") or _back(token)


@router.post("/waitlist")
def add_waitlist(token: str, student_id: int = Form(...)):
    with get_session() as s:
        inst = _instructor(s, token)
        _own_student(s, inst, student_id)
        if s.exec(select(WaitlistEntry).where(WaitlistEntry.instructor_id == inst.id,
                                              WaitlistEntry.student_id == student_id)).first() is None:
            s.add(WaitlistEntry(instructor_id=inst.id, student_id=student_id))
            s.commit()
    return _back(token)


@router.post("/waitlist/{entry_id}/remove")
def remove_waitlist(token: str, entry_id: int):
    with get_session() as s:
        inst = _instructor(s, token)
        entry = s.get(WaitlistEntry, entry_id)
        if entry is None or entry.instructor_id != inst.id:
            raise HTTPException(status_code=404, detail=T("err_not_found"))
        s.delete(entry)
        s.commit()
    return _back(token)


@router.post("/lesson/{lesson_id}/cancel")
def cancel_lesson(token: str, lesson_id: int):
    with get_session() as s:
        inst = _instructor(s, token)
        lesson = s.get(Lesson, lesson_id)
        if lesson is None or lesson.instructor_id != inst.id:
            raise HTTPException(status_code=404, detail=T("err_not_found"))
        lesson.status = "cancelled"
        lesson.awaiting_reply = False
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        offer_next_waitlist(s, lesson)
    return _back(token)


@router.post("/student/{student_id}/deactivate")
def deactivate_student(token: str, student_id: int):
    with get_session() as s:
        inst = _instructor(s, token)
        st = _own_student(s, inst, student_id)
        st.active = False
        s.add(st)
        s.commit()
    return _back(token)
