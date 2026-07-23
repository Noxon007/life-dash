"""A47 (Anmerkung 116) — die Verdichtungsstufe ist eine Frage, keine Vorgabe.

Bis 0.38 fasste der Zeitstrahl importierte Besuche fest nach `(Tag, Stadt)`
zusammen. Das ist eine gute Voreinstellung und eine schlechte Vorgabe: „In
welchen Ländern war ich 2019?" und „In welchen Stadtteilen von Berlin?" sind
beide legitim.

Drei Eigenschaften stehen hier auf dem Spiel:

* **Verdichtet wird VOR dem Blättern.** Erst die Seite zu bauen und dann zu
  gruppieren zerschneidet eine Gruppe an der Seitengrenze — beide Hälften
  zeigen dann eine zu kleine Zahl (A39/A37).
* **Kein stiller Rückfall.** Ein Besuch ohne Ortsteil kommt nicht in eine
  Ortsteil-Gruppe, die in Wahrheit die Stadt ist.
* **Beide Dialekte.** Der Ortsteil steckt in einer JSON-Spalte, und
  `json_extract` gibt es nur in SQLite, `->>` nur in PostgreSQL. Genau diese
  Fehlerklasse hat `test_a37_postgres_dialect.py` schon einmal teuer gemacht.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models import ConfirmState, Event, Location, Source
from app.routers.events import (_condensable_visits, _place_of,
                                _visit_group_info, _visit_group_reps,
                                events_index, list_events)

PG = postgresql.dialect()
DAY = datetime(2024, 7, 12, 9, 0)


def _loc(db, user, name, *, city=None, country=None, address=None):
    loc = Location(user_id=user.id, name=name, lat=51.9, lng=8.8,
                   city=city, country=country, address=address)
    db.add(loc)
    db.flush()
    return loc


def _visit(db, user, loc, hour):
    db.add(Event(user_id=user.id, title=f"Besuch: {loc.name}",
                 date_start=DAY.replace(hour=hour), date_end=DAY.replace(hour=hour + 1),
                 category="event", confirmed=ConfirmState.confirmed,
                 source=Source.google_timeline, location=loc,
                 external_id=f"h-{loc.name}-{hour}"))


@pytest.fixture()
def berlin(db, user):
    """Vier Besuche in zwei Berliner Ortsteilen, plus einer in Hamburg."""
    mitte = _loc(db, user, "Rosenthaler Str.", city="Berlin", country="Deutschland",
                 address={"road": "Rosenthaler Str.", "suburb": "Mitte",
                          "city": "Berlin", "country": "Deutschland"})
    kreuz = _loc(db, user, "Oranienstr.", city="Berlin", country="Deutschland",
                 address={"road": "Oranienstr.", "suburb": "Kreuzberg",
                          "city": "Berlin", "country": "Deutschland"})
    hh = _loc(db, user, "Reeperbahn", city="Hamburg", country="Deutschland",
              address={"road": "Reeperbahn", "borough": "St. Pauli",
                       "city": "Hamburg", "country": "Deutschland"})
    for hour in (9, 10):
        _visit(db, user, mitte, hour)
    for hour in (12, 13):
        _visit(db, user, kreuz, hour)
    for hour in (16, 17):
        _visit(db, user, hh, hour)
    db.commit()
    return {"mitte": mitte, "kreuz": kreuz, "hh": hh}


def _rows(db, user, level, **kw):
    return list_events(db=db, user=user, slim=True, visits=True, condense=True,
                       group=level, **kw)


# --------------------------------------------------------------------------- #
# Die Stufen tun, was sie sagen
# --------------------------------------------------------------------------- #
def test_city_is_the_default_and_condenses_per_city(db, user, berlin):
    rows = _rows(db, user, "city")
    # Zwei Städte an diesem Tag → zwei Vertreter statt sechs Besuchen.
    assert len(rows) == 2
    assert {r.group.city for r in rows if r.group} == {"Berlin", "Hamburg"}
    assert {r.group.count for r in rows if r.group} == {4, 2}


def test_country_merges_both_cities(db, user, berlin):
    rows = _rows(db, user, "country")
    assert len(rows) == 1
    assert rows[0].group.city == "Deutschland"
    assert rows[0].group.count == 6


def test_district_splits_berlin_in_two(db, user, berlin):
    rows = _rows(db, user, "district")
    places = {r.group.city for r in rows if r.group}
    assert places == {"Mitte", "Kreuzberg", "St. Pauli"}
    assert len(rows) == 3


def test_point_does_not_condense_at_all(db, user, berlin):
    rows = _rows(db, user, "point")
    assert len(rows) == 6
    assert all(r.group is None for r in rows)


def test_an_unknown_level_is_refused(db, user):
    """Still auf „city" zu biegen hieße, jemandem eine plausible Antwort auf
    eine andere Frage zu geben."""
    with pytest.raises(HTTPException):
        _rows(db, user, "strasse")


# --------------------------------------------------------------------------- #
# Kein stiller Rückfall
# --------------------------------------------------------------------------- #
def test_a_place_without_a_district_stays_on_its_own(db, user):
    """Zwei Besuche an einem Ort ohne Ortsteil dürfen auf der Ortsteil-Stufe
    nicht zusammenfallen — sonst stünde „2 Besuche in <Stadt>" da und sähe aus
    wie ein Ortsteil."""
    wald = _loc(db, user, "Waldparkplatz", city="Detmold", country="Deutschland",
                address={"road": "Waldweg", "city": "Detmold"})
    _visit(db, user, wald, 9)
    _visit(db, user, wald, 11)
    db.commit()
    rows = _rows(db, user, "district")
    assert len(rows) == 2
    assert all(r.group is None for r in rows)
    # Auf Stadt-Ebene fallen dieselben beiden sehr wohl zusammen.
    assert len(_rows(db, user, "city")) == 1


def test_the_district_falls_back_across_naming_variants(db, user):
    """Nominatim benennt dieselbe Ebene je nach Land anders. Eine Abfrage nur
    auf `suburb` fände in halb Europa nichts und sähe aus wie „es gibt keinen
    Ortsteil"."""
    for key in ("suburb", "city_district", "neighbourhood", "quarter", "borough"):
        loc = Location(user_id=user.id, name=f"Ort-{key}", lat=1.0, lng=1.0,
                       address={key: f"Teil-{key}"})
        assert _place_of(loc, "district") == f"Teil-{key}"


def test_hand_written_entries_are_never_condensed(db, user, berlin):
    """Sie sind einzeln eingetragen worden, also sind sie einzeln gemeint."""
    mine = Event(user_id=user.id, title="Konzert", date_start=DAY.replace(hour=20),
                 category="event", confirmed=ConfirmState.confirmed,
                 source=Source.manual, location=berlin["mitte"])
    db.add(mine)
    db.commit()
    rows = _rows(db, user, "country")
    assert any(r.id == mine.id for r in rows)


# --------------------------------------------------------------------------- #
# Verdichtet wird VOR dem Blättern
# --------------------------------------------------------------------------- #
def test_condensing_happens_before_paging(db, user, berlin):
    """Der Kern von A39: Die MENGE wird reduziert, dann wird geblättert. Würde
    erst die Seite gebaut und dann gruppiert, zerschnitte die Seitengrenze eine
    Gruppe — und beide Hälften zeigten eine zu kleine Zahl."""
    page = _rows(db, user, "district", limit=1, offset=0)
    assert len(page) == 1
    # Die Zahl der Gruppe ist die WAHRE Zahl, nicht die auf dieser Seite.
    assert page[0].group.count == 2
    ids = {page[0].id}
    for offset in (1, 2):
        nxt = _rows(db, user, "district", limit=1, offset=offset)
        assert nxt and nxt[0].id not in ids
        ids.add(nxt[0].id)
    assert len(ids) == 3


def test_the_representative_is_stable(db, user, berlin):
    """Springt der Vertreter zwischen zwei Aufrufen, springen beim Blättern
    Einträge."""
    first = [r.id for r in _rows(db, user, "city")]
    again = [r.id for r in _rows(db, user, "city")]
    assert first == again


# --------------------------------------------------------------------------- #
# Der Index sagt, ob die Ortsteil-Stufe überhaupt Daten hat
# --------------------------------------------------------------------------- #
def test_the_index_counts_places_without_address(db, user, berlin):
    _loc(db, user, "Alter Ort ohne Bausteine", city="Detmold")
    db.commit()
    idx = events_index(db=db, user=user)
    assert idx.locations_total == 4
    assert idx.locations_no_address == 1


def test_a_place_without_address_parts_is_fetched_once(db, user):
    """A47 hängt den Rückstand an den EINEN Ortsnamen-Lauf (A28 hat die drei
    Scopes abgeschafft, weil ein Ort sonst mehrfach geocodiert wurde).

    Der Ort hat einen tadellosen Namen und eine Stadt — trotzdem ist er
    Kandidat, weil die Bausteine fehlen. Und danach ist er es NICHT mehr:
    genau die Grenze zwischen einem Rückstand und einem Dauerläufer.
    """
    from app.routers.tracks import _resolve_candidates

    parts = ["road", "suburb", "city", "country"]
    loc = Location(user_id=user.id, name="Kaiserstr., Detmold, Deutschland",
                   lat=51.9, lng=8.8, city="Detmold", address=None)
    db.add(loc)
    db.commit()
    assert loc in _resolve_candidates(db, user.id, parts)

    # Was der Lauf danach hinterlässt — auch im Fehlschlag (leeres Dict).
    loc.address = {}
    db.commit()
    assert loc not in _resolve_candidates(db, user.id, parts)


@pytest.mark.parametrize("hit", [
    None,                                        # OSM kennt den Punkt nicht
    {"address": {}, "type": "yes"},              # getroffen, aber kein Name
])
def test_resolved_name_always_marks_the_address(db, user, monkeypatch, hit):
    """**Die Terminierung des Ortsnamen-Laufs hängt seit A47 hieran.**

    `address IS NULL` macht einen Ort zum Kandidaten. Verlässt ein Ort die
    Auflösung mit NULL — weil OSM nichts kennt oder kein brauchbarer Name
    herauskommt —, ist er beim nächsten Batch wieder vorn, und der Lauf
    endet nie. Genau diese Schleife beschreiben die Anmerkungen 77 und 96,
    zweimal in anderer Gestalt.

    Geprüft werden deshalb die AUSSTIEGE, nicht der Erfolgsfall: auf jedem
    Pfad muss eine Marke stehen bleiben.
    """
    from app.routers import tracks

    monkeypatch.setattr(tracks.geocode_svc, "reverse_geocode",
                        lambda lat, lng, lang=None: hit)
    monkeypatch.setattr(tracks.geocode_svc, "short_name",
                        lambda h, parts=None: None)
    loc = Location(user_id=user.id, name="Ort (51.9000, 8.8000)",
                   lat=51.9, lng=8.8, address=None)
    db.add(loc)
    db.commit()

    assert tracks._apply_resolved_name(db, loc, user.id, ["city"], "de") is False
    assert loc.address is not None, "ohne Marke ist der Ort ewig Kandidat"


def test_an_empty_dict_counts_as_asked(db, user):
    """`address = {}` heißt „nachgesehen, nichts bekommen"; NULL heißt „nie
    nachgesehen". Ohne die Unterscheidung fragte der Rückfüll-Lauf dieselben
    Orte ewig neu — die Falle inzwischen zum achten Mal."""
    _loc(db, user, "Nichts gefunden", address={})
    db.commit()
    idx = events_index(db=db, user=user)
    assert idx.locations_no_address == 0


# --------------------------------------------------------------------------- #
# Beide Dialekte
# --------------------------------------------------------------------------- #
def _sql(query) -> str:
    return str(query.statement.compile(
        dialect=PG, compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("level", ["country", "city", "district"])
def test_every_level_compiles_for_postgres(db, user, level):
    """Der Ortsteil steckt in einer JSON-Spalte, und da gehen die Dialekte
    auseinander: `json_extract` kennt nur SQLite, `->>` nur PostgreSQL. Ein
    Fehler darin fiele in der SQLite-Testsuite nie auf und beim ersten Start
    auf der echten Datenbank sofort (dieselbe Überlegung wie A37)."""
    sql = _sql(_visit_group_reps(db, user.id, level)).lower()
    assert "group by" in sql
    assert _sql(_condensable_visits(db, user.id, level))


def test_the_district_expression_uses_the_postgres_json_operator(db, user):
    sql = _sql(_visit_group_reps(db, user.id, "district")).lower()
    assert "json_extract" not in sql, "SQLite-Funktion im PostgreSQL-SQL"
    assert "->>" in sql or "coalesce" in sql, sql[:400]


def test_sql_and_python_agree_on_the_place(db, user, berlin):
    """`_level_column` (SQL) und `_place_of` (Python) müssen dasselbe sagen —
    sonst findet der Vertreter seine Gruppe nicht und steht ohne Chip da,
    obwohl es die Gruppe gibt."""
    info = _visit_group_info(db, user.id,
                             db.query(Event).filter(Event.user_id == user.id).all(),
                             "district")
    assert set(v["city"] for v in info.values()) == {"Mitte", "Kreuzberg", "St. Pauli"}
