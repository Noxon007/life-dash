"""Die Naht zwischen SQL-Vorfilter und `_needs_weather` (Release-Durchsicht).

`_weather_candidates` läuft VOR JEDEM 25er-Stapel. Bis zur Durchsicht holte die
Abfrage jedes verortete, datierte Ereignis samt Metriken und ließ erst Python
entscheiden, ob es Wetter braucht — die Trefferzahl schrumpfte mit jedem
Stapel, die geholte Menge nicht. Gemessen (Anmerkung 219): 396 ms bei 2.000
fertigen Ereignissen, 1.321 ms bei 5.000, 2.979 ms bei 10.000. Über einen
Rückstandslauf ist das quadratisch.

Die Revisionsfrage steht jetzt als `NOT EXISTS` in der Abfrage. Damit gibt es
sie an ZWEI Orten — und das ist die Falle, gegen die dieses Projekt sonst
antritt. Geprüft wird deshalb nicht „ist es schnell", sondern **dass beide
Orte dieselbe Menge meinen**: für jeden Bestand muss

    _weather_candidates(db)  ==  [e for e in alle if _needs_weather(e)]

gelten. Ein Test je Hälfte würde genau den Fall verfehlen, der wehtut — die
Hälften sind einzeln richtig, der Defekt läge DAZWISCHEN.

Offline: keine Open-Meteo-Abrufe, es wird nur ausgewählt.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.models import ConfirmState, Event, Location, Metric, Source
from app.services.enrichment import (WEATHER_REVISION, _needs_weather,
                                     _weather_candidates)
from app.services.weather import ERA5_LAG_DAYS


def _day(offset_days: int) -> datetime:
    """Ein Tag, gemessen an heute — `offset_days` negativ = Vergangenheit."""
    base = datetime.now(timezone.utc).date() + timedelta(days=offset_days)
    return datetime(base.year, base.month, base.day, 12, 0)


def _event(db, user, title, *, when, located=True) -> Event:
    loc = None
    if located:
        loc = Location(user_id=user.id, name=title, lat=51.94, lng=8.88)
        db.add(loc)
        db.flush()
    ev = Event(user_id=user.id, title=title, category="trip", date_start=when,
               location=loc, source=Source.manual,
               confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.commit()
    return ev


def _weather(db, event, *, rev: float | None, extra: bool = True) -> None:
    """Wetter an ein Ereignis hängen. `rev=None` = Metriken ohne Marke."""
    if extra:
        db.add(Metric(event_id=event.id, key="temperature_c", value=12.0,
                      unit="°C", source=Source.weather))
    if rev is not None:
        db.add(Metric(event_id=event.id, key="weather_rev", value=rev,
                      source=Source.weather))
    db.commit()


@pytest.fixture()
def stock(db, user) -> dict[str, Event]:
    """Ein Bestand, der jede Zeile der Wahrheitstabelle trifft — und die
    Ränder, an denen ein Vorfilter gern zu viel wegnimmt."""
    made = {
        # --- braucht Wetter ---
        "blank": _event(db, user, "blank", when=_day(-400)),
        "no_mark": _event(db, user, "no_mark", when=_day(-400)),
        "old_mark": _event(db, user, "old_mark", when=_day(-400)),
        # --- braucht keins ---
        "current": _event(db, user, "current", when=_day(-400)),
        "newer_mark": _event(db, user, "newer_mark", when=_day(-400)),
        # --- fällt aus anderen Gründen weg ---
        "unlocated": _event(db, user, "unlocated", when=_day(-400),
                            located=False),
        "undated": _event(db, user, "undated", when=None),
        "future": _event(db, user, "future", when=_day(+30)),
        # --- die Ränder der Archivgrenze (Anmerkung 186) ---
        "too_recent": _event(db, user, "too_recent",
                             when=_day(-ERA5_LAG_DAYS + 1)),
        "just_old_enough": _event(db, user, "just_old_enough",
                                  when=_day(-ERA5_LAG_DAYS)),
    }
    _weather(db, made["no_mark"], rev=None)
    _weather(db, made["old_mark"], rev=WEATHER_REVISION - 1)
    _weather(db, made["current"], rev=WEATHER_REVISION)
    _weather(db, made["newer_mark"], rev=WEATHER_REVISION + 1)
    return made


def test_the_prefilter_and_the_rule_pick_the_same_events(db, user, stock):
    """Die eine Zusage: SQL nimmt genau das weg, was `_needs_weather` ablehnt."""
    by_rule = {e.id for e in db.query(Event).all() if _needs_weather(e)}
    by_sql = {e.id for e in _weather_candidates(db)}

    assert by_sql == by_rule


def test_it_picks_the_four_that_need_weather(db, user, stock):
    """Und dass die Menge auch die richtige ist — die Probe darauf, dass die
    Prüfung oben nicht zwei identisch falsche Hälften vergleicht."""
    got = {e.title for e in _weather_candidates(db)}

    assert got == {"blank", "no_mark", "old_mark", "just_old_enough"}


def test_a_finished_stock_costs_no_rows(db, user, stock):
    """Der eigentliche Grund für den Umbau — und der Grund, aus dem dieser Test
    NICHT die Rückgabe prüft.

    Die Rückgabe war schon vorher leer: Python filterte die fertigen
    Ereignisse ja weg. Teuer war, dass sie vorher GEHOLT wurden, samt
    Metriken, vor jedem einzelnen Stapel. Ein Test auf `== []` wäre gegen den
    alten Stand grün gewesen und hätte damit genau nichts über den Umbau
    gesagt.

    Beobachtet wird deshalb, WAS AN DIE DATENBANK GING. Die Metriken hängen
    über `selectinload` an der Ereignis-Abfrage: liefert die keine Zeile, gibt
    es die zweite Anweisung gar nicht erst. Genau das ist der Unterschied
    zwischen den beiden Ständen — und die Identitätskarte taugt nicht dafür,
    sie hält nur schwache Verweise und ist nach dem Aufruf ohnehin leer.
    """
    for ev in db.query(Event).all():
        if ev.location_id and ev.date_start:
            db.query(Metric).filter(Metric.event_id == ev.id).delete()
            _weather(db, ev, rev=WEATHER_REVISION)
    db.expunge_all()

    seen: list[str] = []

    def _record(conn, cursor, statement, params, context, many):
        seen.append(" ".join(statement.split()).lower())

    event.listen(db.get_bind(), "before_cursor_execute", _record)
    try:
        assert _weather_candidates(db) == []
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _record)

    # Gemeint ist die NACHLADE-Anweisung von `selectinload`, die mit
    # „select metrics." beginnt — nicht die `NOT EXISTS`-Unterabfrage, die
    # „from metrics" ebenfalls enthält und gerade der Grund ist, warum es die
    # erste nicht mehr gibt.
    loaded = [s for s in seen if s.startswith("select metrics.")]
    assert loaded == [], (
        "Metriken fertiger Ereignisse geholt, um sie zu verwerfen — genau die "
        f"Arbeit, die den Rückstandslauf quadratisch machte: {len(loaded)}")


def test_the_account_filter_still_holds(db, user, other_user, stock):
    """Anmerkung 115: der Knopf eines Nutzers fasst fremde Ereignisse nicht an.
    Der neue Vorfilter darf diese Hälfte nicht mitreißen."""
    theirs = _event(db, other_user, "fremd", when=_day(-400))

    mine = {e.id for e in _weather_candidates(db, user_id=user.id)}

    assert theirs.id not in mine
    assert theirs.id in {e.id for e in _weather_candidates(db)}


@pytest.fixture()
def other_user(db):
    from app.models import User, UserRole
    u = User(oidc_subject="cand-sub", email="cand@example.org",
             display_name="Zweite", role=UserRole.user)
    db.add(u)
    db.commit()
    return u
