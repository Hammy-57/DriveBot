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

from admin import LOCAL_TZ, PAGE_STYLE, _button, _local, apply_reminder_choice, esc, normalize_phone, split_lessons, stat_cards
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
    return (f'<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer">'
            f'<title>{esc(title)}</title>{PAGE_STYLE}</head><body>{body}</body></html>')


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
        f"<tr><td>{esc(st.name)}</td><td>{esc(st.phone)}</td><td>{'IT' if st.language == 'it' else 'EN'}</td>"
        f"<td>{_button(f'{base}/student/{st.id}/deactivate', 'Rimuovi') if st.active else 'Rimosso'}</td></tr>"
        for st in students
    ) or "<tr><td colspan='4'>Nessun allievo.</td></tr>"

    def lesson_row(l):
        return (f"<tr><td>{esc(name_of.get(l.student_id, '?'))}</td><td>{_local(l.start_time)}</td>"
                f"<td>{esc(l.location or '-')}</td><td><span class='status'>{esc(STATUS_IT.get(l.status, l.status))}</span></td>"
                f"<td>{_button(f'{base}/lesson/{l.id}/cancel', 'Cancella') if l.status in ('scheduled', 'confirmed', 'reschedule_requested') else '-'}</td></tr>")

    upcoming, past = split_lessons(lessons)
    head = "<tr><th>Allievo</th><th>Quando</th><th>Luogo</th><th>Stato</th><th></th></tr>"
    upcoming_html = f"<table>{head}{''.join(lesson_row(l) for l in upcoming) or '<tr><td colspan=5>Nessuna lezione in programma.</td></tr>'}</table>"
    past_html = (f"<details><summary>Lezioni passate e cancellate ({len(past)})</summary><table>{head}"
                 f"{''.join(lesson_row(l) for l in past)}</table></details>") if past else ""
    cards = stat_cards([
        (len(upcoming), "lezioni in programma"),
        (sum(1 for l in upcoming if l.status == "confirmed"), "confermate"),
        (sum(1 for l in upcoming if l.status == "scheduled"), "in attesa di risposta"),
        (sum(1 for l in upcoming if l.status == "reschedule_requested"), "vogliono spostare"),
        (sum(1 for st in students if st.active), "allievi attivi"),
    ])

    waitlist_rows = "".join(
        f"<tr><td>{esc(name_of.get(w.student_id, '?'))}</td>"
        f"<td>{'In attesa' if not w.offered else 'Slot proposto'}</td>"
        f"<td>{_button(f'{base}/waitlist/{w.id}/remove', 'Togli')}</td></tr>"
        for w in waitlist
    ) or "<tr><td colspan='3'>Lista d'attesa vuota.</td></tr>"

    opts = "".join(f"<option value='{st.id}'>{esc(st.name)}</option>" for st in students if st.active)
    no_opts = "<option disabled>Aggiungi prima un allievo</option>"

    return _page(f"{inst.name} — DriveBot", f"""
    <h1>🚗 Ciao {esc(inst.name)}</h1>
    <p style="color:#9a9ca3">Gli allievi ricevono un promemoria su WhatsApp 24 ore e 2 ore prima della lezione e possono confermare o cancellare rispondendo.
    Se qualcuno cancella, lo slot viene proposto alla lista d'attesa. Le lezioni si leggono in ora italiana.</p>

    <h2>Lezioni</h2>
    {cards}{upcoming_html}{past_html}
    <div class="card"><strong>Nuova lezione</strong>
      <form method="post" action="{base}/lessons">
        <label>Allievo</label><select name="student_id" required>{opts or no_opts}</select>
        <label>Data e ora</label><input type="datetime-local" name="when" required>
        <label>Luogo (facoltativo)</label><input name="location" placeholder="Via Roma 25, Cassino">
        <label>Promemoria all'allievo</label>
        <select name="reminder">
          <option value="auto">Automatico (24 ore e 2 ore prima)</option>
          <option value="now">Invia subito</option>
          <option value="2min">Invia tra 2 minuti</option>
        </select>
        <button type="submit">Aggiungi lezione</button>
      </form></div>

    <h2>Allievi</h2>
    <table><tr><th>Nome</th><th>Telefono</th><th>Lingua</th><th></th></tr>{student_rows}</table>
    <div class="card"><strong>Nuovo allievo</strong>
      <form method="post" action="{base}/students">
        <label>Nome</label><input name="name" required>
        <label>Telefono WhatsApp (con prefisso, es. +39...)</label><input name="phone" placeholder="+39..." required>
        <label>Lingua dei messaggi</label>
        <select name="language"><option value="it">Italiano</option><option value="en">Inglese</option></select>
        <button type="submit">Aggiungi allievo</button>
      </form>
      <p style="color:#9a9ca3;font-size:13px">Avvisa l'allievo che riceverà messaggi WhatsApp di promemoria da questo numero.</p></div>

    <h2>Lista d'attesa</h2>
    <table><tr><th>Allievo</th><th>Stato</th><th></th></tr>{waitlist_rows}</table>
    <div class="card"><strong>Aggiungi alla lista d'attesa</strong>
      <form method="post" action="{base}/waitlist">
        <label>Allievo</label><select name="student_id" required>{opts or no_opts}</select>
        <button type="submit">Aggiungi</button>
      </form></div>""")


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
