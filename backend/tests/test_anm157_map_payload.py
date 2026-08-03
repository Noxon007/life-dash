"""Anmerkung 157 — die Karte schickt Fotos als PUNKTE, nicht als Ereignisse.

Anmerkung 140 hat es gemessen und ausdrücklich liegen gelassen: `/api/events/map`
antwortete bei 20.000 Ereignissen mit 6,1 MB, weil jedes Foto sein volles
Ereignis mitbrachte — Titel, Präzision, Quelle, Ereigniskennung und einen
verschachtelten Ort mit eigener Kennung, von denen die Karte nichts zeigt.

Was hier festgenagelt wird, ist deshalb nicht „die Antwort ist kleiner"
(Bytes sind kein Vertrag), sondern **was in der Antwort steht und was nicht**:

* Fotos gehen in `photos`, Pins in `events` — die Trennung aus Anmerkung 139
  eine Schicht tiefer.
* Ortsnamen und Kategorien stehen EINMAL da, je Punkt nur ihr Index.
* Ein Fotopunkt trägt **keine Ereigniskennung**. Das ist die Zusicherung, die
  umfällt, sobald jemand sie „der Vollständigkeit halber" wieder hineinlegt —
  und mit ihr die Hälfte der Ersparnis.
* Der Deckel gilt über BEIDE Formen zusammen: er ist eine Aussage über die
  Karte, nicht über eine Ebene.
"""
from __future__ import annotations

from datetime import datetime

from app.models import (ConfirmState, DatePrecision, Event, Location, Metric,
                        Source)
from app.routers.events import list_map_events


def _loc(db, user, name="Detmold", lat=51.93, lng=8.87) -> Location:
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng, type="photo")
    db.add(loc)
    db.commit()
    return loc


def _photo(db, user, asset, when, loc) -> Event:
    e = Event(user_id=user.id, title=f"Foto in {loc.name}", category="event",
              date_start=when, date_precision=DatePrecision.exact,
              location=loc, source=Source.immich,
              confirmed=ConfirmState.confirmed, confirmed_by="import",
              external_id=f"immich:photo:{asset}")
    db.add(e)
    db.commit()
    return e


def _pin(db, user, title, when, loc, source=Source.manual) -> Event:
    e = Event(user_id=user.id, title=title, category="trip",
              date_start=when, date_precision=DatePrecision.day,
              location=loc, source=source,
              confirmed=ConfirmState.confirmed, confirmed_by="me")
    db.add(e)
    db.commit()
    return e


def test_photos_leave_the_event_list_and_arrive_as_points(db, user):
    loc = _loc(db, user)
    _photo(db, user, "a1", datetime(2024, 6, 1, 12, 30), loc)
    _pin(db, user, "Urlaub", datetime(2024, 6, 2), loc)

    r = list_map_events(db=db, user=user)
    assert [e["title"] for e in r["events"]] == ["Urlaub"]
    assert r["photos"]["points"] == [[51.93, 8.87, "2024-06-01T12:30:00",
                                      "a1", 0, 0]]
    assert r["photos"]["places"] == ["Detmold"]
    assert r["photos"]["cats"] == ["event"]
    # Beide Formen zusammen sind die Karte — `shown`/`total` zählen beide.
    assert r["total"] == 2 and r["shown"] == 2


def test_a_photo_point_carries_no_event_id(db, user):
    """Die Zusicherung, die umfällt, sobald jemand die Kennung zurücklegt.

    36 Zeichen je Punkt sind bei 20.000 Fotos 0,7 MB — für etwas, das die
    Karte nicht benutzt: das Popup eines Fotos zeigt das Bild, nie den
    Bearbeiten-Dialog (Anmerkung 139). Die Identität eines Fotos ist sein
    Asset, und das steht drin.
    """
    loc = _loc(db, user)
    ev = _photo(db, user, "a1", datetime(2024, 6, 1, 12, 30), loc)

    r = list_map_events(db=db, user=user)
    flat = [str(v) for point in r["photos"]["points"] for v in point]
    assert ev.id not in flat
    assert loc.id not in flat
    assert "a1" in flat          # …die Kennung, die es wirklich braucht


def test_place_and_category_are_interned_once(db, user):
    """Der Ortsname ist der längste Wert je Punkt und für hunderte derselbe."""
    loc = _loc(db, user)
    other = _loc(db, user, "Köln", 50.94, 6.96)
    for i in range(5):
        _photo(db, user, f"a{i}", datetime(2024, 6, 1, 8 + i), loc)
    _photo(db, user, "b1", datetime(2024, 6, 2, 9), other)

    block = list_map_events(db=db, user=user)["photos"]
    assert block["places"] == ["Detmold", "Köln"]
    assert block["cats"] == ["event"]
    assert [p[4] for p in block["points"]] == [0, 0, 0, 0, 0, 1]
    assert len(block["points"]) == 6


def test_photos_off_sends_no_points_at_all(db, user):
    """Anmerkung 139: ein ausgeschalteter Schalter soll die Punkte gar nicht
    erst über die Leitung schicken — auch nicht als leere Hüllen."""
    loc = _loc(db, user)
    _photo(db, user, "a1", datetime(2024, 6, 1, 12), loc)
    _pin(db, user, "Urlaub", datetime(2024, 6, 2), loc)

    r = list_map_events(db=db, user=user, photos=False)
    assert r["photos"] == {"places": [], "cats": [], "points": []}
    assert r["total"] == 1 and r["shown"] == 1
    assert [e["title"] for e in r["events"]] == ["Urlaub"]


def test_the_cap_spreads_over_both_kinds(db, user):
    """Deckeln heißt nicht abschneiden — und der Deckel kennt keine Ebenen.

    Ein Deckel je Form wäre zwei Deckel und zwei Hinweise; der Nutzer sieht
    eine Karte. Und `even_spread` muss über die gemeinsame Reihenfolge greifen,
    sonst käme aus einer Bibliothek mit Fotos ab 2010 ein Ausschnitt, in dem
    alle Pins fehlen.
    """
    loc = _loc(db, user)
    for i in range(10):
        _photo(db, user, f"a{i}", datetime(2024, 6, 1, 0, i), loc)
    for i in range(10):
        _pin(db, user, f"Reise {i}", datetime(2024, 7, 1 + i), loc)

    r = list_map_events(db=db, user=user, limit=10)
    assert r["total"] == 20 and r["shown"] == 10
    assert len(r["events"]) + len(r["photos"]["points"]) == 10
    # Gleichmäßig heißt: aus BEIDEN Hälften kommt etwas an.
    assert r["events"] and r["photos"]["points"]


def test_weather_still_reaches_the_pins(db, user):
    """Das Wetter hängt an den Pins — dort zeigen Popup und Stopp-Liste es.

    Fotopunkte bekommen bewusst keins: ein Feld, das immer `null` ist, ist ein
    Versprechen ohne Deckung.
    """
    loc = _loc(db, user)
    pin = _pin(db, user, "Urlaub", datetime(2024, 6, 2), loc)
    db.add(Metric(event_id=pin.id, key="temperature_c", value=21.5,
                  source=Source.weather))
    _photo(db, user, "a1", datetime(2024, 6, 1, 12), loc)
    db.commit()

    r = list_map_events(db=db, user=user, weather=True)
    assert r["events"][0]["weather"] == {"temperature_c": 21.5}
    assert "weather" not in str(r["photos"]["points"])


def test_old_day_clusters_still_draw_as_points(db, user):
    """Die alten Fototag-Sammeleinträge (`immich:day:…`) sind ebenfalls
    `source=immich` und gehören weiter auf die Foto-Ebene — sie haben nur kein
    Asset, also auch kein Vorschaubild. `null` ist hier die richtige Antwort
    und nicht ein leerer String, der wie eine Kennung aussieht."""
    loc = _loc(db, user)
    e = Event(user_id=user.id, title="34 Fotos in Detmold", category="event",
              date_start=datetime(2024, 6, 1), date_precision=DatePrecision.day,
              location=loc, source=Source.immich,
              confirmed=ConfirmState.confirmed, confirmed_by="import",
              external_id="immich:day:2024-06-01:Detmold")
    db.add(e)
    db.commit()

    block = list_map_events(db=db, user=user)["photos"]
    assert len(block["points"]) == 1
    assert block["points"][0][3] is None
