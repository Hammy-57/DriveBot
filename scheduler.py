"""
Runs check_and_send_reminders() every 5 minutes in the background,
so you don't have to trigger it manually once this is deployed.
Also runs one-off "send this reminder in 2 minutes" jobs.
"""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from bot_logic import check_and_send_reminders, send_reminder_now
from db import get_session
from models import Lesson

_scheduler = BackgroundScheduler()


def _job():
    with get_session() as session:
        check_and_send_reminders(session)


def _send_one(lesson_id: int):
    with get_session() as session:
        lesson = session.get(Lesson, lesson_id)
        if lesson is not None and lesson.status in ("scheduled", "confirmed"):
            send_reminder_now(session, lesson)


def schedule_reminder(lesson_id: int, delay_seconds: int = 120) -> datetime:
    """Send this lesson's reminder once, after a short delay. Lost if the server restarts before then."""
    run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    _scheduler.add_job(_send_one, "date", run_date=run_at, args=[lesson_id],
                       id=f"remind-{lesson_id}-{int(run_at.timestamp())}", misfire_grace_time=300)
    return run_at


def start_scheduler():
    if not _scheduler.running:
        _scheduler.add_job(_job, "interval", minutes=5)
        _scheduler.start()
