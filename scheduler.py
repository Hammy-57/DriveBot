"""
Runs check_and_send_reminders() every 5 minutes in the background,
so you don't have to trigger it manually once this is deployed.
"""
from apscheduler.schedulers.background import BackgroundScheduler

from bot_logic import check_and_send_reminders
from db import get_session

_scheduler = BackgroundScheduler()


def _job():
    with get_session() as session:
        check_and_send_reminders(session)


def start_scheduler():
    if not _scheduler.running:
        _scheduler.add_job(_job, "interval", minutes=5)
        _scheduler.start()
