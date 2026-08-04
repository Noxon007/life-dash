"""Ort auf der Karte wählen — und was daran die Aussage ist.

Ein getippter Ortsname und ein geklickter Punkt sehen im Modell gleich aus
(beide werden ein `Location` mit Name und Koordinate), sind aber **umgekehrte
Aussagen**: beim Namen ist der Text die Angabe und die Koordinate ihre
Ableitung, beim Klick ist es andersherum. Genau das nageln die Tests hier fest,
denn wenn es umkippt, kippt es LEISE — der Ort bekommt einen plausiblen Namen,
einen plausiblen Punkt, und liegt nur nicht mehr da, wo hingezeigt wurde.

Vier Stellen, an denen das passieren kann:

* **Vorwärts-Geocoding auf einem gewählten Punkt.** Nominatim antwortet auf den
  Namen mit seinem eigenen Punkt (Ortsmittelpunkt statt Haus). Der Klick wäre
  dann eine Anregung gewesen, keine Angabe.
* **Ein vorhandener Ort wird verschoben.** An ihm hängt die Historie; ein
  Klick, der ihn versetzt, versetzt jedes Ereignis daran mit.
* **`address` bleibt `NULL` nach einem Fehlversuch.** Dann holt der A47-Lauf
  denselben Punkt für immer neu — die Endlos-Abruf-Falle in ihrer nächsten
  Auflage.
* **`location_lat` landet als Spalte am Ereignis.** Der Korrektur-Endpunkt
  setzt alles, was in `data` übrig bleibt, per `setattr` — die Koordinaten
  müssen vorher heraus.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import (ConfirmState, DatePrecision, Event, Location, Source,
                        User)
from app.services.ingestion import place_from_point

# Der Punkt, auf den geklickt wird: ein Haus, nicht ein Ortsmittelpunkt.
PICK_LAT, PICK_LNG = 53.93412, 10.30871
# Was ein VORWÄRTS-Geocoding daraus machen würde — dieselbe Adresse, aber der
# Punkt der Gemeinde. Steht hier, damit die Tests den Unterschied prüfen können
# und nicht nur „irgendeine Koordinate".
FORWARD_LAT, FORWARD_LNG = 53.9500, 10.3100


@pytest.fixture()
def client(db, user):
    """Client ohne `with` — im Kontextmanager fährt der Lifespan und öffnet die
    KONFIGURIERTE Datenbank samt Minuten-Ticker (siehe `test_f20_baseline.py`).
    Auf SQLite unsichtbar, auf PostgreSQL hängt die Suite."""
    app.dependency_overrides[get_db] = lambda: db
    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def geocoding(monkeypatch):
    """Geocoding AN, beide Richtungen als Doppel — und sie antworten
    verschieden.

    Beide zu stellen ist der Punkt: ein Doppel, das nur die Rückwärtsrichtung
    kennt, ließe einen versehentlichen Vorwärts-Abruf ins Leere laufen und der
    Test wäre grün, weil nichts passiert ist. Hier ist der Vorwärts-Abruf eine
    ANDERE Antwort, also fällt seine Benutzung auf.
    """
    monkeypatch.setattr(settings, "geocoding_enabled", True)
    calls = {"forward": 0, "reverse": 0}
    hit = {
        "lat": FORWARD_LAT, "lng": FORWARD_LNG, "type": "house",
        "name": "Musterweg 1, 23795 Mözen, Deutschland",
        "address": {"road": "Musterweg", "house_number": "1",
                    "village": "Mözen", "country": "Deutschland"},
        "namedetails": {},
    }

    def _forward(query, lang=None):
        calls["forward"] += 1
        return dict(hit)

    def _reverse(lat, lng, lang=None):
        calls["reverse"] += 1
        return dict(hit)

    monkeypatch.setattr("app.services.ingestion.geocode", _forward)
    monkeypatch.setattr("app.services.ingestion.reverse_geocode", _reverse)
    return calls


# --------------------------------------------------------------------------- #
# Die eine Regel: der geklickte Punkt ist der gespeicherte Punkt
# --------------------------------------------------------------------------- #
def test_gewaehlter_punkt_wird_nicht_vorwaerts_geocodiert(db, user, geocoding):
    loc = place_from_point(db, user.id, PICK_LAT, PICK_LNG, "irgendwas")

    assert (loc.lat, loc.lng) == (PICK_LAT, PICK_LNG)
    assert geocoding["forward"] == 0, "der Name wurde nachgeschlagen — der Klick wäre verloren"
    assert geocoding["reverse"] == 1


def test_name_und_felder_kommen_aus_dem_punkt(db, user, geocoding):
    """Stadt, Land und Bausteine sind Ableitungen der Koordinate, nicht des
    Formulars — sie tragen A39 (Städte), F4 (Länder) und A47 (Ortsteil)."""
    loc = place_from_point(db, user.id, PICK_LAT, PICK_LNG, "Elternhaus")

    assert "Musterweg" in loc.name
    assert loc.country == "Deutschland"
    assert loc.city == "Mözen"
    assert (loc.address or {}).get("road") == "Musterweg"


def test_getippter_name_ist_nur_rueckfall(db, user, monkeypatch):
    """Ohne Adresse zum Punkt zählt, was im Feld stand — und ohne das ein
    lesbarer Platzhalter statt eines leeren Namens.

    „Ort (…)" ist nicht Verlegenheit, sondern die Marke, an der der
    Ortsnamen-Lauf ihn später wiederfindet (`_name_defect` → „unnamed").
    """
    monkeypatch.setattr(settings, "geocoding_enabled", True)
    monkeypatch.setattr("app.services.ingestion.reverse_geocode",
                        lambda lat, lng, lang=None: None)

    named = place_from_point(db, user.id, PICK_LAT, PICK_LNG, "Hütte im Wald")
    assert named.name == "Hütte im Wald"

    blank = place_from_point(db, user.id, 51.5, 7.5, "")
    assert blank.name.startswith("Ort (")


def test_fehlversuch_wird_vermerkt(db, user, monkeypatch):
    """Endlos-Abruf-Falle: `address IS NULL` heißt „nie nachgesehen".

    Nachgesehen wurde gerade — auch wenn nichts kam. Ohne die leere Marke holt
    der A47-Rückfüll-Lauf diesen Punkt bei jedem Durchgang erneut.
    """
    monkeypatch.setattr(settings, "geocoding_enabled", True)
    monkeypatch.setattr("app.services.ingestion.reverse_geocode",
                        lambda lat, lng, lang=None: None)
    assert place_from_point(db, user.id, PICK_LAT, PICK_LNG, "X").address == {}


def test_ohne_geocoding_bleibt_address_offen(db, user):
    """Gegenrichtung, und sie ist keine Kosmetik: hier wurde NICHT nachgesehen.

    Eine leere Marke hieße „nachgesehen, nichts da" und schlösse den Ort für
    immer vom Nachtragen aus — eine Instanz ohne Geocoding könnte ihre Orte nie
    mehr auflösen, sobald sie eines bekommt.
    """
    assert place_from_point(db, user.id, PICK_LAT, PICK_LNG, "Hütte").address is None


# --------------------------------------------------------------------------- #
# Identität: der Name — und ein vorhandener Ort wird nie verschoben
# --------------------------------------------------------------------------- #
def test_zweiter_klick_ergibt_keinen_zweiten_ort(db, user, geocoding):
    first = place_from_point(db, user.id, PICK_LAT, PICK_LNG, "")
    second = place_from_point(db, user.id, PICK_LAT + 0.0004, PICK_LNG, "")

    assert second.id == first.id
    # Und er behält seinen Punkt: an ihm hängen Ereignisse, ein Versetzen
    # versetzte sie alle mit.
    assert (second.lat, second.lng) == (PICK_LAT, PICK_LNG)


def test_ort_ohne_koordinate_bekommt_sie(db, user, geocoding):
    """Rein additiv — die einzige Änderung, die ein Klick an einem vorhandenen
    Ort vornehmen darf. Ohne sie bliebe ein Ort ohne Wetter, obwohl gerade
    jemand gezeigt hat, wo er liegt."""
    blind = Location(user_id=user.id, name="Musterweg 1, Mözen, Deutschland")
    db.add(blind)
    db.flush()

    loc = place_from_point(db, user.id, PICK_LAT, PICK_LNG, "")
    assert loc.id == blind.id
    assert (loc.lat, loc.lng) == (PICK_LAT, PICK_LNG)


# --------------------------------------------------------------------------- #
# Über die Endpunkte — dort, wo die Angabe herkommt
# --------------------------------------------------------------------------- #
def test_manuelles_ereignis_mit_gewaehltem_punkt(client, db, geocoding):
    r = client.post("/api/events", json={
        "title": "Grillen im Garten",
        "date_start": "2026-07-01T00:00:00",
        "location_name": "Elternhaus",
        "location_lat": PICK_LAT, "location_lng": PICK_LNG,
    })
    assert r.status_code == 201, r.text
    loc = r.json()["location"]
    assert (loc["lat"], loc["lng"]) == (PICK_LAT, PICK_LNG)
    assert geocoding["forward"] == 0


def test_korrektur_setzt_keine_spalten_am_ereignis(client, db, user, geocoding):
    """Der Korrektur-Endpunkt setzt alles, was in `data` übrig bleibt, per
    `setattr` auf das Ereignis. Bleiben die Koordinaten drin, entsteht ein
    `event.location_lat` — kein Fehler, keine Spalte, nur ein Wert, der beim
    nächsten Commit spurlos verschwindet."""
    ev = Event(user_id=user.id, title="Konzert", category="concert",
               date_start=datetime(2026, 5, 1), date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual)
    db.add(ev)
    db.flush()

    r = client.patch(f"/api/moderation/{ev.id}", json={
        "location_lat": PICK_LAT, "location_lng": PICK_LNG,
    })
    assert r.status_code == 200, r.text
    assert (r.json()["location"]["lat"], r.json()["location"]["lng"]) == (PICK_LAT, PICK_LNG)
    assert not hasattr(ev, "location_lat")


def test_korrektur_ohne_ort_entfernt_ihn_weiterhin(client, db, user):
    """Die Nachbarregel, die beim Umbau hätte kippen können: ein leerer Name
    heißt „Ort entfernen" und nicht „Ort unverändert lassen"."""
    loc = Location(user_id=user.id, name="Irgendwo", lat=1.0, lng=2.0)
    db.add(loc)
    db.flush()
    ev = Event(user_id=user.id, title="X", category="event",
               date_start=datetime(2026, 5, 1), date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual, location=loc)
    db.add(ev)
    db.flush()

    r = client.patch(f"/api/moderation/{ev.id}", json={"location_name": ""})
    assert r.status_code == 200, r.text
    assert r.json()["location"] is None


def test_grundort_mit_gewaehltem_punkt(client, geocoding):
    """Der Fall, für den das Paket am meisten zählt: „das Elternhaus" hat oft
    keine Adresse, die Nominatim findet — und ohne Koordinate bekämen seine
    Tausende abgeleiteter Tage nie ein Wetter."""
    r = client.post("/api/baselines", json={
        "place": "Elternhaus", "date_start": "1991-09-25", "date_end": "2011-09-25",
        "lat": PICK_LAT, "lng": PICK_LNG,
    })
    assert r.status_code == 201, r.text
    assert (r.json()["lat"], r.json()["lng"]) == (PICK_LAT, PICK_LNG)
    assert geocoding["forward"] == 0


def test_grundort_aendern_verschiebt_den_punkt(client, geocoding, monkeypatch):
    r = client.post("/api/baselines", json={
        "place": "Elternhaus", "date_start": "1991-09-25", "date_end": "2011-09-25",
        "lat": PICK_LAT, "lng": PICK_LNG,
    })
    bid = r.json()["id"]

    # Anderer Punkt, andere Adresse — sonst griffe die Namens-Identität und der
    # Test bewiese nur, dass zweimal dasselbe zurückkommt.
    monkeypatch.setattr("app.services.ingestion.reverse_geocode",
                        lambda lat, lng, lang=None: {
                            "lat": 0, "lng": 0, "type": "house",
                            "address": {"road": "Andere Str.", "city": "Kiel",
                                        "country": "Deutschland"}, "namedetails": {}})
    r = client.patch(f"/api/baselines/{bid}", json={"lat": 54.32, "lng": 10.14})
    assert r.status_code == 200, r.text
    assert (r.json()["lat"], r.json()["lng"]) == (54.32, 10.14)


def test_unsinnige_koordinate_wird_abgelehnt(client):
    """Eine Koordinate außerhalb der Erde ist kein Ort, sondern ein Tippfehler
    — und würde als Wohnort klaglos Tausende Tage mit Wetter von nirgendwo
    füllen."""
    r = client.post("/api/baselines", json={
        "place": "X", "date_start": "2020-01-01", "lat": 91.0, "lng": 10.0,
    })
    assert r.status_code == 422
