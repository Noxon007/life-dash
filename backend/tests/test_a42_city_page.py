"""A42 — die Stadt als Sammlungs-Eintrag (Anmerkung 102).

A41 lieferte den Reiter, aber keine Seite: geklickt wurde daraus ein
Zeitstrahl-Filter. Hier steht der serverseitige Teil der Seite — Orte,
Ereignis-Vorschau, Beschreibung — und vor allem die drei Eigenschaften, die
still brechen können:

* **Zugriff:** eine Stadt, die nicht in den EIGENEN Orten vorkommt, gibt es
  nicht. Sonst wäre der Beschreibungs-Endpunkt eine Auskunft darüber, wo andere
  waren — der Cache ist bewusst gemeinsam, die Sichtbarkeit nicht.
* **Kein Endlos-Abruf:** „nachgesehen, kein Artikel" muss gespeichert werden,
  sonst fragt jedes Öffnen erneut bei Wikipedia an (F12 `weather_rev`, A39
  Leerstring — dieselbe Falle zum dritten Mal).
* **Keine unbegrenzte Liste:** eine Stadt kann tausende Besuche tragen (A37).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import (CityInfo, ConfirmState, DatePrecision, Event, Location,
                        Source, User, UserRole)
from app.routers.modules import (CITY_EVENT_LIMIT, city_detail, describe_city)
from fastapi import HTTPException


@pytest.fixture()
def other_user(db):
    u = User(oidc_subject="other-sub", email="other@example.org",
             display_name="Zweitnutzer", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def _place(db, user, name, city, country="Deutschland", lat=51.2, lng=6.7):
    loc = Location(user_id=user.id, name=name, city=city, country=country,
                   lat=lat, lng=lng)
    db.add(loc)
    db.flush()
    return loc


def _visit(db, user, loc, day, title="Besuch"):
    ev = Event(user_id=user.id, title=title, category="event", location_id=loc.id,
               date_start=datetime(2024, 6, day, 10, 0),
               date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.google_timeline)
    db.add(ev)
    return ev


@pytest.fixture()
def duesseldorf(db, user):
    a = _place(db, user, "Kaiserstraße", "Düsseldorf")
    b = _place(db, user, "Hofgarten", "Düsseldorf", lat=51.24, lng=6.77)
    for day in range(1, 6):
        _visit(db, user, a, day)
    _visit(db, user, b, 7)
    db.commit()
    return a, b


# --------------------------------------------------------------------------- #
# Die Seite
# --------------------------------------------------------------------------- #
def test_stadtseite_traegt_orte_und_zahlen(db, user, duesseldorf):
    d = city_detail(name="Düsseldorf", db=db, user=user)

    assert d.name == "Düsseldorf" and d.country == "Deutschland"
    assert d.event_count == 6
    assert d.place_count == 2
    assert {p.name for p in d.places} == {"Kaiserstraße", "Hofgarten"}
    assert {p.event_count for p in d.places} == {5, 1}
    assert d.first_visit == datetime(2024, 6, 1, 10, 0)
    assert d.last_visit == datetime(2024, 6, 7, 10, 0)


def test_orte_tragen_koordinaten_fuer_die_karte(db, user, duesseldorf):
    d = city_detail(name="Düsseldorf", db=db, user=user)
    assert all(p.lat is not None and p.lng is not None for p in d.places)


def test_ereignisse_sind_eine_vorschau_keine_liste(db, user):
    """Nach einem Import trägt eine Stadt tausende Besuche. Die Seite zeigt die
    jüngsten und sagt daneben, wie viele es wirklich sind (A37)."""
    loc = _place(db, user, "Kaiserstraße", "Köln")
    for i in range(CITY_EVENT_LIMIT + 25):
        _visit(db, user, loc, (i % 28) + 1, f"Besuch {i}")
    db.commit()

    d = city_detail(name="Köln", db=db, user=user)
    assert d.event_count == CITY_EVENT_LIMIT + 25, "die Wahrheit steht daneben"
    assert d.events_shown == CITY_EVENT_LIMIT
    assert len(d.events) == CITY_EVENT_LIMIT


def test_fremde_stadt_gibt_es_nicht(db, user, other_user, duesseldorf):
    """Der Zugriffsschutz sitzt an den eigenen Orten, nicht am Cache."""
    with pytest.raises(HTTPException) as err:
        city_detail(name="Düsseldorf", db=db, user=other_user)
    assert err.value.status_code == 404


def test_unbekannte_stadt_gibt_404(db, user, duesseldorf):
    with pytest.raises(HTTPException):
        city_detail(name="Atlantis", db=db, user=user)


# --------------------------------------------------------------------------- #
# Die Beschreibung
# --------------------------------------------------------------------------- #
@pytest.fixture()
def wiki(monkeypatch):
    """Ersetzt den Wikipedia-Abruf; sammelt die Aufrufe."""
    calls: list[tuple] = []
    result: dict = {"value": {"description": "Landeshauptstadt von NRW.",
                              "wiki_title": "Düsseldorf",
                              "wiki_url": "https://de.wikipedia.org/wiki/Düsseldorf",
                              "thumbnail": None}}

    def _fake(name, country=None, lang=None):
        calls.append((name, country, lang))
        return result["value"]

    monkeypatch.setattr("app.services.wikipedia.fetch_city_summary", _fake)
    return calls, result


def test_beschreibung_wird_geholt_und_zwischengespeichert(db, user, duesseldorf, wiki):
    calls, _ = wiki

    info = describe_city(name="Düsseldorf", db=db, user=user)
    assert info.description.startswith("Landeshauptstadt")
    assert len(calls) == 1

    # Zweiter Aufruf: aus dem Cache, kein weiterer Abruf
    describe_city(name="Düsseldorf", db=db, user=user)
    assert len(calls) == 1, "jedes Öffnen fragte erneut bei Wikipedia an"

    # Und einmal über den Weg, den eine neue Sitzung nimmt: frisch aus der
    # Datenbank gelesen ist `fetched_at` naiv. Ein zeitzonenbewusster Vergleich
    # wäre hier ein TypeError — und zwar erst beim zweiten Öffnen.
    db.expire_all()
    describe_city(name="Düsseldorf", db=db, user=user)
    assert len(calls) == 1

    assert db.query(CityInfo).count() == 1


def test_das_land_geht_in_die_suche_ein(db, user, duesseldorf, wiki):
    """„Frankfurt" gibt es mehrfach — ohne das Land beschreibt die Suche mit
    voller Überzeugung die falsche Stadt."""
    calls, _ = wiki
    describe_city(name="Düsseldorf", db=db, user=user)
    assert calls[0][1] == "Deutschland"


def test_kein_artikel_wird_als_antwort_gespeichert(db, user, duesseldorf, wiki):
    """Ein Ort ohne Wikipedia-Artikel ist normal. Ohne gespeichertes „nichts
    gefunden" liefe der Abruf bei jedem Öffnen erneut — dieselbe Endlosschleife
    wie bei F12 und A39."""
    calls, result = wiki
    result["value"] = None

    info = describe_city(name="Düsseldorf", db=db, user=user)
    assert info.description is None
    assert db.query(CityInfo).count() == 1, "der Fehlversuch wurde nicht vermerkt"

    describe_city(name="Düsseldorf", db=db, user=user)
    assert len(calls) == 1, "ein Ort ohne Artikel wurde ewig neu abgefragt"


def test_nach_langer_zeit_wird_es_noch_einmal_versucht(db, user, duesseldorf, wiki):
    """Ein Artikel kann entstehen — der Merker ist eine Pause, keine Aufgabe."""
    calls, result = wiki
    result["value"] = None
    describe_city(name="Düsseldorf", db=db, user=user)

    row = db.query(CityInfo).one()
    row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60)
    db.commit()

    result["value"] = {"description": "Inzwischen beschrieben."}
    info = describe_city(name="Düsseldorf", db=db, user=user)
    assert info.description == "Inzwischen beschrieben."
    assert len(calls) == 2


def test_fremde_stadt_laesst_sich_nicht_beschreiben(db, user, other_user,
                                                   duesseldorf, wiki):
    """Der Cache ist bewusst gemeinsam (Wikipedia gehört niemandem hier) — der
    Weg dorthin ist es nicht, sonst verriete er, wo andere waren."""
    calls, _ = wiki
    with pytest.raises(HTTPException) as err:
        describe_city(name="Düsseldorf", db=db, user=other_user)
    assert err.value.status_code == 404
    assert calls == []


def test_beschreibung_kommt_mit_der_seite_zurueck(db, user, duesseldorf, wiki):
    describe_city(name="Düsseldorf", db=db, user=user)
    d = city_detail(name="Düsseldorf", db=db, user=user)
    assert d.info is not None and d.info.description.startswith("Landeshauptstadt")


def test_zweiter_nutzer_erbt_den_cache(db, user, other_user, duesseldorf, wiki):
    """Wer dieselbe Stadt in den eigenen Orten hat, holt sie nicht erneut."""
    calls, _ = wiki
    describe_city(name="Düsseldorf", db=db, user=user)

    _place(db, other_user, "Königsallee", "Düsseldorf")
    db.commit()
    info = describe_city(name="Düsseldorf", db=db, user=other_user)

    assert info.description.startswith("Landeshauptstadt")
    assert len(calls) == 1


def test_sprache_ist_teil_des_schluessels(db, user, duesseldorf, wiki):
    """Sonst bliebe der einmal geholte deutsche Absatz unter einer englischen
    Oberfläche stehen (F10)."""
    calls, _ = wiki
    describe_city(name="Düsseldorf", db=db, user=user)

    user.settings = {"lang": "en"}
    db.commit()
    describe_city(name="Düsseldorf", db=db, user=user)

    assert [c[2] for c in calls] == ["de", "en"]
    assert db.query(CityInfo).count() == 2
