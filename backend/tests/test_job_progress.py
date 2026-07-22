"""Zwei Läufe, die ihre eigene Arbeit nicht fanden (Anmerkungen 96 und 97).

Beides sind keine Feature-Lücken, sondern Schleifen, die sich selbst im Weg
standen — dieselbe Fehlerklasse, die Anmerkung 77 schon einmal für den
Immich-Lauf beschrieben hat: *eine Schleife, deren Ende von einem Zustand
abhängt, den nur ein Teil der Durchläufe ändert*.

Offline: kein Nominatim, kein Open-Meteo — die Aufrufe werden ersetzt und
gezählt. Genau das Zählen ist der Punkt, denn beide Defekte kosten nichts außer
Anfragen, bis sie plötzlich den Lauf beenden.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Job, Location,
                        Metric, Source)


# --------------------------------------------------------------------------- #
# Anmerkung 96 — der Ortsnamen-Lauf wiederholte seine Fehlschläge
# --------------------------------------------------------------------------- #
def _unnamed(db, user, n, start=0):
    out = []
    for i in range(start, start + n):
        loc = Location(user_id=user.id, name=f"Ort ({i}.0000, 7.0000)",
                       lat=51.0 + i / 100, lng=7.0)
        db.add(loc)
        out.append(loc)
    db.flush()
    return out


@pytest.fixture()
def geocoder(monkeypatch):
    """Ersetzt das Reverse-Geocoding. `unresolvable` sind Orte, für die nie
    etwas zurückkommt — die Sorte, an der sich der Lauf verschluckt hat."""
    import app.routers.tracks as tracks

    state = {"calls": [], "unresolvable": set()}

    def _apply(db, loc, user_id, parts=None, lang=None):
        state["calls"].append(loc.id)
        if loc.id in state["unresolvable"]:
            return False
        loc.name = f"Straße, Stadt {loc.id[:4]}"
        loc.city = f"Stadt {loc.id[:4]}"
        return True

    monkeypatch.setattr(tracks, "_apply_resolved_name", _apply)
    monkeypatch.setattr(tracks, "_geo_delay", lambda: 0.0)
    return state


def test_a_failure_is_not_asked_again_in_the_same_run(db, user, geocoder):
    """Der beobachtete Fall (Anmerkung 96): ein Ort, den OSM nicht kennt,
    blieb Kandidat und wanderte an die Spitze der Warteschlange — jeder Batch
    fragte ihn erneut."""
    from app.routers.tracks import resolve_names_batch

    locs = _unnamed(db, user, 6)
    geocoder["unresolvable"] = {locs[0].id}
    db.commit()

    tried: set[str] = set()
    r1 = resolve_names_batch(db, user, limit=3, skip=tried)
    r2 = resolve_names_batch(db, user, limit=3, skip=tried)

    assert r1.failed == 1 and r1.resolved == 2
    # Der Kern: der Fehlschlag taucht im zweiten Batch NICHT wieder auf.
    assert geocoder["calls"].count(locs[0].id) == 1
    assert r2.resolved == 3
    assert r2.remaining == 0


def test_the_run_finishes_instead_of_walling_itself_in(db, user, geocoder):
    """Die teure Folge, nicht die verlorene Sekunde: sammelten sich `limit`
    unauflösbare Orte vorne, bestand ein ganzer Batch aus Fehlschlägen, der
    Runner sah `resolved == 0` und meldete „nicht auflösbar" — obwohl dahinter
    auflösbare Orte warteten."""
    from app.routers.jobs import _run_resolve_names

    locs = _unnamed(db, user, 8)
    geocoder["unresolvable"] = {l.id for l in locs[:4]}
    db.commit()

    job = Job(user_id=user.id, type="resolve_names", status="running",
              done=0, params={})
    db.add(job)
    db.commit()

    # Batchgröße 25 > Bestand, also entscheidet sich alles im ersten Durchgang;
    # gestaffelt wird die Eigenschaft von test_a_failure… geprüft.
    status, msg = _run_resolve_names(db, job)
    assert status == "done", msg
    assert "4 nicht auflösbar" in msg
    # Jeder Ort genau einmal versucht — die Eigenschaft, die Anmerkung 77 für
    # den Immich-Lauf formuliert hat.
    assert sorted(geocoder["calls"]) == sorted(l.id for l in locs)


def test_remaining_counts_what_is_left_to_try(db, user, geocoder):
    """Bis 0.34 zog `remaining` die Fehlschläge nur von der GEMELDETEN Zahl
    ab — die Zahl stimmte, die Warteschlange nicht."""
    from app.routers.tracks import resolve_names_batch

    locs = _unnamed(db, user, 5)
    geocoder["unresolvable"] = {locs[0].id, locs[1].id}
    db.commit()

    tried: set[str] = set()
    r = resolve_names_batch(db, user, limit=5, skip=tried)
    assert r.resolved == 3 and r.failed == 2
    assert r.remaining == 0        # nichts mehr, was nicht versucht worden wäre
    assert len(tried) == 2


# --------------------------------------------------------------------------- #
# Anmerkung 97 — der Wetterlauf lud vor jedem Batch den ganzen Bestand
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    """Naiv wie die Spalte (DateTime ohne Zeitzone) und in UTC wie der
    Vorfilter — sonst prüfte der Test eine andere Grenze als der Code."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _event(db, user, when, located=True, lat=51.2):
    loc = None
    if located:
        loc = Location(user_id=user.id, name="Detmold", lat=lat, lng=8.8)
        db.add(loc)
        db.flush()
    ev = Event(user_id=user.id, title="Etwas", category="event",
               date_start=when, date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, location=loc)
    db.add(ev)
    db.flush()
    return ev


def test_candidates_are_prefiltered_in_sql(db, user):
    """Was SQL entscheiden kann, entscheidet SQL: verortet, datiert, nicht in
    der Zukunft. Vorher kamen ALLE Ereignisse in den Speicher und wurden in
    Python aussortiert — bei 12.000 Einträgen der teuerste Teil des Laufs."""
    from app.services.enrichment import _weather_candidates

    wanted = _event(db, user, datetime(2021, 6, 1))
    _event(db, user, datetime(2021, 6, 2), located=False)          # ohne Ort
    _event(db, user, None)                                          # ohne Datum
    _event(db, user, _now() + timedelta(days=30), lat=52.0)  # Zukunft
    db.commit()

    assert [e.id for e in _weather_candidates(db)] == [wanted.id]


def test_todays_events_still_count_as_past(db, user):
    """Die Grenze ist tagesgenau („Zukunft hat noch kein Wetter") — ein
    Ereignis von heute Nachmittag darf der SQL-Vorfilter nicht wegschneiden,
    sonst bekäme der heutige Tag nie Wetter."""
    from app.services.enrichment import _weather_candidates

    today = _event(db, user, _now().replace(hour=23, minute=59))
    db.commit()

    assert [e.id for e in _weather_candidates(db)] == [today.id]


def test_already_enriched_events_drop_out(db, user):
    """Die Revisionsfrage bleibt in Python — sie hängt an den Metriken, nicht
    an einer Spalte. Der Vorfilter darf sie nicht verändern."""
    from app.services.enrichment import WEATHER_REVISION, _weather_candidates

    done = _event(db, user, datetime(2021, 6, 1))
    open_ = _event(db, user, datetime(2021, 6, 2), lat=52.0)
    db.add(Metric(event_id=done.id, key="weather_rev", value=WEATHER_REVISION,
                  source=Source.weather))
    db.add(Metric(event_id=done.id, key="temperature_c", value=21.0,
                  unit="°C", source=Source.weather))
    db.commit()

    assert [e.id for e in _weather_candidates(db)] == [open_.id]
