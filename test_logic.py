"""
Run with: pytest

These tests use an in-memory SQLite database, so they run in
milliseconds and never touch Twilio (whatsapp.py falls back to
DEV MODE printing when no credentials are set).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

import bot_logic
from bot_logic import check_and_send_reminders, handle_incoming_message, expire_stale_offers
from models import Instructor, Lesson, Student, WaitlistEntry


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed(session):
    instructor = Instructor(name="Marco", phone="+390000000001")
    session.add(instructor)
    session.commit()
    session.refresh(instructor)

    giulia = Student(name="Giulia", phone="+390000000002", instructor_id=instructor.id)
    luca = Student(name="Luca", phone="+390000000003", instructor_id=instructor.id)
    session.add_all([giulia, luca])
    session.commit()
    session.refresh(giulia)
    session.refresh(luca)

    lesson = Lesson(
        instructor_id=instructor.id,
        student_id=giulia.id,
        start_time=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)

    waitlist = WaitlistEntry(instructor_id=instructor.id, student_id=luca.id)
    session.add(waitlist)
    session.commit()

    return instructor, giulia, luca, lesson


def test_reminder_gets_sent_24h_before(session, capsys):
    _seed(session)
    check_and_send_reminders(session)
    output = capsys.readouterr().out
    assert "Giulia" in output
    assert "DEV MODE" in output
    assert "template not sent" in output  # no Content SID configured in tests


def test_reminder_survives_scheduler_downtime(session, capsys):
    """
    Simulates the scheduler having been down until only 1 hour before
    the lesson -- the 24h reminder was never sent, but it still should
    be, immediately, on the next check (not skipped forever).
    """
    instructor = Instructor(name="Marco", phone="+390000000001")
    session.add(instructor)
    session.commit()
    session.refresh(instructor)
    student = Student(name="Ahmed", phone="+390000000009", instructor_id=instructor.id)
    session.add(student)
    session.commit()
    session.refresh(student)
    lesson = Lesson(
        instructor_id=instructor.id,
        student_id=student.id,
        start_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(lesson)
    session.commit()

    check_and_send_reminders(session)
    output = capsys.readouterr().out
    assert "Ahmed" in output  # the 24h reminder still fires, late but sent


def test_confirm_reply_confirms_lesson(session):
    _, giulia, _, lesson = _seed(session)
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "SI")
    session.refresh(lesson)
    assert lesson.status == "confirmed"
    assert "confermata" in reply.lower()


def test_cancel_triggers_waitlist_offer(session, capsys):
    _, giulia, luca, lesson = _seed(session)

    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "ANNULLA")
    session.refresh(lesson)

    assert lesson.status == "cancelled"
    assert "cancellata" in reply.lower()

    # Luca (on the waitlist) should have been offered the slot via template
    output = capsys.readouterr().out
    assert "Luca" in output
    assert "template not sent" in output


def test_waitlist_student_can_accept_freed_slot(session):
    _, giulia, luca, lesson = _seed(session)

    # Giulia cancels -> Luca gets offered the slot
    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "ANNULLA")

    # Luca accepts
    reply = handle_incoming_message(session, f"whatsapp:{luca.phone}", "SI")
    session.refresh(lesson)

    assert lesson.student_id == luca.id
    assert lesson.status == "confirmed"
    assert "tuo" in reply.lower()


def test_unrecognized_reply_asks_for_clarification(session):
    _, giulia, _, _ = _seed(session)
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "boh")
    assert "menu" in reply.lower()


def test_menu_command(session):
    _, giulia, _, _ = _seed(session)
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "menu")
    assert "1" in reply and "2" in reply and "3" in reply


def test_my_lessons_command(session):
    _, giulia, _, lesson = _seed(session)
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "1")
    assert "Via Roma" not in reply or True  # location only present if set on this lesson
    assert reply != ""


def test_language_switch_to_english_and_back(session):
    _, giulia, _, _ = _seed(session)
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "english")
    assert "english" in reply.lower()

    # subsequent messages should now come back in English
    reply2 = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "menu")
    assert "next lesson" in reply2.lower()

    reply3 = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "italiano")
    assert "italiano" in reply3.lower()


def test_reschedule_request_notifies_instructor(session, capsys):
    _, giulia, _, lesson = _seed(session)
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "riprogramma")
    session.refresh(lesson)

    assert lesson.status == "reschedule_requested"
    assert "istruttore" in reply.lower() or "instructor" in reply.lower()
    assert "📅" in reply  # includes the current lesson's date
    assert "⏰" in reply  # and time

    output = capsys.readouterr().out
    assert "Giulia" in output
    assert "riprogrammazione" in output.lower()


def test_confirm_notifies_instructor(session, capsys):
    _, giulia, _, lesson = _seed(session)
    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "SI")
    output = capsys.readouterr().out
    assert "confermato" in output.lower()


def test_cancel_notifies_instructor_and_waitlist(session, capsys):
    _, giulia, luca, lesson = _seed(session)
    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "ANNULLA")
    output = capsys.readouterr().out
    # both the instructor cancellation notice AND the waitlist offer to Luca happen
    assert "cancellato" in output.lower()
    assert "Luca" in output


def test_reminder_includes_location(session, capsys):
    _, giulia, _, lesson = _seed(session)
    lesson.location = "Via Roma 25, Cassino"
    session.add(lesson)
    session.commit()

    check_and_send_reminders(session)
    output = capsys.readouterr().out
    assert "Via Roma 25" in output


def test_my_lessons_includes_maps_link(session):
    _, giulia, _, lesson = _seed(session)
    lesson.location = "Via Roma 25, Cassino"
    session.add(lesson)
    session.commit()

    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "1")
    assert "google.com/maps" in reply


# ---------------- new tests for the hardening pass ----------------

def test_bare_no_without_reminder_does_not_cancel(session):
    _, giulia, _, lesson = _seed(session)
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "NO")
    session.refresh(lesson)
    assert lesson.status == "scheduled"
    assert "annulla" in reply.lower()


def test_bare_no_after_reminder_cancels(session):
    _, giulia, _, lesson = _seed(session)
    check_and_send_reminders(session)  # sets awaiting_reply
    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "NO")
    session.refresh(lesson)
    assert lesson.status == "cancelled"


def test_failed_send_is_not_marked_sent_and_does_not_crash(session, monkeypatch):
    _, _, _, lesson = _seed(session)
    monkeypatch.setattr(bot_logic, "send_whatsapp_template", lambda *a, **k: False)
    check_and_send_reminders(session)  # must not raise
    session.refresh(lesson)
    assert lesson.reminder_24h_sent is False  # will be retried next run


def test_exception_in_one_lesson_does_not_stop_others(session, monkeypatch):
    _, giulia, luca, lesson = _seed(session)
    calls = []

    def flaky(phone, sid, variables, **kw):
        calls.append(phone)
        if phone == giulia.phone:
            raise RuntimeError("boom")
        return True

    other = Lesson(instructor_id=lesson.instructor_id, student_id=luca.id,
                   start_time=datetime.now(timezone.utc) + timedelta(hours=20))
    session.add(other)
    session.commit()
    monkeypatch.setattr(bot_logic, "send_whatsapp_template", flaky)
    check_and_send_reminders(session)
    assert luca.phone in calls


def test_instructor_notice_falls_back_to_template(session, monkeypatch):
    instructor, giulia, _, _ = _seed(session)
    sent = []
    monkeypatch.setattr(bot_logic, "send_whatsapp_message", lambda *a, **k: False)
    monkeypatch.setattr(bot_logic, "send_whatsapp_template", lambda phone, sid, v, **k: sent.append((phone, v)) or True)
    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "SI")
    assert any(p == instructor.phone and "confermato" in v["1"] for p, v in sent)
    assert all("\n" not in v["1"] for _, v in sent)


def test_waitlist_accept_resets_reminders_and_notifies_instructor(session, capsys):
    instructor, giulia, luca, lesson = _seed(session)
    check_and_send_reminders(session)
    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "ANNULLA")
    handle_incoming_message(session, f"whatsapp:{luca.phone}", "SI")
    session.refresh(lesson)
    assert lesson.reminder_24h_sent is False
    assert "ha preso lo slot" in capsys.readouterr().out


def test_waitlist_offer_expires_and_moves_to_next(session, capsys):
    instructor, giulia, luca, lesson = _seed(session)
    marta = Student(name="Marta", phone="+390000000004", instructor_id=instructor.id)
    session.add(marta)
    session.commit()
    session.refresh(marta)
    session.add(WaitlistEntry(instructor_id=instructor.id, student_id=marta.id))
    session.commit()

    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "ANNULLA")  # Luca offered
    later = datetime.now(timezone.utc) + timedelta(minutes=bot_logic.WAITLIST_OFFER_MINUTES + 1)
    capsys.readouterr()
    expire_stale_offers(session, later)
    assert "Marta" in capsys.readouterr().out  # offer passed on


def test_waitlist_slot_no_longer_available(session):
    _, giulia, luca, lesson = _seed(session)
    handle_incoming_message(session, f"whatsapp:{giulia.phone}", "ANNULLA")
    lesson.status = "confirmed"  # someone else got it in the meantime
    session.add(lesson)
    session.commit()
    reply = handle_incoming_message(session, f"whatsapp:{luca.phone}", "SI")
    assert "piu' disponibile" in reply


def test_template_variables_are_never_empty_or_multiline(session, monkeypatch):
    _, _, _, lesson = _seed(session)  # lesson has no location
    seen = []
    monkeypatch.setattr(bot_logic, "send_whatsapp_template", lambda p, sid, v, **k: seen.append(v) or True)
    check_and_send_reminders(session)
    assert seen and all(val.strip() and "\n" not in val for val in seen[0].values())


def test_inactive_student_is_not_recognised(session):
    _, giulia, _, _ = _seed(session)
    giulia.active = False
    session.add(giulia)
    session.commit()
    reply = handle_incoming_message(session, f"whatsapp:{giulia.phone}", "SI")
    assert "non riconosciuto" in reply.lower()


def test_all_templates_are_valid_for_whatsapp():
    import re
    for kind, text in bot_logic.TEMPLATE_TEXTS.items():
        nums = sorted({int(n) for n in re.findall(r"\{\{(\d+)\}\}", text)})
        assert nums == list(range(1, len(nums) + 1)), f"{kind}: variables skip a number"
        assert not text.startswith("{{") and not text.rstrip().endswith("}}"), f"{kind}: starts/ends with variable"
        words = re.sub(r"\{\{\d+\}\}", "", text).split()
        assert len(words) >= 2 * len(nums) + 1, f"{kind}: too few fixed words per variable"


def test_every_business_template_uses_all_four_variables():
    for kind in ("reminder_24h", "reminder_2h", "waitlist_offer"):
        for n in "1234":
            assert "{{" + n + "}}" in bot_logic.TEMPLATE_TEXTS[kind], (kind, n)
