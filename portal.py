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

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

import ui
from admin import DASH, LOCAL_TZ, _button, _local, apply_reminder_choice, esc, normalize_phone, split_lessons, stat_cards
from bot_logic import offer_next_waitlist
from db import get_session
from models import Instructor, Lesson, Student, WaitlistEntry

router = APIRouter(prefix="/i/{token}")

STATUS_IT = {
    "scheduled": "In programma",
    "confirmed": "Confermata",
    "cancelled": "Cancellata",
    "reschedule_requested": "Vuole spostarla",
    "no_show": "Assente",
    "completed": "Completata",
}


def _instructor(s, token: str) -> Instructor:
    inst = None
    if token and len(token) >= 16:
        inst = s.exec(select(Instructor).where(Instructor.access_token == token)).first()
    if inst is None:
        raise HTTPException(status_code=404, detail="Pagina non trovata")
    return inst


def _own_student(s, inst: Instructor, student_id: int) -> Student:
    st = s.get(Student, student_id)
    if st is None or st.instructor_id != inst.id:
        raise HTTPException(status_code=404, detail="Allievo non trovato")
    return st


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except HTTPException:
        raise HTTPException(status_code=400, detail="Numero non valido. Usa il formato +393331234567")


def _page(title: str, body: str) -> str:
    return ui.page(title, body, lang="it", context="Area istruttore",
                   extra_head='<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer">')


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
        f"<tr><td>{ui.person(st.name)}</td><td>{esc(st.phone)}</td><td>{'IT' if st.language == 'it' else 'EN'}</td>"
        f"<td><div class='actions'>{_button(f'{base}/student/{st.id}/deactivate', 'Rimuovi') if st.active else ui.badge('Rimosso')}</div></td></tr>"
        for st in students
    )

    def lesson_row(l):
        can_cancel = l.status in ("scheduled", "confirmed", "reschedule_requested")
        return (f"<tr><td>{ui.person(name_of.get(l.student_id, '?'))}</td><td class='nowrap'>{_local(l.start_time)}</td>"
                f"<td>{esc(l.location or DASH)}</td><td>{ui.badge(STATUS_IT.get(l.status, l.status), l.status)}</td>"
                f"<td><div class='actions'>{_button(f'{base}/lesson/{l.id}/cancel', 'Cancella') if can_cancel else ''}</div></td></tr>")

    upcoming, past = split_lessons(lessons)
    heads = ["Allievo", "Quando", "Luogo", "Stato", ""]
    upcoming_html = ui.table(heads, "".join(lesson_row(l) for l in upcoming), "Nessuna lezione in programma.")
    past_html = (f"<details><summary>Lezioni passate e cancellate ({len(past)})</summary>"
                 f"{ui.table(heads, ''.join(lesson_row(l) for l in past))}</details>") if past else ""
    cards = stat_cards([
        (len(upcoming), "lezioni in programma"),
        (sum(1 for l in upcoming if l.status == "confirmed"), "confermate"),
        (sum(1 for l in upcoming if l.status == "scheduled"), "in attesa di risposta"),
        (sum(1 for l in upcoming if l.status == "reschedule_requested"), "vogliono spostare"),
        (sum(1 for st in students if st.active), "allievi attivi"),
    ])

    waitlist_rows = "".join(
        f"<tr><td>{ui.person(name_of.get(w.student_id, '?'))}</td>"
        f"<td>{ui.badge('In attesa', 'b-info') if not w.offered else ui.badge('Slot proposto', 'b-warn')}</td>"
        f"<td><div class='actions'>{_button(f'{base}/waitlist/{w.id}/remove', 'Togli')}</div></td></tr>"
        for w in waitlist
    )

    opts = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in students if st.active)
    no_opts = "<option disabled selected>Aggiungi prima un allievo</option>"
    student_select = f'<select name="student_id" required>{opts or no_opts}</select>'

    lesson_form = ui.form_card(
        "Nuova lezione", f"{base}/lessons",
        ui.field("Allievo", student_select)
        + ui.field("Data e ora", '<input type="datetime-local" name="when" required>')
        + ui.field("Luogo", '<input name="location" placeholder="Via Roma 25, Cassino">', optional="(facoltativo)")
        + ui.field("Promemoria all'allievo",
                   '<select name="reminder"><option value="auto">Automatico (24 ore e 2 ore prima)</option>'
                   '<option value="now">Invia subito</option><option value="2min">Invia tra 2 minuti</option></select>'),
        "Aggiungi lezione",
    )
    student_form = ui.form_card(
        "Nuovo allievo", f"{base}/students",
        ui.field("Nome", '<input name="name" required>')
        + ui.field("Telefono WhatsApp", '<input name="phone" placeholder="+39..." required>', optional="(con prefisso, es. +39...)")
        + ui.field("Lingua dei messaggi", '<select name="language"><option value="it">Italiano</option><option value="en">Inglese</option></select>', full=True),
        "Aggiungi allievo",
        hint="Avvisa l'allievo che riceverà messaggi WhatsApp di promemoria da questo numero.",
    )
    waitlist_form = ui.form_card(
        "Aggiungi alla lista d'attesa", f"{base}/waitlist",
        ui.field("Allievo", student_select, full=True),
        "Aggiungi",
    )

    body = (
        ui.page_head(f"Ciao {esc(inst.name)}",
                     "Gli allievi ricevono un promemoria su WhatsApp 24 ore e 2 ore prima della lezione e possono confermare o cancellare rispondendo. "
                     "Se qualcuno cancella, lo slot viene proposto alla lista d'attesa. Le lezioni si leggono in ora italiana.")
        + ui.section("Lezioni", cards + upcoming_html + past_html + lesson_form)
        + ui.section("Allievi", ui.table(["Nome", "Telefono", "Lingua", ""], student_rows, "Nessun allievo."), count=len(students))
        + student_form
        + ui.section("Lista d'attesa", ui.table(["Allievo", "Stato", ""], waitlist_rows, "Lista d'attesa vuota."), count=len(waitlist))
        + waitlist_form
    )
    return _page(f"{inst.name} \u2014 DriveBot", body)


def _back(token: str) -> RedirectResponse:
    return RedirectResponse(url=f"/i/{token}/", status_code=303)


@router.post("/students")
def add_student(token: str, name: str = Form(...), phone: str = Form(...), language: str = Form("it")):
    phone = _phone(phone)
    with get_session() as s:
        inst = _instructor(s, token)
        if s.exec(select(Student).where(Student.phone == phone)).first() is not None:
            raise HTTPException(status_code=400, detail="Questo numero è già registrato.")
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
        raise HTTPException(status_code=400, detail="Data o ora non valida.")
    utc_dt = local_dt.astimezone(timezone.utc)
    if utc_dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="La data è nel passato.")
    with get_session() as s:
        inst = _instructor(s, token)
        _own_student(s, inst, student_id)
        lesson = Lesson(instructor_id=inst.id, student_id=student_id, start_time=utc_dt, location=(location.strip() or None))
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        lesson_id = lesson.id
    return apply_reminder_choice(lesson_id, reminder, f"/i/{token}/", it=True) or _back(token)


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
            raise HTTPException(status_code=404, detail="Non trovato")
        s.delete(entry)
        s.commit()
    return _back(token)


@router.post("/lesson/{lesson_id}/cancel")
def cancel_lesson(token: str, lesson_id: int):
    with get_session() as s:
        inst = _instructor(s, token)
        lesson = s.get(Lesson, lesson_id)
        if lesson is None or lesson.instructor_id != inst.id:
            raise HTTPException(status_code=404, detail="Lezione non trovata")
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
