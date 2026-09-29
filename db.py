"""
SQLite by default. On a host with a persistent volume set, e.g.
    DATABASE_URL=sqlite:////data/drivebot.db
so the data survives redeploys.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///drivebot.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate()


def _migrate() -> None:
    """Tiny migration: add columns introduced after a DB file already existed."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(waitlistentry)"))]
        if cols and "offered_at" not in cols:
            conn.execute(text("ALTER TABLE waitlistentry ADD COLUMN offered_at DATETIME"))


def get_session() -> Session:
    return Session(engine)
