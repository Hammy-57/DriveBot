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

import ui
from admin import LOCAL_TZ, _local, apply_reminder_choice, esc, normalize_phone, split_lessons
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

    # ---- lessons
    lesson_heads = [T("student"), T("when_rome"), T("location"), T("status")]

    def lesson_row(l):
        cancel = (ui.button_form(f"{base}/lesson/{l.id}/cancel", T("cancel"))
                  if l.status in ("scheduled", "confirmed", "reschedule_requested") else "")
        return ui.tr(lesson_heads, [esc(name_of.get(l.student_id, "?")), f"<span class='num'>{_local(l.start_time)}</span>",
                                    esc(l.location or "–"), ui.badge(l.status)], actions=cancel, wrap=(2,))

    upcoming, past = split_lessons(lessons)
    upcoming_html = ui.table(lesson_heads, [lesson_row(l) for l in upcoming], T("no_upcoming"))
    past_html = ui.history(T("past_cancelled", n=len(past)), ui.table(lesson_heads, [lesson_row(l) for l in past])) if past else ""
    cards = ui.kpis([
        (len(upcoming), T("stat_upcoming")),
        (sum(1 for l in upcoming if l.status == "confirmed"), T("stat_confirmed")),
        (sum(1 for l in upcoming if l.status == "scheduled"), T("stat_waiting")),
        (sum(1 for l in upcoming if l.status == "reschedule_requested"), T("stat_resched")),
        (sum(1 for st in students if st.active), T("stat_students")),
    ], i=1)

    active_students = [st for st in students if st.active]
    opts = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in active_students)
    pick = opts or f"<option disabled>{esc(T('add_student_first'))}</option>"

    lesson_form = ui.form(
        f"{base}/lessons",
        ui.select_field(T("student"), "student_id", pick)
        + ui.field(T("date_time"), "when", type="datetime-local")
        + ui.field(T("location_opt"), "location", placeholder="Via Roma 25, Cassino", required=False)
        + ui.select_field(T("reminder_to"), "reminder",
                          f'<option value="auto">{esc(T("rem_auto"))}</option><option value="now">{esc(T("rem_now"))}</option>'
                          f'<option value="2min">{esc(T("rem_2min"))}</option>'),
        T("schedule_lesson"))

    # ---- students
    stu_heads = [T("name"), T("phone"), T("language")]
    student_rows = [
        ui.tr(stu_heads, [esc(st.name), f"<span class='mono' dir='ltr'>{esc(st.phone)}</span>", "IT" if st.language == "it" else "EN"],
              actions=ui.button_form(f"{base}/student/{st.id}/deactivate", T("remove")))
        for st in active_students
    ]
    student_form = ui.form(
        f"{base}/students",
        ui.field(T("name"), "name") + ui.field(T("wa_phone_cc"), "phone", placeholder="+39...", ltr=True)
        + ui.select_field(T("message_language"), "language",
                          f'<option value="it">{esc(T("lang_it"))}</option><option value="en">{esc(T("lang_en"))}</option>')
        + f'<p class="hint full" style="grid-column:1/-1;margin:0">{esc(T("consent_note"))}</p>',
        T("add_student"))

    # ---- waitlist
    wl_heads = [T("student"), T("status")]
    wl_rows = [
        ui.tr(wl_heads, [esc(name_of.get(w.student_id, "?")),
                         f"<span class='badge {'info' if w.offered else ''}'>{esc(T('offered_slot') if w.offered else T('waiting'))}</span>"],
              actions=ui.button_form(f"{base}/waitlist/{w.id}/remove", T("remove")))
        for w in waitlist
    ]
    wl_form = ui.form(f"{base}/waitlist", ui.select_field(T("student"), "student_id", pick), T("add_to_waitlist"))

    body = (ui.header(T("hello", name=esc(inst.name)), sub=T("portal_intro"),
                      extra_html=f'<p class="note">{esc(T("tip_whatsapp"))}</p>')
            + cards
            + ui.section(T("lessons"), upcoming_html + past_html + ui.panel(T("schedule_lesson"), lesson_form), count=len(upcoming), i=2)
            + ui.section(T("students"), ui.table(stu_heads, student_rows, T("no_students")) + ui.panel(T("add_student"), student_form),
                         count=len(active_students), i=3)
            + ui.section(T("waitlist"), ui.table(wl_heads, wl_rows, T("waitlist_empty")) + ui.panel(T("add_to_waitlist"), wl_form),
                         count=len(waitlist), i=4))
    return ui.page(f"{inst.name} — DriveBot", body, home=f"{base}/")


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
