"""Anmerkung 200 — drei Befunde einer Sicherheits-Durchsicht.

Alle drei sind still: keiner hätte je eine Beschwerde erzeugt, und zwei von
ihnen wären auf der Instanz des Autors (ein Nutzer, ein Immich) nie
aufgefallen. Deshalb Wächter, und jeder einmal gegen den kaputten Stand
gefahren.

1. Der OIDC-Rückweg setzte das Sitzungs-Cookie ohne `Secure` — der lokale
   Login tat es richtig. Dieselbe Zusage, zweimal geschrieben.
2. Der Import schrieb `user_id` um und übersah dabei jeden ANDEREN Verweis
   einer Zeile: `event_id`, `location_id`, `entity_id`.
3. Der Immich-Verbindungstest prüfte das Schema der Adresse nicht — die
   Prüfung stand nur beim Speichern, also nicht auf dem Pfad, der die Adresse
   tatsächlich aufruft.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app import auth
from app.config import settings
from app.models import (BaselineLocation, ConfirmState, DatePrecision, Entity,
                        Event, EventEntityLink, Location, MediaRef, Metric,
                        Source, User, UserRole)
from app.routers.auth import (callback, local_login, local_register, login,
                              update_my_settings)
# Unter anderem Namen: `test_immich` heißt im Router nach seiner Aufgabe, und
# pytest würde den Endpunkt hier sonst selbst als Testfall einsammeln.
from app.routers.auth import test_immich as immich_connection_test
from app.routers.data import import_data
from app.schemas import LocalLogin, LocalRegister


# --------------------------------------------------------------------------- #
# 1 — Anmelde-Cookies: alle Merkmale, an jeder Setzstelle
# --------------------------------------------------------------------------- #
@pytest.fixture()
def https_mode(monkeypatch):
    """Betrieb hinter TLS — nur dann ist `Secure` überhaupt zu erwarten."""
    monkeypatch.setattr(settings, "public_base_url", "https://life.example.com")
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(auth, "adopt_orphan_rows", lambda *a, **k: 0)
    auth._fail_state.clear()


def _cookie_header(resp, name: str) -> str:
    """Der `set-cookie`-Kopf zu diesem Cookie — die AUSGELIEFERTE Zeichenkette.

    Bewusst nicht das Argument der Aufruferseite: geprüft wird, was im Browser
    ankommt, und nicht, was jemand zu übergeben glaubte."""
    for key, value in resp.raw_headers:
        if key.decode().lower() == "set-cookie" and value.decode().startswith(name + "="):
            return value.decode()
    raise AssertionError(f"Kein set-cookie für {name!r} in der Antwort")


def _assert_hardened(header: str) -> None:
    assert "HttpOnly" in header, f"HttpOnly fehlt: {header}"
    assert "Secure" in header, f"Secure fehlt: {header}"
    assert "SameSite=lax" in header.replace("samesite", "SameSite"), \
        f"SameSite fehlt: {header}"


def test_local_login_cookie_is_hardened(db, https_mode):
    local_register(LocalRegister(email="chef@example.org", password="passwort123"), db=db)
    resp = local_login(LocalLogin(email="chef@example.org", password="passwort123"), db=db)
    _assert_hardened(_cookie_header(resp, auth.SESSION_COOKIE))


def test_oidc_callback_cookie_is_hardened(db, monkeypatch, https_mode):
    """Der eigentliche Befund: derselbe Cookie, anderer Weg, andere Merkmale.

    Der Ablauf wird nur so weit nachgestellt, wie es für die Antwort nötig ist
    — Provider-Antwort, Token-Tausch und Token-Prüfung sind Doppel. Was echt
    bleibt, ist die Stelle, um die es geht: das Setzen des Cookies.
    """
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_client_id", "life-dash")
    monkeypatch.setattr(auth, "oidc_discovery", lambda: {
        "authorization_endpoint": "https://id.example.com/authorize",
        "token_endpoint": "https://id.example.com/token",
        "issuer": "https://id.example.com",
    })

    # Schritt 1: /login — der State-Cookie trägt den PKCE-Verifier und braucht
    # dieselben Merkmale. Wer ihn mitliest, löst einen abgefangenen Code ein.
    start = login()
    state_header = _cookie_header(start, auth.STATE_COOKIE)
    _assert_hardened(state_header)

    raw_state = state_header.split("=", 1)[1].split(";", 1)[0]
    data = auth.read_cookie(raw_state)

    class _Resp:
        def read(self):
            return b'{"id_token": "egal"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("app.routers.auth.urllib.request.urlopen",
                        lambda *a, **k: _Resp())
    monkeypatch.setattr(auth, "validate_oidc_token", lambda token, **k: {
        "sub": "oidc-sub-1", "email": "wer@example.org", "nonce": data["nonce"]})
    monkeypatch.setattr(auth, "adopt_orphan_rows", lambda *a, **k: 0)

    class _Request:
        cookies = {auth.STATE_COOKIE: raw_state}

    resp = callback(_Request(), code="abc", state=data["state"], db=db)
    _assert_hardened(_cookie_header(resp, auth.SESSION_COOKIE))


def test_cookie_stays_plain_without_tls(db, monkeypatch):
    """Die Gegenrichtung: lokal über http darf `Secure` NICHT gesetzt sein —
    sonst käme der Cookie nie an und die Entwicklung wäre ausgesperrt."""
    monkeypatch.setattr(settings, "public_base_url", "http://127.0.0.1:8000")
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(auth, "adopt_orphan_rows", lambda *a, **k: 0)
    auth._fail_state.clear()
    local_register(LocalRegister(email="lokal@example.org", password="passwort123"), db=db)
    resp = local_login(LocalLogin(email="lokal@example.org", password="passwort123"), db=db)
    header = _cookie_header(resp, auth.SESSION_COOKIE)
    assert "Secure" not in header
    assert "HttpOnly" in header


# --------------------------------------------------------------------------- #
# 2 — Import: ein Verweis zeigt auf Eigenes, oder die Zeile kommt nicht an
# --------------------------------------------------------------------------- #
@pytest.fixture()
def victim(db):
    """Ein zweites Konto mit einem Ereignis und einem Ort — das Ziel."""
    other = User(oidc_subject="opfer-sub", email="opfer@example.org",
                 display_name="Opfer", role=UserRole.user)
    db.add(other)
    db.commit()
    loc = Location(user_id=other.id, name="Geheime Adresse 3",
                   lat=52.5, lng=13.4)
    db.add(loc)
    db.commit()
    ev = Event(user_id=other.id, title="Fremder Termin", category="event",
               date_start=datetime(2026, 5, 5, 10, 0),
               date_precision=DatePrecision.day, source=Source.manual,
               confirmed=ConfirmState.confirmed, location_id=loc.id)
    db.add(ev)
    db.commit()
    ent = Entity(user_id=other.id, name="Fremdes Objekt", type="thing")
    db.add(ent)
    db.commit()
    return {"user": other, "event": ev, "location": loc, "entity": ent}


def _payload(**blocks) -> dict:
    return {"format": "lifedash-export", "version": 1, **blocks}


def test_metric_cannot_attach_to_foreign_event(db, user, victim):
    """Der gemeldete Fall: `metrics` trägt gar kein `user_id`, die `event_id`
    aus der Datei blieb also stehen."""
    result = import_data(payload=_payload(metrics=[{
        "id": "m-1", "event_id": victim["event"].id, "key": "temperature_c",
        "value": 999.0, "source": "weather"}]), db=db, user=user)

    assert result["imported"]["metrics"] == 0
    assert result["skipped_foreign"] == 1
    assert db.query(Metric).count() == 0


def test_link_cannot_attach_to_foreign_event(db, user, victim):
    result = import_data(payload=_payload(event_entity_links=[{
        "id": "l-1", "event_id": victim["event"].id,
        "entity_id": victim["entity"].id, "role": "subject"}]), db=db, user=user)

    assert result["skipped_foreign"] == 1
    assert db.query(EventEntityLink).count() == 0


def test_media_ref_cannot_attach_to_foreign_event(db, user, victim):
    """`media_refs` bekommt ein eigenes `user_id` und sah damit geprüft aus —
    die `event_id` daneben war es nicht."""
    result = import_data(payload=_payload(media_refs=[{
        "id": "mr-1", "event_id": victim["event"].id, "provider": "local",
        "external_id": "x.jpg", "mime": "image/jpeg"}]), db=db, user=user)

    assert result["skipped_foreign"] == 1
    assert db.query(MediaRef).count() == 0


def test_event_cannot_borrow_a_foreign_location(db, user, victim):
    """Die andere Richtung, und die schwerere: über `location_id` stünde der
    NAME eines fremden Ortes im eigenen Zeitstrahl — kein Schreibzugriff auf
    fremde Daten, sondern ein Lesezugriff."""
    result = import_data(payload=_payload(events=[{
        "id": "e-1", "title": "Meins", "category": "event",
        "date_start": "2026-05-05T10:00:00", "date_precision": "day",
        "source": "manual", "confirmed": "confirmed",
        "location_id": victim["location"].id}]), db=db, user=user)

    assert result["skipped_foreign"] == 1
    assert db.query(Event).filter(Event.user_id == user.id).count() == 0


def test_baseline_cannot_borrow_a_foreign_location(db, user, victim):
    """Dieselbe Regel, dritte Tabelle — sie stand in keiner Meldung. Genau
    dafür fragt die Prüfung das SCHEMA und nicht eine Liste von Tabellen."""
    result = import_data(payload=_payload(baseline_locations=[{
        "id": "b-1", "location_id": victim["location"].id,
        "date_start": "2020-01-01", "date_end": "2021-01-01",
        "label": "Zuhause"}]), db=db, user=user)

    assert result["skipped_foreign"] == 1
    assert db.query(BaselineLocation).count() == 0


def test_own_export_still_restores_completely(db, user):
    """Der Fehlalarm-Wächter, und der wichtigere von beiden: eine Prüfung, die
    ein gültiges Backup beschädigt, wird beim ersten Fehlalarm wieder
    ausgebaut. Eltern und Kind stehen in EINER Datei, das Kind zuerst — die
    Reihenfolge innerhalb eines Blocks sagt nichts zu.
    """
    payload = _payload(
        locations=[{"id": "loc-1", "name": "Zuhause", "lat": 52.0, "lng": 13.0}],
        events=[
            {"id": "kind-1", "title": "Reise — Tag 2", "category": "event",
             "date_start": "2026-05-06T10:00:00", "date_precision": "day",
             "source": "manual", "confirmed": "confirmed",
             "parent_event_id": "eltern-1", "location_id": "loc-1"},
            {"id": "eltern-1", "title": "Reise", "category": "event",
             "date_start": "2026-05-05T10:00:00", "date_precision": "day",
             "source": "manual", "confirmed": "confirmed",
             "location_id": "loc-1"},
        ],
        metrics=[{"id": "m-9", "event_id": "kind-1", "key": "temperature_c",
                  "value": 21.5, "source": "weather"}],
    )
    result = import_data(payload=payload, db=db, user=user)

    assert result["skipped_foreign"] == 0, "gültiges Backup wurde beschnitten"
    assert result["imported"]["events"] == 2
    assert result["imported"]["metrics"] == 1
    assert db.query(Event).filter(Event.user_id == user.id).count() == 2


def test_reimport_of_existing_rows_is_still_idempotent(db, user):
    """Zweiter Import derselben Datei: die Eltern liegen jetzt in der
    Datenbank, nicht mehr im Lauf. Die Prüfung muss beide Herkünfte kennen."""
    loc = Location(user_id=user.id, name="Zuhause", lat=52.0, lng=13.0)
    db.add(loc)
    db.commit()
    ev = Event(user_id=user.id, title="Da", category="event",
               date_start=datetime(2026, 5, 5, 10, 0),
               date_precision=DatePrecision.day, source=Source.manual,
               confirmed=ConfirmState.confirmed, location_id=loc.id)
    db.add(ev)
    db.commit()

    result = import_data(payload=_payload(metrics=[{
        "id": "m-2", "event_id": ev.id, "key": "temperature_c",
        "value": 18.0, "source": "weather"}]), db=db, user=user)

    assert result["skipped_foreign"] == 0
    assert result["imported"]["metrics"] == 1


def test_adopted_rows_without_owner_stay_foreign(db, user, victim):
    """Eine Zeile OHNE `user_id` (Alt-Bestand vor der Mehrnutzer-Umstellung)
    gehört niemandem — und darf deshalb nicht als „meins" durchgehen."""
    orphan = Location(user_id=None, name="Herrenlos", lat=1.0, lng=1.0)
    db.add(orphan)
    db.commit()

    result = import_data(payload=_payload(events=[{
        "id": "e-2", "title": "Meins", "category": "event",
        "date_start": "2026-05-05T10:00:00", "date_precision": "day",
        "source": "manual", "confirmed": "confirmed",
        "location_id": orphan.id}]), db=db, user=user)

    assert result["skipped_foreign"] == 1


# --------------------------------------------------------------------------- #
# 3 — Immich-Verbindungstest: das Schema der Adresse
# --------------------------------------------------------------------------- #
@pytest.fixture()
def no_network(monkeypatch):
    """Ein Netzaufruf ist hier der Fehlerfall, nicht der Normalfall."""
    def _boom(*a, **k):
        raise AssertionError("Es wurde trotz ungültiger Adresse ins Netz gegriffen")

    monkeypatch.setattr("app.services.immich.check", _boom)
    return _boom


@pytest.mark.parametrize("bad", [
    "file:///etc/passwd",
    "ftp://intern.example.com",
    "gopher://127.0.0.1:11211",
    "127.0.0.1:2283",          # ohne Schema — urllib rät sonst selbst
])
def test_immich_test_rejects_foreign_schemes(db, user, no_network, bad):
    with pytest.raises(HTTPException) as err:
        immich_connection_test(payload={"url": bad, "api_key": "geheim"}, db=db, user=user)
    assert err.value.status_code == 400
    assert "http" in str(err.value.detail)


def test_immich_settings_still_reject_foreign_schemes(db, user):
    """Die Stelle, an der die Prüfung schon stand — sie muss die Umstellung
    auf die gemeinsame Funktion überleben."""
    with pytest.raises(HTTPException) as err:
        update_my_settings(payload={"immich": {"url": "file:///etc/passwd"}},
                           db=db, user=user)
    assert err.value.status_code == 400


def test_immich_test_accepts_a_normal_url(db, user, monkeypatch):
    """Gegenrichtung: eine gewöhnliche Adresse geht durch — auch eine interne.
    Der Immich-Server steht beim Nutzer, seine Adresse ist seine Sache."""
    seen: list[tuple] = []
    monkeypatch.setattr("app.services.immich.check",
                        lambda url, key: seen.append((url, key)) or {"ok": True})

    out = immich_connection_test(payload={"url": "http://192.168.1.5:2283/", "api_key": "k"},
                      db=db, user=user)
    assert out == {"ok": True}
    assert seen == [("http://192.168.1.5:2283", "k")]
