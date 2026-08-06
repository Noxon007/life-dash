"""Anmerkung 199 — die Befunde einer Code-Durchsicht, jeder mit seinem Wächter.

Fünf Fehler, die keine bestehende Prüfung anfassen konnte, und sie teilen sich
denselben Nenner: **jeder ist eine Regel, die es schon gab, an einer zweiten
Stelle anders.** Die Löschliste kannte `day_metrics`, der Export nicht. Die
Rangliste führte einen Stichentscheid, die Balken darüber nicht. Der
Ereignis-Zweig von `discard_weather` fragte nach der Quelle, der Tages-Zweig
nicht.

Deshalb prüft dieses File, wo es geht, **strukturell statt an einem Beispiel**
(`test_every_user_table_can_be_exported` gegen `Base.metadata`) — nach dem
Vorbild von `test_wipe_completeness.py`. Ein Beispiel findet nur die Tabelle,
nach der jemand gefragt hat; eine Tabelle, die niemandem einfällt, kann kein
Beispiel vermissen.
"""
from __future__ import annotations

from datetime import date, datetime

from app.database import Base
from app.models import (ConfirmState, DatePrecision, DayMetric, Entity,
                        EventEntityLink, Event, Location, Metric, Source, User,
                        UserRole)
from app.routers.data import export_data, import_data, wipe_my_data
from app.services.enrichment import discard_weather
from app.services.stats_overview import compute_overview

# Tabellen, die der Export bewusst NICHT trägt — mit Begründung, damit
# „vergessen" und „gelassen" unterscheidbar bleiben (dieselbe Form wie
# `WIPE_KEEPS`).
EXPORT_KEEPS = {
    "users": "Das Konto entsteht beim Anmelden, nicht beim Zurückspielen.",
    "jobs": "Lauf-Protokoll dieser Instanz, keine Lebensdaten.",
    "city_info": "Wikipedia-Zwischenspeicher, gehört keinem Konto (A42).",
}


# --------------------------------------------------------------------------- #
# 1. Der Export muss jede Tabelle kennen, die der Wipe löscht
# --------------------------------------------------------------------------- #
def test_every_user_table_can_be_exported(db, user):
    """`day_metrics` fehlte im Export, seit es die Tabelle gibt.

    Auffallen konnte das nirgends: der Wipe-Dialog sagt „mach vorher ein
    Backup", das Backup lief durch, die Datei sah vollständig aus — und nach
    dem Zurückspielen fehlte das Wetter der Jahre, in denen nur ein Wohnort
    steht. Genau die Jahre also, für die F20 gebaut wurde.

    Geprüft wird gegen `Base.metadata`, damit auch die Tabelle rot wird, die
    es beim Schreiben dieses Tests noch nicht gab.
    """
    payload = export_data(db=db, user=user)
    known = {k for k in payload if isinstance(payload.get(k), list)} | set(EXPORT_KEEPS)
    forgotten = sorted(set(Base.metadata.tables) - known)

    assert not forgotten, (
        f"Diese Tabellen trägt der Export nicht: {forgotten}. Entweder in "
        "routers/data.py aufnehmen (Export UND Import-`plan`) oder hier in "
        "EXPORT_KEEPS mit Begründung eintragen.")


def test_export_keeps_carry_a_reason():
    for table, reason in EXPORT_KEEPS.items():
        assert table in Base.metadata.tables, f"{table} gibt es gar nicht mehr"
        assert len(reason) > 20, f"{table}: Begründung fehlt"


def test_every_exported_block_has_a_way_back(db, user):
    """Ein Block im Export ohne Gegenstück im Import ist eine Sicherung, die
    nur in eine Richtung funktioniert — und das merkt man erst beim Zurück.

    Geprüft am Verhalten und nicht am Quelltext: `import_data` meldet je
    Tabelle, wie viele Zeilen es angelegt hat. Was der Export füllt, muss dort
    auftauchen; was nur der Export kennt, fällt hier auf.
    """
    _populate(db, user)

    payload = export_data(db=db, user=user)
    filled = {k for k, v in payload.items() if isinstance(v, list) and v}
    wipe_my_data(confirm="LÖSCHEN", db=db, user=user)
    result = import_data(payload=payload, db=db, user=user)

    unreachable = sorted(filled - set(result["imported"]))
    assert not unreachable, (
        f"Diese Blöcke exportiert Life-Dash, holt sie aber nie zurück: "
        f"{unreachable}. Der `plan` in `import_data` braucht eine Zeile.")


def _populate(db, user) -> None:
    """Von jeder exportierten Sorte mindestens eine Zeile."""
    from app.models import (BaselineLocation, Fragment, FragmentStatus,
                            MediaRef, Track)

    loc = Location(user_id=user.id, name="Elternhaus", city="Bad Segeberg",
                   country="Deutschland", lat=53.9, lng=10.3)
    frag = Fragment(user_id=user.id, raw_text="{}", source=Source.manual,
                    status=FragmentStatus.processed)
    ent = Entity(user_id=user.id, type="animal", name="Amsel",
                 confirmed=ConfirmState.confirmed)
    db.add_all([loc, frag, ent])
    db.flush()
    ev = Event(user_id=user.id, title="Besuch", category="event",
               date_start=datetime(2001, 4, 1), date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual,
               location_id=loc.id)
    db.add(ev)
    db.flush()
    db.add_all([
        EventEntityLink(event_id=ev.id, entity_id=ent.id),
        Metric(event_id=ev.id, key="temperature_c", value=12.0,
               source=Source.weather),
        MediaRef(user_id=user.id, event_id=ev.id, provider="local",
                 external_id="a.jpg"),
        Track(user_id=user.id, date_start=datetime(2001, 4, 1),
              date_end=datetime(2001, 4, 1, 1), points=[[53.9, 10.3], [54.0, 10.4]],
              activity_type="walk", distance_m=1200.0),
        BaselineLocation(user_id=user.id, location_id=loc.id, label="Kindheit",
                         date_start=date(1995, 3, 1), date_end=date(2007, 8, 31)),
        DayMetric(user_id=user.id, day=date(1998, 7, 4), key="temp_max_c",
                  value=26.5, source=Source.weather),
    ])
    db.commit()


def test_the_day_weather_survives_a_backup_and_a_wipe(db, user):
    """Derselbe Satz einmal ausgeführt: exportieren, alles löschen,
    zurückspielen — und das Tageswetter ist wieder da."""
    loc = Location(user_id=user.id, name="Elternhaus", lat=51.9, lng=8.9)
    db.add(loc)
    db.flush()
    db.add(DayMetric(user_id=user.id, day=date(1998, 7, 4), key="temp_max_c",
                     value=26.5, unit="°C", source=Source.weather))
    db.add(DayMetric(user_id=user.id, day=date(1998, 7, 4), key="weather",
                     value_text="klar", source=Source.weather))
    db.commit()

    payload = export_data(db=db, user=user)
    assert len(payload["day_metrics"]) == 2

    wipe_my_data(confirm="LÖSCHEN", db=db, user=user)
    import_data(payload=payload, db=db, user=user)

    rows = {r.key: r for r in db.query(DayMetric).all()}
    assert set(rows) == {"temp_max_c", "weather"}
    # Ein Tag muss ein Tag bleiben — die Wohnort-Rechnung vergleicht `date`.
    assert rows["temp_max_c"].day == date(1998, 7, 4)
    assert rows["temp_max_c"].value == 26.5
    assert rows["weather"].value_text == "klar"


def test_a_second_import_does_not_break_on_the_unique_key(db, user):
    """Der Fall, der ohne den fachlichen Vergleich den GANZEN Import gerissen
    hätte: `ux_day_metrics_key` (Konto, Tag, Kennzahl) ist zugesagt, und das
    Tageswetter entsteht bei jedem Anreicherungslauf unter einer neuen
    Kennung neu. Ein Backup von gestern trägt also dieselbe Aussage mit einer
    anderen id — und der Fehler käme erst beim Commit, nachdem jede andere
    Tabelle schon als importiert gezählt war."""
    db.add(DayMetric(user_id=user.id, day=date(1998, 7, 4), key="temp_max_c",
                     value=26.5, source=Source.weather))
    db.commit()
    payload = export_data(db=db, user=user)

    # Der Bestand bleibt stehen, die Sicherung bringt dieselbe Aussage unter
    # einer FREMDEN Kennung mit.
    payload["day_metrics"][0]["id"] = "00000000-0000-0000-0000-0000000000ff"
    result = import_data(payload=payload, db=db, user=user)

    assert db.query(DayMetric).count() == 1
    assert result["imported"]["day_metrics"] == 0
    assert result["skipped_existing"] >= 1


# --------------------------------------------------------------------------- #
# 2. Die wärmste Reise heißt wie die Reise
# --------------------------------------------------------------------------- #
def _ev(db, user, title, when, *, parent=None, category="trip", temp=None):
    e = Event(user_id=user.id, title=title, category=category, date_start=when,
              date_precision=DatePrecision.day, confirmed=ConfirmState.confirmed,
              source=Source.manual, parent_event_id=parent)
    db.add(e)
    db.commit()
    if temp is not None:
        db.add(Metric(event_id=e.id, key="temperature_c", value=temp,
                      source=Source.weather))
        db.commit()
    return e


def test_the_warmest_trip_is_named_after_the_trip(db, user):
    """Gruppiert wird über den Elternteil, benannt wurde das erste KIND — die
    Kachel sagte „Andalusien — Tag 1" statt „Andalusien". Sie traf damit
    ausgerechnet den Fall, für den es die Mittelung gibt."""
    trip = _ev(db, user, "Andalusien", datetime(2023, 8, 1))
    _ev(db, user, "Andalusien — Tag 1", datetime(2023, 8, 1, 9),
        parent=trip.id, temp=30.0)
    _ev(db, user, "Andalusien — Tag 2", datetime(2023, 8, 2, 9),
        parent=trip.id, temp=34.0)

    warmest = compute_overview(db, user.id)["weather"]["warmest_trip"]

    assert warmest["title"] == "Andalusien"
    assert warmest["avg"] == 32.0


def test_an_undivided_trip_keeps_its_own_name(db, user):
    """Die Gegenrichtung — ohne Tages-Kinder ist das Ereignis sein eigener
    Schlüssel, und das hat immer gestimmt. Ein Wächter, der nur seinen
    Auslöser kennt, ist einer für die Vergangenheit."""
    _ev(db, user, "Wochenende am Meer", datetime(2024, 6, 8, 10), temp=22.0)

    warmest = compute_overview(db, user.id)["weather"]["warmest_trip"]

    assert warmest["title"] == "Wochenende am Meer"


# --------------------------------------------------------------------------- #
# 3. Balken und Rangliste sortieren gleich
# --------------------------------------------------------------------------- #
def _at(db, user, place, when):
    loc = (db.query(Location)
           .filter(Location.user_id == user.id, Location.name == place).first())
    if loc is None:
        loc = Location(user_id=user.id, name=place, city=place)
        db.add(loc)
        db.flush()
    e = Event(user_id=user.id, title=f"Besuch: {place}", category="event",
              date_start=when, date_precision=DatePrecision.day,
              confirmed=ConfirmState.confirmed, source=Source.manual,
              location_id=loc.id)
    db.add(e)
    db.commit()


def _residence(db, user, place, start, end):
    """Ein Wohnort, dessen Tage NICHT aus Ereignissen kommen."""
    from app.models import BaselineLocation

    loc = Location(user_id=user.id, name=place, city=place)
    db.add(loc)
    db.flush()
    db.add(BaselineLocation(user_id=user.id, location_id=loc.id,
                            date_start=start, date_end=end))
    db.commit()


def test_places_with_the_same_count_are_ordered_by_name(db, user):
    """Bei Gleichstand entschied die Reihenfolge der Datenbank — auf
    PostgreSQL die Hash-Aggregation, also zwischen zwei Aufrufen verschieden.
    Die Rangliste direkt darunter führt diesen Stichentscheid seit Anmerkung
    156; die Balken darüber taten es nicht, und beide stehen im selben Reiter
    untereinander.

    **Warum der Gleichstand hier über einen WOHNORT gebaut wird.** Ein Test
    mit zwei Ereignis-Orten wäre auf SQLite grün, auch mit dem Fehler drin:
    dort sortiert `GROUP BY name` ohnehin alphabetisch, das Ergebnis stimmte
    also aus Versehen. Erst der Wohnort erzeugt eine Reihenfolge, die
    NACHWEISLICH nicht alphabetisch ist — `compute_overview` hängt seine Tage
    hinter die aus den Ereignissen, und `sorted` ist stabil. Ohne den
    Stichentscheid steht deshalb „Zürich" vor „Aachen", auf jeder Datenbank.
    """
    for day in (1, 2, 3):
        _at(db, user, "Zürich", datetime(2024, 3, day))
    _residence(db, user, "Aachen", date(2019, 1, 1), date(2019, 1, 3))

    ov = compute_overview(db, user.id)

    assert dict(ov["top_places"])["Aachen"] == 3      # gleichauf, nicht knapper
    assert dict(ov["top_places"])["Zürich"] == 3
    assert [name for name, _n in ov["top_places"]] == ["Aachen", "Zürich"]
    assert [name for name, _n in ov["top_cities"]] == ["Aachen", "Zürich"]


def test_more_days_still_beat_the_alphabet(db, user):
    """Der Stichentscheid ist die ZWEITE Stufe und darf die erste nicht
    überstimmen — sonst wäre aus einer Rangliste eine Namensliste geworden."""
    for day in (1, 2, 3, 4):
        _at(db, user, "Zürich", datetime(2024, 3, day))
    _residence(db, user, "Aachen", date(2019, 1, 1), date(2019, 1, 3))

    ov = compute_overview(db, user.id)

    assert [name for name, _n in ov["top_places"]] == ["Zürich", "Aachen"]


def test_the_animal_ranking_carries_the_tiebreak_in_its_query(db, user):
    """Bei den Tieren wiegt der Gleichstand schwerer als bei den Orten: die
    Rangfolge steht in SQL, mit `LIMIT` — es entscheidet also, WER überhaupt
    in der Liste steht, nicht nur an welcher Stelle.

    **Geprüft wird die Abfrage und nicht ihr Ergebnis, und das ist hier die
    ehrlichere Prüfung.** Ein Ergebnis-Vergleich wäre auf SQLite grün, auch
    ohne den Stichentscheid (dieselbe Falle wie oben), und ginge auf
    PostgreSQL nur manchmal kaputt — ein Wächter, der vom Ausführungsplan
    abhängt, ist keiner. Dass die Zeile im Ergebnis ankommt, prüft der Test
    darunter.
    """
    import re

    src = compute_overview.__globals__["__file__"]
    body = open(src, encoding="utf-8").read()
    animals = body.split("animal_rows = ", 1)[1].split(".all())", 1)[0]

    assert "Entity.name.asc()" in re.sub(r"\s+", " ", animals), (
        "Die Tier-Rangliste sortiert bei Gleichstand nach der Datenbank — "
        "und ihr LIMIT entscheidet dann, wer aus der Liste fällt.")


def test_the_animal_ranking_still_answers(db, user):
    """Die Gegenprobe zum Wächter darüber: der Stichentscheid darf die
    Rangfolge nach Häufigkeit nicht überschreiben."""
    e = Event(user_id=user.id, title="Spaziergang", category="event",
              date_start=datetime(2024, 5, 1), confirmed=ConfirmState.confirmed,
              source=Source.manual)
    db.add(e)
    db.flush()
    for name, times in (("Waschbär", 1), ("Amsel", 3)):
        ent = Entity(user_id=user.id, type="animal", name=name,
                     confirmed=ConfirmState.confirmed)
        db.add(ent)
        db.flush()
        for _ in range(times):
            db.add(EventEntityLink(event_id=e.id, entity_id=ent.id))
    db.commit()

    names = [row[0] for row in compute_overview(db, user.id)["top_animals"]]

    assert names == ["Amsel", "Waschbär"]


# --------------------------------------------------------------------------- #
# 4. „Wetter verwerfen" nimmt nur Wetter mit
# --------------------------------------------------------------------------- #
def test_discarding_the_day_weather_leaves_a_foreign_metric(db, user):
    """Der Ereignis-Zweig fragte nach der Quelle, der Tages-Zweig nicht — eine
    Regel an zwei Orten, verschieden aufgeschrieben. Heute schreibt nur die
    Anreicherung in `day_metrics`; der erste zweite Schreiber hätte seine
    Zeilen kommentarlos verloren."""
    db.add(DayMetric(user_id=user.id, day=date(2001, 4, 1), key="temp_max_c",
                     value=19.0, source=Source.weather))
    db.add(DayMetric(user_id=user.id, day=date(2001, 4, 1), key="steps",
                     value=8400, source=Source.manual))
    db.commit()

    removed = discard_weather(db, user.id, events=False)

    assert removed["days"] == 1
    assert [r.key for r in db.query(DayMetric).all()] == ["steps"]


# --------------------------------------------------------------------------- #
# 5. Der Timeline-Import meldet nur, was wirklich unlesbar war
# --------------------------------------------------------------------------- #
def test_a_consumed_activity_segment_is_not_reported_as_invalid(db, user):
    """`_annotate_paths` VERBRAUCHT die activity-Segmente, die einem Pfad
    seinen Typ geben — gezählt wurde danach, also meldete ein sauberer
    Geräte-Export „unbrauchbare Segmente" für Segmente, die restlos angekommen
    sind. Eine Zahl, die genau dann Alarm schlägt, wenn alles gut ging."""
    from app.routers.tracks import import_timeline

    payload = {"semanticSegments": [
        {"startTime": "2024-05-01T08:00:00+02:00",
         "endTime": "2024-05-01T08:30:00+02:00",
         "timelinePath": [{"point": "51.2°, 6.7°"}, {"point": "51.3°, 6.8°"},
                          {"point": "51.4°, 6.9°"}]},
        {"startTime": "2024-05-01T08:05:00+02:00",
         "endTime": "2024-05-01T08:25:00+02:00",
         "activity": {"start": "51.2°, 6.7°", "end": "51.4°, 6.9°",
                      "distanceMeters": 4200,
                      "topCandidate": {"type": "cycling"}}},
    ]}

    result = import_timeline(payload=payload, auto_resolve=False, db=db, user=user)

    assert result.tracks_created == 1
    assert result.skipped_invalid == 0
