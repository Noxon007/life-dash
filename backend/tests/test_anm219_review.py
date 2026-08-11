"""Anmerkung 219 — Backend-Durchsicht: vier Befunde, alle nachgestellt.

Jede Prüfung hier ist **einmal gegen den kaputten Stand gelaufen** und war rot.
Das ist in diesem Projekt keine Formalie, sondern der Unterschied zwischen einem
Wächter und einer Zeile, die grün ist, weil es die Funktion GIBT (CLAUDE.md,
„Prüfungen, die nichts prüfen").

Die vier Befunde und was sie gemeinsam haben: drei von vieren sind eine Regel,
die an zwei Orten steht und an einem davon unvollständig ist.

1. **Widerruf gegen Neuausstellung.** `revoke_sessions` setzt den Schnitt eine
   Sekunde in die ZUKUNFT (mit Nachkommastellen), `sign_cookie` schrieb
   `iat = int(time.time())` — auf die Sekunde ABGESCHNITTEN. Ein Cookie, das
   direkt nach dem Widerruf ausgestellt wird, war damit immer älter als der
   Schnitt: der Passwortwechsel warf den Nutzer aus seiner eigenen Anwendung,
   und ein Login in den zwei Sekunden nach „überall abmelden" ging auch nicht.
   `test_anm209_sessions.py` prüfte beide Hälften einzeln und nie den Rundlauf.

2. **Die Rohansicht hatte ihre eigene Abhängigkeitsliste** — die dritte im
   Projekt, neben `wipe.WIPE_ORDER` und `photo_points.delete_events`, und die
   einzige unvollständige. Jetzt fragt sie das SCHEMA, wer auf eine Zeile zeigt.

3. **`ux_metrics_weather` fehlte im ersten Lauf** einer frischen Instanz, weil
   `ensure_schema` seine Tabellenliste VOR `create_all` erhob.

4. **Der Nachtplan brach beim ersten Fehler für alle FOLGENDEN Nutzer ab** —
   ein `try` um die ganze Schleife statt um einen Durchgang.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect

from app import auth
from app.models import (BaselineLocation, Event, Job, Location, Metric,
                        Source, Track, User, UserRole)


# --------------------------------------------------------------------------- #
#  1 — Widerrufen und im selben Atemzug neu ausstellen
# --------------------------------------------------------------------------- #
def _user(**kw) -> User:
    u = User(id="u1", oidc_subject="local:a@b.c", email="a@b.c")
    for k, v in kw.items():
        setattr(u, k, v)
    return u


def test_the_cookie_issued_right_after_a_revocation_is_valid():
    """Der gemeldete Fehler, in der Reihenfolge des Endpunkts.

    `local_change_password` widerruft und stellt SOFORT neu aus — dazwischen
    liegen Millisekunden, nicht Sekunden. Genau dieser Rundlauf fehlte.
    """
    user = _user()
    auth.revoke_sessions(user)
    fresh = auth.read_cookie(auth.session_cookie_for(user))
    assert auth.session_still_valid(user, fresh)


def test_a_login_in_the_same_second_as_a_logout_all_works():
    """„Überall abmelden" und sofort wieder anmelden — dieselbe Sekunde.

    Ohne die Reparatur war das Konto für ein bis zwei Sekunden nicht
    anmeldbar: jedes frische Cookie fiel unter den Schnitt.
    """
    user = _user()
    auth.revoke_sessions(user)
    assert auth.session_still_valid(user, auth.read_cookie(auth.session_cookie_for(user)))


def test_revoking_still_kills_the_cookie_from_before():
    """Die Gegenrichtung, und der eigentliche Zweck des Widerrufs.

    Eine Reparatur, die den Schnitt einfach aufweicht, hätte diesen Test
    gekippt — sie hätte die Sicherheit gegen die Bequemlichkeit getauscht.
    """
    user = _user()
    before = auth.read_cookie(auth.session_cookie_for(user))
    auth.revoke_sessions(user)
    assert not auth.session_still_valid(user, before)
    # …und die neue gilt trotzdem.
    assert auth.session_still_valid(user, auth.read_cookie(auth.session_cookie_for(user)))


def test_an_aware_cutoff_from_the_database_rejects_as_well_as_it_accepts():
    """PostgreSQL kann den Schnitt zeitzonenbehaftet zurückgeben.

    `test_anm209_sessions.py` prüft davon die ANNEHMENDE Hälfte. Fehlte die
    Umrechnung nur im ablehnenden Zweig, wäre das ein Widerruf, der auf einer
    Datenbank hält und auf der anderen durchlässt — und niemand sähe es, weil
    die Testsuite standardmäßig auf SQLite läuft.
    """
    aware = datetime.now(timezone.utc)
    user = _user(sessions_valid_from=aware)
    # Vorher ausgestellt (eine Stunde alt): abgelehnt.
    assert not auth.session_still_valid(
        user, {"uid": "u1", "iat": time.time() - 3600})
    # Danach ausgestellt: angenommen.
    assert auth.session_still_valid(user, auth.read_cookie(auth.session_cookie_for(user)))


def test_the_issue_time_never_lies_in_the_future():
    """**Die Falle, in die die erste Fassung dieser Reparatur gelaufen ist.**

    Der naheliegende Weg war, `iat` bis hinter den Schnitt zu SCHIEBEN. PyJWT
    weist ein Token mit `iat` in der Zukunft aber mit `ImmatureSignatureError`
    ab — `read_cookie` liefert dann `None`, und aus „Cookie gilt nicht" wäre
    „Cookie ist unlesbar" geworden, also derselbe Ausfall eine Schicht tiefer.
    Deshalb löst die Reparatur es über die AUFLÖSUNG und nicht über die Grenze.
    """
    user = _user()
    auth.revoke_sessions(user)
    claims = auth.read_cookie(auth.session_cookie_for(user))
    assert claims is not None, "Das Cookie ließ sich nicht einmal lesen."
    assert claims["iat"] <= time.time()


def test_the_session_does_not_get_longer_by_being_reissued():
    """Ein Widerruf verschiebt keine Laufzeit.

    Die verworfene erste Fassung hätte `exp` an eine vorgeschobene
    Ausstellungszeit gehängt — eine Sitzung, die mit jedem Widerruf ein Stück
    länger gilt. Der Test bleibt stehen, weil genau dieser Griff naheliegt.
    """
    plain = auth.read_cookie(auth.session_cookie_for(_user()))
    revoked_user = _user()
    auth.revoke_sessions(revoked_user)
    revoked = auth.read_cookie(auth.session_cookie_for(revoked_user))
    assert abs(revoked["exp"] - plain["exp"]) <= 1
    assert revoked["exp"] <= int(time.time()) + auth.session_max_age()


# --------------------------------------------------------------------------- #
#  2 — Die Rohansicht kennt jeden, der auf eine Zeile zeigt
# --------------------------------------------------------------------------- #
def test_every_foreign_key_into_a_deletable_table_has_an_answer():
    """**Der eigentliche Wächter**: nicht die drei gefundenen Spalten, sondern
    die Frage, ob eine VIERTE unbemerkt dazukommen kann.

    Gefragt wird das Schema, nicht eine Beispielliste — dieselbe Bauart wie
    `test_wipe_covers_every_user_table`. Eine neue Tabelle mit einem neuen
    Verweis macht diesen Test rot, statt still eine Waise zu hinterlassen.
    """
    from app.routers import admin

    for table, column in admin.all_dependent_columns():
        assert (table, column) in admin.ON_DELETE, (
            f"{table}.{column} zeigt auf eine Tabelle, die über die Rohansicht "
            f"gelöscht werden kann — `ON_DELETE` sagt aber nicht, was mit der "
            f"Zeile geschehen soll.")


def test_deleting_a_location_that_is_a_residence_is_refused(db, user):
    """Der Wohnort ist Lebensdatenbank und verschwindet nicht als NEBENWIRKUNG.

    Vorher: `{'deleted': True, 'side_effects': []}` — und `baseline_locations`
    zeigte auf einen Ort, den es nicht mehr gab. Auf SQLite lautlos (der
    Zeitraum verlor seinen Ort und zählte seine Tage weiter unter „gesamt",
    aber unter keiner Stadt und keinem Land), auf PostgreSQL ein 500er.
    """
    from fastapi import HTTPException

    from app.routers.admin import delete_row

    loc = Location(user_id=user.id, name="Elternhaus", lat=54.0, lng=10.0)
    db.add(loc)
    db.commit()
    db.add(BaselineLocation(user_id=user.id, location_id=loc.id, label="Kindheit",
                            date_start=date(1986, 4, 2), date_end=date(1992, 8, 31)))
    db.commit()

    with pytest.raises(HTTPException) as err:
        delete_row("locations", loc.id, db=db)
    assert err.value.status_code == 409
    assert "Wohnort" in err.value.detail
    # Und der Ort steht noch — eine Weigerung, die die Hälfte schon getan hat,
    # wäre schlimmer als keine.
    db.rollback()
    assert db.get(Location, loc.id) is not None


def test_deleting_an_event_detaches_its_day_children_and_tracks(db, user):
    """Kind und Weg zeigten auf ein gelöschtes Ereignis.

    Beide sind nullable und stehen für sich — der Lösch-Dialog
    (`with_children=False`) und `photo_points.delete_events` hängen sie
    ausdrücklich ab. Die Rohansicht tat es als einzige nicht.
    """
    from app.routers.admin import delete_row

    parent = Event(user_id=user.id, title="Urlaub", date_start=datetime(2024, 7, 1))
    db.add(parent)
    db.commit()
    child = Event(user_id=user.id, title="Urlaub — Tag 1",
                  date_start=datetime(2024, 7, 1), parent_event_id=parent.id)
    track = Track(user_id=user.id, date_start=datetime(2024, 7, 1),
                  date_end=datetime(2024, 7, 1), event_id=parent.id)
    db.add_all([child, track])
    db.commit()
    # Die Kennungen als reine Zeichenketten festhalten: nach `expunge_all` ist
    # jedes ORM-Objekt von der Session gelöst, und schon `parent.id` wäre dann
    # ein Nachladeversuch.
    parent_id, child_id, track_id = parent.id, child.id, track.id

    result = delete_row("events", parent_id, db=db)
    # `expunge_all` und nicht `expire_all`: `delete_row` löscht per Core-DELETE,
    # von dem die Session nichts weiß — ein bloßes Ablaufen ließe `db.get` den
    # Eintrag im Identity-Map nachladen wollen und mit `ObjectDeletedError`
    # scheitern, statt `None` zu sagen. Der Test prüfte dann seinen eigenen
    # Zwischenspeicher.
    db.expunge_all()
    assert db.get(Event, parent_id) is None
    assert db.get(Event, child_id).parent_event_id is None
    assert db.get(Track, track_id).event_id is None
    # **Und die Antwort SAGT es.** „keine Folgeänderungen" neben zwei
    # abgehängten Zeilen war die eigentliche Stille an diesem Befund.
    assert any("abgehängt" in s for s in result["side_effects"]), result


def test_deleting_an_event_still_takes_what_cannot_stand_alone(db, user):
    """Die Gegenrichtung: was ohne sein Ziel nicht existieren kann, geht mit.

    Ohne diesen Test wäre „alles abhängen" die bequeme Reparatur gewesen — und
    `metrics` hätte danach Zeilen ohne Ereignis getragen.
    """
    from app.routers.admin import delete_row

    event = Event(user_id=user.id, title="Ausflug", date_start=datetime(2024, 7, 1))
    db.add(event)
    db.commit()
    db.add(Metric(event_id=event.id, key="temperature_c", value=21.0,
                  source=Source.weather))
    db.commit()
    event_id = event.id

    result = delete_row("events", event_id, db=db)
    db.expunge_all()
    assert db.query(Metric).filter(Metric.event_id == event_id).count() == 0
    assert any("mitgelöscht" in s for s in result["side_effects"]), result


def test_deleting_a_location_detaches_events(db, user):
    """Was vorher schon richtig war, bleibt es — der Umbau ersetzt eine
    handgeschriebene Kette durch eine schemagetriebene, und der einzige Weg zu
    wissen, dass dabei nichts verloren ging, ist die alte Zusage zu prüfen."""
    from app.routers.admin import delete_row

    loc = Location(user_id=user.id, name="Bahnhof")
    db.add(loc)
    db.commit()
    event = Event(user_id=user.id, title="Abfahrt", date_start=datetime(2024, 7, 1),
                  location_id=loc.id)
    db.add(event)
    db.commit()
    loc_id, event_id = loc.id, event.id

    delete_row("locations", loc_id, db=db)
    db.expunge_all()
    assert db.get(Location, loc_id) is None
    assert db.get(Event, event_id).location_id is None


# --------------------------------------------------------------------------- #
#  3 — Der Wetter-Index gilt ab dem ERSTEN Start
# --------------------------------------------------------------------------- #
def test_a_brand_new_database_has_the_weather_unique_index(tmp_path):
    """`ensure_schema` erhob seine Tabellenliste, bevor es die Tabellen GAB.

    Auf einer frischen Datenbank fiel damit alles aus, was eine bestehende
    Tabelle voraussetzt — allen voran `ux_metrics_weather`, der Dublettenschutz
    aus A11. Er erschien erst beim ZWEITEN Start, und deshalb hat ihn nie
    jemand vermisst: der erste Lauf einer neuen Instanz ist auch der, bei dem
    `SEED_DEMO` Wetter schreibt.
    """
    from app.migrate import ensure_schema

    engine = create_engine(f"sqlite:///{tmp_path/'fresh.db'}")
    ensure_schema(engine)
    names = {i["name"] for i in inspect(engine).get_indexes("metrics")}
    engine.dispose()
    assert "ux_metrics_weather" in names


def test_ensure_schema_stays_idempotent(tmp_path):
    """Zweimal laufen lassen darf nichts ändern — sonst wäre aus der Reparatur
    ein Schema geworden, das bei jedem Start etwas tut."""
    from app.migrate import ensure_schema

    engine = create_engine(f"sqlite:///{tmp_path/'twice.db'}")
    ensure_schema(engine)
    assert ensure_schema(engine) == []
    engine.dispose()


# --------------------------------------------------------------------------- #
#  4 — Der Nachtplan überlebt einen einzelnen Nutzer
# --------------------------------------------------------------------------- #
def test_one_broken_account_does_not_cancel_the_night_for_everyone(db, monkeypatch):
    """Das `try` lag um die ganze Nutzerschleife.

    Ein Fehler beim dritten Konto nahm allen folgenden ihren Termin — still,
    Nacht für Nacht, und ausgerechnet bei den kontogebundenen Läufen, für die
    Anmerkung 115 zwölf Zeilen tiefer genau das verhindern wollte.
    """
    from app.routers import jobs

    first = User(oidc_subject="s-a", email="a@x.y", role=UserRole.user,
                 settings={"job_schedule": {"weather": {"enabled": True, "hour": 3}}})
    second = User(oidc_subject="s-b", email="b@x.y", role=UserRole.user,
                  settings={"job_schedule": {"weather": {"enabled": True, "hour": 3}}})
    db.add_all([first, second])
    db.commit()
    order = sorted([first.id, second.id])

    monkeypatch.setattr(jobs, "SessionLocal", lambda: db)
    monkeypatch.setattr(jobs, "spawn_worker", lambda job_id: None)

    class _AtThree(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 11, 3, 30)

    monkeypatch.setattr(jobs, "datetime", _AtThree)

    # Das erste Konto (nach `db.query(User)`-Reihenfolge) scheitert.
    doomed = order[0]
    real_add = db.add

    def _explode(obj):
        if isinstance(obj, Job) and obj.user_id == doomed:
            raise RuntimeError("kaputtes Konto")
        return real_add(obj)

    monkeypatch.setattr(db, "add", _explode)
    jobs.run_due_schedules()
    monkeypatch.undo()

    started = {j.user_id for j in db.query(Job).all()}
    assert order[1] in started, ("Das zweite Konto bekam seinen Lauf nicht — "
                                 "ein Fehler beim ersten hat die Runde beendet.")


# --------------------------------------------------------------------------- #
#  5 — Kleinkram, der trotzdem eine Regel an zwei Orten war
# --------------------------------------------------------------------------- #
def test_both_outbound_user_agents_name_the_running_version():
    """Nominatim verlangt eine identifizierende Angabe, und `geocode` schickte
    seit jeher „life-dash/0.1" — eine Version, die es nie gab. Die richtige
    stand danebenliegend in `auth.HTTP_HEADERS`. Jetzt EINE Zeichenkette."""
    from app.services import geocode
    from app.version import APP_VERSION, USER_AGENT

    assert APP_VERSION in USER_AGENT
    assert geocode.USER_AGENT == USER_AGENT
    assert auth.HTTP_HEADERS["User-Agent"] == USER_AGENT


def test_health_does_not_tell_a_stranger_that_there_is_no_login():
    """`/health` ist ohne Anmeldung erreichbar — das ist Absicht (die Oberfläche
    nennt es „die richtige Ziel-URL für einen Uptime-Monitor").

    `auth_mode` gehört dann aber nicht hinein: „dev" heißt wörtlich „diese
    Instanz hat keine Tür", und der Datenbanktyp ist eine Auskunft über innen,
    die niemand von außen braucht. Beide Felder hatte kein einziger Leser.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    body = TestClient(app).get("/health").json()
    assert body["status"] == "ok"
    # Was die Oberfläche wirklich liest, bleibt (Anmerkung 86/186):
    assert "version" in body and "weather_model" in body and "ai_provider" in body
    assert "auth_mode" not in body
    assert "database" not in body


def test_the_oidc_callback_refuses_when_oidc_is_off():
    """`/api/auth/login` prüft die Betriebsart, `/api/auth/callback` nicht —
    dieselbe Frage, an einer der beiden Stellen nicht gestellt."""
    from fastapi import HTTPException

    from app.config import settings
    from app.routers.auth import callback

    assert settings.auth_mode != "oidc"
    with pytest.raises(HTTPException) as err:
        callback(request=None, code="c", state="s", db=None)
    assert err.value.status_code == 404
