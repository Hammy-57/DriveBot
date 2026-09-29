"""
Run this once to populate the database with fake data so you can test
the bot end-to-end before you have real instructors.

    python seed.py
"""
from datetime import datetime, timedelta, timezone

from db import get_session, init_db
from models import Instructor, Lesson, Student, WaitlistEntry

init_db()

with get_session() as session:
    marco = Instructor(name="Marco Rossi", phone="+390000000001")
    session.add(marco)
    session.commit()
    session.refresh(marco)

    giulia = Student(name="Giulia", phone="+390000000002", instructor_id=marco.id)
    luca = Student(name="Luca", phone="+390000000003", instructor_id=marco.id)
    session.add(giulia)
    session.add(luca)
    session.commit()
    session.refresh(giulia)
    session.refresh(luca)

    # A lesson happening in ~24 hours -- will trigger the 24h reminder
    lesson = Lesson(
        instructor_id=marco.id,
        student_id=giulia.id,
        start_time=datetime.now(timezone.utc) + timedelta(hours=24),
        location="Via Roma 25, Cassino",
    )
    session.add(lesson)

    # Luca is on the waitlist for a freed-up slot
    waitlist_entry = WaitlistEntry(instructor_id=marco.id, student_id=luca.id)
    session.add(waitlist_entry)

    session.commit()

print("Seed data created: 1 instructor, 2 students, 1 lesson, 1 waitlist entry.")
