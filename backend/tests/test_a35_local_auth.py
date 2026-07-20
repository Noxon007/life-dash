"""Tests für 0.29.0: A35 — lokale Konten (E-Mail + Passwort).

Schwerpunkt sind die drei zugesagten Sicherheitseigenschaften: modernes
Hashing, keine Enumeration über die Antwort, Sperre gegen Passwort-Raten.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth
from app.config import settings
from app.models import User, UserRole
from app.routers.admin import create_user
from app.routers.auth import (auth_config, local_change_password, local_login,
                              local_register)
from app.schemas import (AdminCreateUser, LocalLogin, LocalRegister,
                         PasswordChange)
from app.services import password as pw


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "local")
    # Sperr-Zustand zwischen Tests zurücksetzen (Modul-global)
    auth._fail_state.clear()
    # adopt_orphan_rows läuft gegen die ECHTE Engine (Alt-Daten-Adoption beim
    # ersten Nutzer). In Tests neutralisieren — sonst fasst das Anlegen des
    # ersten lokalen Kontos die produktive DB an (CLAUDE.md: nie anfassen).
    monkeypatch.setattr(auth, "adopt_orphan_rows", lambda *a, **k: 0)


# --------------------------------------------------------------------------- #
# Passwort-Hashing
# --------------------------------------------------------------------------- #
def test_hash_is_salted_and_verifiable():
    h1 = pw.hash_password("geheimes-passwort")
    h2 = pw.hash_password("geheimes-passwort")
    assert h1 != h2                        # zufälliger Salt -> nie gleich
    assert h1.startswith("scrypt$")
    assert pw.verify_password("geheimes-passwort", h1)
    assert pw.verify_password("geheimes-passwort", h2)
    assert not pw.verify_password("falsch", h1)


def test_plaintext_is_never_stored():
    h = pw.hash_password("KlartextTaucht!Nicht#Auf")
    assert "KlartextTaucht" not in h


def test_verify_tolerates_broken_hashes():
    for bad in (None, "", "kein-format", "bcrypt$x$y", "scrypt$only$three"):
        assert pw.verify_password("x", bad) is False


# --------------------------------------------------------------------------- #
# Registrierung: erster Nutzer wird Admin, danach zu
# --------------------------------------------------------------------------- #
def test_first_registration_becomes_admin(db):
    resp = local_register(LocalRegister(email="chef@example.org",
                                        password="ordentlich-lang"), db=db)
    assert resp.status_code == 200
    user = db.query(User).one()
    assert user.role == UserRole.admin
    assert user.password_hash and user.password_hash.startswith("scrypt$")
    # Session-Cookie gesetzt
    assert auth.SESSION_COOKIE in resp.headers.get("set-cookie", "")


def test_registration_closes_after_first_user(db):
    local_register(LocalRegister(email="chef@example.org", password="ordentlich-lang"), db=db)
    with pytest.raises(HTTPException) as exc:
        local_register(LocalRegister(email="zweiter@example.org",
                                     password="ordentlich-lang"), db=db)
    assert exc.value.status_code == 403


def test_registration_needs_an_at_sign(db):
    with pytest.raises(HTTPException) as exc:
        local_register(LocalRegister(email="keinemail", password="ordentlich-lang"), db=db)
    assert exc.value.status_code == 400


def test_config_signals_setup_when_empty(db):
    assert auth_config(db=db).needs_setup is True
    local_register(LocalRegister(email="a@example.org", password="ordentlich-lang"), db=db)
    assert auth_config(db=db).needs_setup is False


# --------------------------------------------------------------------------- #
# Login: kein Aufschluss, welche Angabe falsch war
# --------------------------------------------------------------------------- #
def _register(db, email="chef@example.org", pw_="ordentlich-lang"):
    local_register(LocalRegister(email=email, password=pw_), db=db)


def test_login_succeeds_with_correct_credentials(db):
    _register(db)
    resp = local_login(LocalLogin(email="chef@example.org",
                                  password="ordentlich-lang"), db=db)
    assert resp.status_code == 200
    assert auth.SESSION_COOKIE in resp.headers.get("set-cookie", "")


def test_unknown_email_and_wrong_password_give_the_same_error(db):
    _register(db)
    errors = []
    for email, pwd in (("chef@example.org", "falsch"),
                       ("niemand@example.org", "irgendwas")):
        with pytest.raises(HTTPException) as exc:
            local_login(LocalLogin(email=email, password=pwd), db=db)
        errors.append((exc.value.status_code, exc.value.detail))
    assert errors[0] == errors[1]          # ununterscheidbar
    assert errors[0][0] == 401


def test_login_is_case_insensitive_on_email(db):
    _register(db, email="Chef@Example.org")
    resp = local_login(LocalLogin(email="chef@example.ORG",
                                  password="ordentlich-lang"), db=db)
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Sperre gegen Passwort-Raten
# --------------------------------------------------------------------------- #
def test_repeated_failures_lock_the_account(db):
    _register(db)
    for _ in range(5):
        with pytest.raises(HTTPException) as exc:
            local_login(LocalLogin(email="chef@example.org", password="falsch"), db=db)
        assert exc.value.status_code == 401
    # Sechster Versuch — jetzt gesperrt, auch mit RICHTIGEM Passwort
    with pytest.raises(HTTPException) as exc:
        local_login(LocalLogin(email="chef@example.org",
                               password="ordentlich-lang"), db=db)
    assert exc.value.status_code == 429


def test_success_resets_the_failure_counter(db):
    _register(db)
    for _ in range(4):        # eine unter dem Limit
        with pytest.raises(HTTPException):
            local_login(LocalLogin(email="chef@example.org", password="falsch"), db=db)
    local_login(LocalLogin(email="chef@example.org", password="ordentlich-lang"), db=db)
    # Zähler zurück -> vier weitere Fehlversuche sperren noch nicht
    for _ in range(4):
        with pytest.raises(HTTPException) as exc:
            local_login(LocalLogin(email="chef@example.org", password="falsch"), db=db)
        assert exc.value.status_code == 401


# --------------------------------------------------------------------------- #
# Passwort ändern
# --------------------------------------------------------------------------- #
def test_change_password(db):
    _register(db)
    user = db.query(User).one()
    local_change_password(PasswordChange(current_password="ordentlich-lang",
                                         new_password="ein-neues-langes"), db=db, user=user)
    assert not pw.verify_password("ordentlich-lang", user.password_hash)
    assert pw.verify_password("ein-neues-langes", user.password_hash)


def test_change_password_needs_the_current_one(db):
    _register(db)
    user = db.query(User).one()
    with pytest.raises(HTTPException) as exc:
        local_change_password(PasswordChange(current_password="falsch",
                                             new_password="ein-neues-langes"),
                              db=db, user=user)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Admin legt weitere Konten an
# --------------------------------------------------------------------------- #
def test_admin_creates_a_second_account(db, user):
    """`user` (Fixture) ist Admin. Er legt ein normales Konto an."""
    create_user(AdminCreateUser(email="kollege@example.org",
                                password="langes-passwort"),
                admin=user, db=db)
    created = auth.find_local_user(db, "kollege@example.org")
    assert created is not None
    assert created.role == UserRole.user
    # Und dieses Konto kann sich anmelden
    resp = local_login(LocalLogin(email="kollege@example.org",
                                  password="langes-passwort"), db=db)
    assert resp.status_code == 200


def test_admin_cannot_create_duplicate_email(db, user):
    create_user(AdminCreateUser(email="k@example.org", password="langes-passwort"),
                admin=user, db=db)
    with pytest.raises(HTTPException) as exc:
        create_user(AdminCreateUser(email="k@example.org", password="langes-passwort"),
                    admin=user, db=db)
    assert exc.value.status_code == 409


def test_local_endpoints_refuse_outside_local_mode(db, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    with pytest.raises(HTTPException) as exc:
        local_login(LocalLogin(email="a@example.org", password="x"), db=db)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Routing-Ebene: fängt den Fehler, den der direkte Funktionsaufruf NICHT sieht.
# Beim Admin-Anlage-Endpunkt fehlte der Import des Body-Schemas; wegen
# `from __future__ import annotations` blieb das Modell ein unauflösbarer
# String, und FastAPI degradierte `payload` zu einem Query-Parameter (422).
# Ein TestClient wäre der direktere Test, fasst über den Lifespan aber die
# echte DB an — deshalb hier DB-frei über das OpenAPI-Schema, das FastAPI
# zwingt, alle Body-Annotationen aufzulösen.
# --------------------------------------------------------------------------- #
def test_admin_create_user_has_a_json_body_not_a_query_param():
    from app.main import app

    op = app.openapi()["paths"]["/api/admin/users"]["post"]
    assert "requestBody" in op, "payload wurde nicht als Body erkannt (Import fehlt?)"
    ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("AdminCreateUser")
    # Und NICHT als Query-Parameter gelandet:
    assert "payload" not in {p.get("name") for p in op.get("parameters", [])}
