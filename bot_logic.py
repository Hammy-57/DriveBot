"""
This file is the actual product. Everything else (FastAPI, scheduler,
Twilio wrapper) is just plumbing to get messages in and out.

Jobs handled here:
1. Send lesson reminders (24h and 2h before) -> check_and_send_reminders()
   Uses WhatsApp TEMPLATES (see whatsapp.py) because these are
   business-initiated messages -- required by WhatsApp policy.
2. Handle a student's WhatsApp reply -> handle_incoming_message()
   Uses free-form replies -- allowed because it's within 24h of the
   student's own inbound message.
3. Offer a freed slot to the next waitlisted student ->
   offer_next_waitlist() -- also a template send, for the same reason.

Design choices, on purpose:
- Students do NOT self-register or create lessons by texting the bot.
  An instructor adds their own students and schedules lessons (for
  now via seed.py / the database directly; later via an admin
  dashboard -- a separate, bigger piece of work).
- Times are stored in UTC in the database (good practice), but always
  DISPLAYED in Europe/Rome local time, since that's where the business
  operates. See LOCAL_TZ below.
- Reminders check "have I sent this yet and are we now inside the
  window" rather than "are we in an exact narrow window" -- this makes
  the system recover correctly even if the scheduler was down for a
  while (e.g. your laptop was off, or a redeploy took a few minutes).
"""
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlmodel import Session, select

import whatsapp as _wa
from models import Instructor, Lesson, Student, WaitlistEntry
from phones import normalize_phone as _norm_phone
from whatsapp import send_whatsapp_message, send_whatsapp_template

load_dotenv()

LOCAL_TZ = ZoneInfo("Europe/Rome")
log = logging.getLogger("drivebot")

# How long a waitlisted student has to answer an offer before it moves on
# to the next person.
WAITLIST_OFFER_MINUTES = 30

# Template texts. These are EXACTLY what you paste into the Twilio Content
# Template Builder (variables must be sequential {{1}}..{{n}} with none
# skipped, and a template must not start or end with a variable). The same
# text is used as plain text in SANDBOX_FREEFORM demo mode.
TEMPLATE_TEXTS = {
    "reminder_24h": "Ciao {{1}}! Hai una lezione di guida il {{2}} alle {{3}}. Luogo: {{4}}. Rispondi SI per confermare o NO per cancellare.",
    "reminder_2h": "Ciao {{1}}, promemoria: la tua lezione del {{2}} e' tra circa 2 ore, alle {{3}}. Luogo: {{4}}. A dopo!",
    "waitlist_offer": "Ciao {{1}}! Si e' liberato uno slot per il {{2}} alle {{3}}. Luogo: {{4}}. Lo vuoi? Rispondi SI o NO.",
    "student_welcome": "Ciao {{1}}! Sono l'assistente WhatsApp del tuo istruttore {{2}}. Ti mandero' qui i promemoria delle tue lezioni di guida. Rispondi MENU per le opzioni oppure STOP per non ricevere piu' messaggi.",
    "instructor_notice": "Aggiornamento DriveBot per il tuo calendario: {{1}} Rispondi a questo messaggio per continuare a ricevere gli avvisi in chat.",
}
# Content SIDs ("HX...") of the approved templates, from your .env.
TEMPLATE_SIDS = {
    "reminder_24h": os.getenv("TWILIO_TEMPLATE_REMINDER_24H"),
    "reminder_2h": os.getenv("TWILIO_TEMPLATE_REMINDER_2H"),
    "waitlist_offer": os.getenv("TWILIO_TEMPLATE_WAITLIST_OFFER"),
    "instructor_notice": os.getenv("TWILIO_TEMPLATE_INSTRUCTOR_NOTICE"),
    "student_welcome": os.getenv("TWILIO_TEMPLATE_STUDENT_WELCOME"),
}

CONFIRM_WORDS = {"si", "sì", "yes", "s", "ok", "va bene", "y"}
CANCEL_WORDS = {"no", "n", "annulla", "cancella", "cancel", "2"}
# A bare "no"/"n" only cancels when the student is answering a reminder;
# otherwise it could be a "no" to anything.
AMBIGUOUS_CANCEL_WORDS = {"no", "n"}
RESCHEDULE_WORDS = {"riprogramma", "reschedule", "cambia", "cambiare", "spostare", "3"}
MENU_WORDS = {"menu", "help", "aiuto", "4"}
STOP_WORDS = {"stop", "basta", "unsubscribe"}

# Instructor commands (sent from the instructor's own WhatsApp number)
ADD_WORDS = {"aggiungi", "add", "nuovo", "nuova"}
REMOVE_WORDS = {"rimuovi", "remove", "elimina", "togli"}
LIST_WORDS = {"lista", "allievi", "studenti", "students", "list"}
LINK_WORDS = {"pagina", "link", "sito"}
MY_LESSONS_WORDS = {
    "1", "le mie lezioni", "my lessons", "lezioni", "lezione",
    "prossima", "prossima lezione", "quando", "quando e la lezione", "when",
}
ENGLISH_WORDS = {"english", "inglese", "en"}
ITALIAN_WORDS = {"italiano", "italian", "it"}

VALID_STATUSES = {
    "scheduled", "confirmed", "completed", "cancelled",
    "reschedule_requested", "no_show",
}

MESSAGES = {
    "it": {
        "confirmed": "Perfetto {name}, lezione confermata per il {when}! 🚗",
        "cancelled": "Lezione cancellata, nessun problema. Se vuoi riprenotare scrivi al tuo istruttore.",
        "no_upcoming": "Non hai lezioni programmate al momento.",
        "unrecognized": "Non ho capito. Scrivi MENU per vedere le opzioni.",
        "not_registered": "Numero non riconosciuto. Contatta il tuo istruttore per essere registrato.",
        "menu": "📋 DRIVEBOT\n\n1️⃣ La mia prossima lezione\n2️⃣ Cancella lezione\n3️⃣ Richiedi un cambio orario\n4️⃣ Aiuto\n\nScrivi ENGLISH per cambiare lingua.",
        "my_lessons_none": "Non hai lezioni in programma al momento.",
        "my_lessons_one": "La tua prossima lezione: {when}.{location}",
        "reschedule_requested": "Certo! Ho avvisato il tuo istruttore.\n\nLezione attuale:\n📅 {date}\n⏰ {time}\n\nIl tuo istruttore ti proporra' un nuovo orario.",
        "reschedule_no_lesson": "Non hai lezioni da riprogrammare al momento.",
        "help": "Scrivi SI o NO per confermare/cancellare una lezione, oppure MENU per vedere tutte le opzioni.",
        "lang_set": "Lingua impostata su Italiano 🇮🇹",
        "waitlist_confirmed": "Ottimo {name}! Lo slot di {when} e' tuo. 🚗",
        "waitlist_declined": "Nessun problema, grazie per aver risposto!",
        "waitlist_unclear": "Rispondi SI se vuoi prendere questo slot, oppure NO se non ti interessa.",
        "waitlist_unavailable": "Purtroppo questo slot non e' piu' disponibile. Ti avviseremo se ne libera un altro.",
        "stopped": "Ok, non riceverai piu' messaggi da questo servizio. Se cambi idea, chiedi al tuo istruttore di riaggiungerti.",
        "cancel_hint": "Se vuoi cancellare la lezione scrivi ANNULLA. Scrivi MENU per le altre opzioni.",
    },
    "en": {
        "confirmed": "Great {name}, lesson confirmed for {when}! 🚗",
        "cancelled": "Lesson cancelled, no problem. Message your instructor if you want to rebook.",
        "no_upcoming": "You have no lessons scheduled right now.",
        "unrecognized": "I didn't understand that. Write MENU to see the options.",
        "not_registered": "Number not recognized. Contact your instructor to get registered.",
        "menu": "📋 DRIVEBOT\n\n1️⃣ My next lesson\n2️⃣ Cancel lesson\n3️⃣ Request a reschedule\n4️⃣ Help\n\nWrite ITALIANO to switch language.",
        "my_lessons_none": "You have no upcoming lessons.",
        "my_lessons_one": "Your next lesson: {when}.{location}",
        "reschedule_requested": "Got it! Your instructor has been notified.\n\nCurrent lesson:\n📅 {date}\n⏰ {time}\n\nThey'll propose a new time soon.",
        "reschedule_no_lesson": "You have no lesson to reschedule right now.",
        "help": "Reply YES or NO to confirm/cancel a lesson, or write MENU to see all options.",
        "lang_set": "Language set to English 🇬🇧",
        "waitlist_confirmed": "Great {name}! The {when} slot is yours. 🚗",
        "waitlist_declined": "No problem, thanks for letting us know!",
        "waitlist_unclear": "Reply YES if you want this slot, or NO if you're not interested.",
        "waitlist_unavailable": "Sorry, this slot is no longer available. We'll let you know if another one opens up.",
        "stopped": "Okay, you won't receive any more messages from this service. If you change your mind, ask your instructor to add you again.",
        "cancel_hint": "To cancel your lesson write CANCEL. Write MENU for the other options.",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in MESSAGES else "it"
    return MESSAGES[lang][key].format(**kwargs)


def _normalize_phone(raw: str) -> str:
    """Twilio sends numbers as 'whatsapp:+3933...' -- strip the prefix."""
    return raw.replace("whatsapp:", "").strip()


def _local(dt: datetime) -> datetime:
    """Convert a stored UTC datetime to Europe/Rome for display."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def _fmt_time(dt: datetime, lang: str = "it") -> str:
    joiner = "at" if lang == "en" else "alle"
    return _local(dt).strftime(f"%d/%m {joiner} %H:%M")


def _fmt_date_only(dt: datetime) -> str:
    return _local(dt).strftime("%d/%m")


def _fmt_time_only(dt: datetime) -> str:
    return _local(dt).strftime("%H:%M")


def _maps_link(location: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote(location)}"


def _fmt_location(lesson: Lesson) -> str:
    """For free-form messages -- includes a clickable Maps link."""
    if lesson.location:
        return f"\n📍 {lesson.location}\n{_maps_link(lesson.location)}"
    return ""


def _fmt_location_line(lesson: Lesson) -> str:
    """For template variables: plain text, never empty, no newlines."""
    return lesson.location or "da definire"


def _send_template(kind: str, phone: str, variables: dict) -> bool:
    text = TEMPLATE_TEXTS[kind]
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", " ".join(str(value).split()))
    return send_whatsapp_template(phone, TEMPLATE_SIDS[kind], variables, fallback_text=text)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _notify_instructor(session: Session, instructor_id: int, text: str) -> None:
    """
    Tell the instructor something happened. Never raises. Free-form text
    only works inside WhatsApp's 24h window, so if that fails we fall
    back to the approved 'instructor_notice' template (one variable, so
    the message is flattened to a single line).
    """
    instructor = session.get(Instructor, instructor_id)
    if instructor is None:
        return
    if send_whatsapp_message(instructor.phone, text):
        return
    flat = " | ".join(part.strip() for part in text.splitlines() if part.strip())
    _send_template("instructor_notice", instructor.phone, {"1": flat})


# ---------------------------------------------------------------------
# 1. Reminders (business-initiated -> must use templates)
# ---------------------------------------------------------------------

def _template_vars(student: Student, lesson: Lesson) -> dict:
    return {
        "1": student.name,
        "2": _fmt_date_only(lesson.start_time),
        "3": _fmt_time_only(lesson.start_time),
        "4": _fmt_location_line(lesson),
    }


def _process_lesson_reminders(session: Session, lesson: Lesson, now: datetime) -> None:
    time_until = _aware(lesson.start_time) - now
    student = session.get(Student, lesson.student_id)
    if student is None or not student.active:
        return

    # "Not sent yet AND now within the window" so a scheduler that was
    # down still catches up. A lesson is only marked as sent if the send
    # actually succeeded; a failed send is retried on the next run.
    if not lesson.reminder_24h_sent and timedelta(0) < time_until <= timedelta(hours=24):
        if _send_template("reminder_24h", student.phone, _template_vars(student, lesson)):
            lesson.reminder_24h_sent = True
            lesson.awaiting_reply = True
            if time_until <= timedelta(hours=2):
                lesson.reminder_2h_sent = True  # booked last-minute: one reminder is enough
            session.add(lesson)
            session.commit()

    elif not lesson.reminder_2h_sent and timedelta(0) < time_until <= timedelta(hours=2):
        if _send_template("reminder_2h", student.phone, _template_vars(student, lesson)):
            lesson.reminder_2h_sent = True
            session.add(lesson)
            session.commit()


def check_and_send_reminders(session: Session, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)

    try:
        expire_stale_offers(session, now)
    except Exception:
        session.rollback()
        log.exception("Failed while expiring stale waitlist offers")

    lessons = session.exec(
        select(Lesson).where(Lesson.status.in_(["scheduled", "confirmed"]))
    ).all()

    for lesson in lessons:
        try:
            _process_lesson_reminders(session, lesson, now)
        except Exception:
            # One broken lesson must never stop the others, and flags for
            # reminders already sent are committed one lesson at a time.
            session.rollback()
            log.exception("Reminder failed for lesson %s", lesson.id)


# ---------------------------------------------------------------------
# 2. Incoming replies (free-form -- within the student's own 24h window)
# ---------------------------------------------------------------------

def handle_incoming_message(session: Session, from_phone: str, body: str) -> str:
    phone = _normalize_phone(from_phone)
    text = body.strip().lower()

    student = session.exec(select(Student).where(Student.phone == phone)).first()
    is_active_student = student is not None and student.active

    instructor = session.exec(select(Instructor).where(Instructor.phone == phone)).first()
    if instructor is not None:
        reply = _handle_instructor_message(session, instructor, body, also_student=is_active_student)
        if reply is not None:
            return reply

    if not is_active_student:
        return t("it", "not_registered")

    lang = student.language

    if text in STOP_WORDS:
        student.active = False
        session.add(student)
        session.commit()
        _notify_instructor(session, student.instructor_id,
                           f"🚫 {student.name} ha chiesto di non ricevere piu' messaggi (STOP). E' stato rimosso dai promemoria.")
        return t(lang, "stopped")

    if text in ENGLISH_WORDS:
        student.language = "en"
        session.add(student)
        session.commit()
        return t("en", "lang_set")
    if text in ITALIAN_WORDS:
        student.language = "it"
        session.add(student)
        session.commit()
        return t("it", "lang_set")

    waitlist_entry = session.exec(
        select(WaitlistEntry).where(
            WaitlistEntry.student_id == student.id,
            WaitlistEntry.offered == True,  # noqa: E712
        )
    ).first()
    if waitlist_entry is not None:
        return _handle_waitlist_reply(session, waitlist_entry, student, text, lang)

    if text in MENU_WORDS:
        return t(lang, "menu")

    upcoming_lesson = session.exec(
        select(Lesson)
        .where(
            Lesson.student_id == student.id,
            Lesson.status.in_(["scheduled", "confirmed"]),
            Lesson.start_time > datetime.now(timezone.utc),
        )
        .order_by(Lesson.start_time)
    ).first()

    if text in MY_LESSONS_WORDS:
        if upcoming_lesson is None:
            return t(lang, "my_lessons_none")
        return t(lang, "my_lessons_one", when=_fmt_time(upcoming_lesson.start_time, lang), location=_fmt_location(upcoming_lesson))

    if text in RESCHEDULE_WORDS:
        if upcoming_lesson is None:
            return t(lang, "reschedule_no_lesson")
        date_str = _fmt_date_only(upcoming_lesson.start_time)
        time_str = _fmt_time_only(upcoming_lesson.start_time)
        upcoming_lesson.status = "reschedule_requested"
        upcoming_lesson.awaiting_reply = False
        session.add(upcoming_lesson)
        session.commit()
        _notify_instructor(
            session,
            upcoming_lesson.instructor_id,
            f"🔄 RICHIESTA DI RIPROGRAMMAZIONE\n\nStudente: {student.name}\n"
            f"Lezione attuale: {date_str} alle {time_str}\n\nContattalo per un nuovo orario.",
        )
        return t(lang, "reschedule_requested", date=date_str, time=time_str)

    if upcoming_lesson is None:
        return t(lang, "no_upcoming")

    if text in CONFIRM_WORDS:
        upcoming_lesson.status = "confirmed"
        upcoming_lesson.awaiting_reply = False
        session.add(upcoming_lesson)
        session.commit()
        _notify_instructor(
            session,
            upcoming_lesson.instructor_id,
            f"✅ {student.name} ha confermato la lezione del {_fmt_time(upcoming_lesson.start_time)}.",
        )
        return t(lang, "confirmed", name=student.name, when=_fmt_time(upcoming_lesson.start_time, lang))

    if text in CANCEL_WORDS:
        if text in AMBIGUOUS_CANCEL_WORDS and not upcoming_lesson.awaiting_reply:
            return t(lang, "cancel_hint")
        upcoming_lesson.status = "cancelled"
        upcoming_lesson.awaiting_reply = False
        session.add(upcoming_lesson)
        session.commit()
        _notify_instructor(
            session,
            upcoming_lesson.instructor_id,
            f"❌ {student.name} ha cancellato la lezione del {_fmt_time(upcoming_lesson.start_time)}.",
        )
        offer_next_waitlist(session, upcoming_lesson)
        return t(lang, "cancelled")

    return t(lang, "unrecognized")


def _handle_waitlist_reply(session: Session, entry: WaitlistEntry, student: Student, text: str, lang: str) -> str:
    lesson = session.get(Lesson, entry.offered_lesson_id) if entry.offered_lesson_id else None

    if text in CONFIRM_WORDS:
        # The slot may have been taken/changed in the meantime.
        if lesson is None or lesson.status != "cancelled":
            session.delete(entry)
            session.commit()
            return t(lang, "waitlist_unavailable")
        lesson.student_id = student.id
        lesson.status = "confirmed"
        lesson.reminder_24h_sent = False   # the new student needs their own reminders
        lesson.reminder_2h_sent = False
        lesson.awaiting_reply = False
        session.add(lesson)
        session.delete(entry)
        session.commit()
        _notify_instructor(
            session,
            lesson.instructor_id,
            f"🔁 {student.name} ha preso lo slot liberato del {_fmt_time(lesson.start_time)}.",
        )
        return t(lang, "waitlist_confirmed", name=student.name, when=_fmt_time(lesson.start_time, lang))

    if text in CANCEL_WORDS:
        session.delete(entry)
        session.commit()
        if lesson is not None and lesson.status == "cancelled":
            offer_next_waitlist(session, lesson)
        return t(lang, "waitlist_declined")

    return t(lang, "waitlist_unclear")


def mark_no_show(session: Session, lesson_id: int) -> None:
    lesson = session.get(Lesson, lesson_id)
    if lesson is not None:
        lesson.status = "no_show"
        session.add(lesson)
        session.commit()


# ---------------------------------------------------------------------
# 3. Waitlist auto-fill (business-initiated -> must use a template)
# ---------------------------------------------------------------------

def offer_next_waitlist(session: Session, cancelled_lesson: Lesson) -> bool:
    if _aware(cancelled_lesson.start_time) <= datetime.now(timezone.utc):
        return False  # lesson already started/passed, nothing to fill

    entries = session.exec(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.instructor_id == cancelled_lesson.instructor_id,
            WaitlistEntry.offered == False,  # noqa: E712
        )
        .order_by(WaitlistEntry.created_at)
    ).all()

    for entry in entries:
        student = session.get(Student, entry.student_id)
        if student is None or not student.active:
            session.delete(entry)
            session.commit()
            continue

        entry.offered = True
        entry.offered_lesson_id = cancelled_lesson.id
        entry.offered_at = datetime.now(timezone.utc)
        session.add(entry)
        session.commit()

        if _send_template("waitlist_offer", student.phone, _template_vars(student, cancelled_lesson)):
            return True

        # Send failed: undo the offer and try the next person.
        entry.offered = False
        entry.offered_lesson_id = None
        entry.offered_at = None
        session.add(entry)
        session.commit()

    return False


def expire_stale_offers(session: Session, now: datetime) -> None:
    """If an offered student doesn't answer in time, pass the slot on."""
    cutoff = now - timedelta(minutes=WAITLIST_OFFER_MINUTES)
    offered = session.exec(
        select(WaitlistEntry).where(WaitlistEntry.offered == True)  # noqa: E712
    ).all()
    for entry in offered:
        if entry.offered_at is None or _aware(entry.offered_at) > cutoff:
            continue
        lesson = session.get(Lesson, entry.offered_lesson_id) if entry.offered_lesson_id else None
        session.delete(entry)
        session.commit()
        if lesson is not None and lesson.status == "cancelled":
            offer_next_waitlist(session, lesson)


# ---------------------------------------------------------------------
# 4. Sending a reminder on demand (admin buttons, "now" / "in 2 minutes")
# ---------------------------------------------------------------------

def send_reminder_now(session: Session, lesson: Lesson) -> tuple[bool, str | None]:
    """Send the reminder immediately, ignoring the 24h window. Returns (ok, error_text)."""
    student = session.get(Student, lesson.student_id)
    if student is None or not student.active:
        return False, "This lesson has no active student."
    if _aware(lesson.start_time) <= datetime.now(timezone.utc):
        return False, "This lesson is already in the past."
    if _send_template("reminder_24h", student.phone, _template_vars(student, lesson)):
        lesson.reminder_24h_sent = True
        lesson.awaiting_reply = True
        session.add(lesson)
        session.commit()
        return True, None
    return False, _wa.last_error or "unknown error"


# ---------------------------------------------------------------------
# 5. Instructor commands over WhatsApp (add students without the website)
# ---------------------------------------------------------------------

INSTRUCTOR_HELP = (
    "Ciao {name}! Ecco cosa puoi scrivermi:\n\n"
    "➕ aggiungi Giulia +393331234567\n"
    "    (aggiungi \"inglese\" in fondo se preferisce l'inglese)\n"
    "👥 lista - i tuoi allievi\n"
    "➖ rimuovi Giulia - togli un allievo\n"
    "🔗 pagina - il tuo link privato per le lezioni\n\n"
    "Prima di aggiungere qualcuno, assicurati che sia d'accordo a ricevere i promemoria su WhatsApp."
)
ADD_FORMAT = "Non ho capito. Scrivi cosi': aggiungi Giulia +393331234567"


def _handle_instructor_message(session: Session, instructor: Instructor, body: str, also_student: bool) -> str | None:
    """
    Returns the reply text, or None to let the normal student flow handle the
    message (only when this person is ALSO a student and wrote something that
    isn't an instructor command -- e.g. an instructor testing with one phone).
    """
    text = body.strip()
    first, _, rest = text.partition(" ")
    cmd = first.lower().rstrip(":")
    rest = rest.strip()

    if cmd in ADD_WORDS:
        return _instructor_add_student(session, instructor, rest)
    if cmd in REMOVE_WORDS:
        return _instructor_remove_student(session, instructor, rest)
    if text.lower() in LIST_WORDS:
        return _instructor_list_students(session, instructor)
    if cmd in LINK_WORDS and not rest:
        return _instructor_link(session, instructor)
    if text.lower() in {"comandi", "istruttore", "commands"}:
        return INSTRUCTOR_HELP.format(name=instructor.name)
    if also_student:
        return None
    return INSTRUCTOR_HELP.format(name=instructor.name)


def _instructor_add_student(session: Session, instructor: Instructor, rest: str) -> str:
    parts = rest.split()
    lang = "it"
    if parts and parts[-1].lower() in ("en", "inglese", "english"):
        lang, parts = "en", parts[:-1]
    elif parts and parts[-1].lower() in ("it", "italiano", "italian"):
        parts = parts[:-1]
    cleaned = " ".join(parts)

    match = re.search(r"(\+?\d[\d\s\-\.]{6,}\d)$", cleaned)
    if not match:
        return ADD_FORMAT
    name = cleaned[:match.start()].strip(" ,:;-")
    if not name or len(name) > 60:
        return ADD_FORMAT
    try:
        phone = _norm_phone(match.group(1))
    except ValueError:
        return "Il numero non sembra valido. Scrivilo con il prefisso, ad esempio +393331234567."

    existing = session.exec(select(Student).where(Student.phone == phone)).first()
    if existing is not None:
        if existing.instructor_id != instructor.id:
            return f"Il numero {phone} risulta gia' registrato con un altro istruttore."
        if existing.active:
            return f"{existing.name} e' gia' nella tua lista."
        existing.active = True
        existing.name = name
        existing.language = lang
        session.add(existing)
        session.commit()
    else:
        session.add(Student(name=name, phone=phone, instructor_id=instructor.id, language=lang))
        session.commit()

    welcomed = _send_template("student_welcome", phone, {"1": name, "2": instructor.name})
    if welcomed:
        return f"✅ {name} aggiunto/a ({phone}). Ho inviato un messaggio di benvenuto."
    return (f"✅ {name} aggiunto/a ({phone}), ma non sono riuscito a inviare il messaggio di benvenuto. "
            f"Chiedi a {name} di scrivere \"ciao\" a questo numero.")


def _instructor_remove_student(session: Session, instructor: Instructor, rest: str) -> str:
    if not rest:
        return "Scrivi: rimuovi Giulia (oppure rimuovi +393331234567)"
    mine = session.exec(
        select(Student).where(Student.instructor_id == instructor.id, Student.active == True)  # noqa: E712
    ).all()
    try:
        wanted_phone = _norm_phone(rest)
    except ValueError:
        wanted_phone = None
    matches = [s for s in mine if s.phone == wanted_phone] if wanted_phone else \
              [s for s in mine if s.name.strip().lower() == rest.strip().lower()]
    if not matches:
        return f"Non trovo nessun allievo attivo chiamato \"{rest}\". Scrivi LISTA per vedere i tuoi allievi."
    if len(matches) > 1:
        return "Ci sono piu' allievi con questo nome: usa il numero, ad esempio rimuovi +393331234567."
    student = matches[0]
    student.active = False
    session.add(student)
    session.commit()
    return f"✅ {student.name} rimosso/a. Non ricevera' piu' messaggi."


def _instructor_list_students(session: Session, instructor: Instructor) -> str:
    mine = session.exec(
        select(Student).where(Student.instructor_id == instructor.id, Student.active == True)  # noqa: E712
        .order_by(Student.name)
    ).all()
    if not mine:
        return "Non hai ancora allievi. Scrivi: aggiungi Giulia +393331234567"
    lines = [f"• {s.name} {s.phone}" for s in mine[:40]]
    extra = f"\n... e altri {len(mine) - 40}" if len(mine) > 40 else ""
    return f"👥 I tuoi allievi ({len(mine)}):\n" + "\n".join(lines) + extra


def _instructor_link(session: Session, instructor: Instructor) -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        return "Il link non e' ancora disponibile. Chiedi a chi ti ha attivato il servizio."
    if not instructor.access_token:
        instructor.access_token = secrets.token_urlsafe(16)
        session.add(instructor)
        session.commit()
    return f"🔗 La tua pagina privata (non condividerla con nessuno):\n{base}/i/{instructor.access_token}/"
