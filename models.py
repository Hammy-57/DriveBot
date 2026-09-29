"""
Data models for the driving-instructor WhatsApp bot.

Kept intentionally simple: four tables is all the MVP needs.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Instructor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str  # WhatsApp number, e.g. "+393331234567"


class Student(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str  # WhatsApp number
    instructor_id: int = Field(foreign_key="instructor.id")
    language: str = Field(default="it")  # "it" or "en" -- student can switch anytime
    active: bool = Field(default=True)  # set False when they finish, instead of deleting history


class Lesson(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    instructor_id: int = Field(foreign_key="instructor.id")
    student_id: int = Field(foreign_key="student.id")
    start_time: datetime
    location: Optional[str] = Field(default=None)  # e.g. "Via Roma 25, Cassino"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # scheduled -> confirmed -> completed
    #           -> cancelled (triggers waitlist offer)
    #           -> reschedule_requested (student asked to move it)
    #           -> no_show
    status: str = Field(default="scheduled")

    reminder_24h_sent: bool = Field(default=False)
    reminder_2h_sent: bool = Field(default=False)

    # set when a reminder is sent and we're waiting for a YES/NO reply
    awaiting_reply: bool = Field(default=False)


class WaitlistEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    instructor_id: int = Field(foreign_key="instructor.id")
    student_id: int = Field(foreign_key="student.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # set to True once we've offered this person a freed slot
    # and are waiting to hear back
    offered: bool = Field(default=False)
    offered_lesson_id: Optional[int] = Field(default=None)
    offered_at: Optional[datetime] = Field(default=None)  # when the offer was sent (for timeout)
