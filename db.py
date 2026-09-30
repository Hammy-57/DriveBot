"""
SQLite by default. On a host with a persistent volume set, e.g.
    DATABASE_URL=sqlite:////data/drivebot.db
so the data survives redeploys.
"""
import os
import secrets

from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

from models import Instructor

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///drivebot.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate()


def _migrate() -> None:
    """Tiny migration: add columns introduced after a DB file already existed."""
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(waitlistentry)"))]
            if cols and "offered_at" not in cols:
                conn.execute(text("ALTER TABLE waitlistentry ADD COLUMN offered_at DATETIME"))
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(instructor)"))]
            if cols and "access_token" not in cols:
                conn.execute(text("ALTER TABLE instructor ADD COLUMN access_token VARCHAR"))

    # Every instructor needs a private-link token.
    with Session(engine) as s:
        for inst in s.exec(select(Instructor).where(Instructor.access_token == None)).all():  # noqa: E711
            inst.access_token = secrets.token_urlsafe(16)
            s.add(inst)
        s.commit()


def get_session() -> Session:
    return Session(engine)
