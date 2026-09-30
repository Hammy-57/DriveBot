"""Tests for the instructor portal, admin extras, and the no-silent-failure fix."""
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import admin
import portal
import whatsapp
from models import Instructor, Lesson, Student, WaitlistEntry


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=__import__("sqlalchemy").pool.StaticPool)
    SQLModel.metadata.create_all(engine)
    factory = lambda: Session(engine)
    monkeypatch.setattr(admin, "get_session", factory)
    monkeypatch.setattr(portal, "get_session", factory)

    with Session(engine) as s:
        ta, tb = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
        a = Instructor(name="Anna", phone="+390000000001", access_token=ta)
        b = Instructor(name="Bruno", phone="+390000000002", access_token=tb)
        s.add(a); s.add(b); s.commit(); s.refresh(a); s.refresh(b)
        sa = Student(name="AlunnoDiAnna", phone="+390000000011", instructor_id=a.id)
        sb = Student(name="AlunnoDiBruno", phone="+390000000012", instructor_id=b.id)
        s.add(sa); s.add(sb); s.commit(); s.refresh(sa); s.refresh(sb)
        la = Lesson(instructor_id=a.id, student_id=sa.id, start_time=datetime.now(timezone.utc) + timedelta(hours=30))
        lb = Lesson(instructor_id=b.id, student_id=sb.id, start_time=datetime.now(timezone.utc) + timedelta(hours=30))
        s.add(la); s.add(lb); s.commit(); s.refresh(la); s.refresh(lb)
        ids = dict(a=a.id, b=b.id, sa=sa.id, sb=sb.id, la=la.id, lb=lb.id, ta=ta, tb=tb)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(admin.router)
    app.include_router(portal.router)
    return TestClient(app, follow_redirects=False), engine, ids


def test_portal_shows_only_own_data(env):
    client, _, ids = env
    page = client.get(f"/i/{ids['ta']}/").text
    assert "AlunnoDiAnna" in page and "AlunnoDiBruno" not in page


def test_bad_or_short_token_is_404(env):
    client, _, ids = env
    assert client.get("/i/wrong-token-abcdefghijklmnop/").status_code == 404
    assert client.get("/i/short/").status_code == 404


def test_cannot_cancel_or_touch_another_instructors_data(env):
    client, engine, ids = env
    t = ids["ta"]  # Anna's link
    assert client.post(f"/i/{t}/lesson/{ids['lb']}/cancel").status_code == 404
    assert client.post(f"/i/{t}/student/{ids['sb']}/deactivate").status_code == 404
    r = client.post(f"/i/{t}/lessons", data={"student_id": ids["sb"], "when": "2099-01-01T10:00"})
    assert r.status_code == 404
    with Session(engine) as s:
        assert s.get(Lesson, ids["lb"]).status == "scheduled"
        assert s.get(Student, ids["sb"]).active is True


def test_instructor_can_add_and_cancel_own(env):
    client, engine, ids = env
    t = ids["ta"]
    assert client.post(f"/i/{t}/students", data={"name": "Nuovo", "phone": "333 999 8888"}).status_code == 303
    assert client.post(f"/i/{t}/lesson/{ids['la']}/cancel").status_code == 303
    with Session(engine) as s:
        assert s.exec(select(Student).where(Student.phone == "+393339998888")).first() is not None
        assert s.get(Lesson, ids["la"]).status == "cancelled"


def test_html_in_names_is_escaped_in_portal(env):
    client, _, ids = env
    client.post(f"/i/{ids['ta']}/students", data={"name": "<script>x</script>", "phone": "+390000000055"})
    assert "<script>x</script>" not in client.get(f"/i/{ids['ta']}/").text


def test_reset_link_kills_old_link(env):
    client, engine, ids = env
    r = client.post(f"/admin/instructor/{ids['a']}/reset-link", auth=("admin", "admin"))
    assert r.status_code == 303
    assert client.get(f"/i/{ids['ta']}/").status_code == 404


def test_portal_link_visible_in_admin_only_with_login(env):
    client, _, ids = env
    assert client.get(f"/admin/instructor/{ids['a']}").status_code == 401
    page = client.get(f"/admin/instructor/{ids['a']}", auth=("admin", "admin")).text
    assert f"/i/{ids['ta']}/" in page and ids["tb"] not in page


def test_admin_test_message_and_resend(env):
    client, engine, ids = env
    r = client.post("/admin/test-message", data={"phone": "+393330000001"}, auth=("admin", "admin"))
    assert r.status_code == 200 and "Sent to Twilio" in r.text
    r = client.post(f"/admin/lesson/{ids['la']}/resend", auth=("admin", "admin"))
    assert "Reminder sent" in r.text
    with Session(engine) as s:
        assert s.get(Lesson, ids["la"]).reminder_24h_sent is True


def test_deployed_without_credentials_fails_instead_of_faking(monkeypatch):
    monkeypatch.setattr(whatsapp, "_client", None)
    monkeypatch.setattr(whatsapp, "DEPLOYED", True)
    assert whatsapp.send_whatsapp_message("+390000000001", "hi") is False
    assert "not configured" in whatsapp.last_error
    assert whatsapp.send_whatsapp_template("+390000000001", "HXabc", {"1": "x"}, fallback_text="x") is False


def test_old_database_is_migrated_and_gets_tokens(tmp_path, monkeypatch):
    import sqlite3
    import db
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE instructor (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, phone VARCHAR NOT NULL)")
    con.execute("CREATE TABLE waitlistentry (id INTEGER PRIMARY KEY, instructor_id INT, student_id INT, created_at DATETIME, offered BOOLEAN, offered_lesson_id INT)")
    con.execute("INSERT INTO instructor (name, phone) VALUES ('Old', '+390000000099')")
    con.commit(); con.close()
    eng = create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "DATABASE_URL", f"sqlite:///{path}")
    db.init_db()
    with Session(eng) as s:
        inst = s.exec(select(Instructor)).first()
        assert inst.access_token and len(inst.access_token) >= 16
