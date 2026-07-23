"""Tests für 0.21.0: A28 (ein Ortsnamen-Lauf statt Scope-Auswahl) und
F14 („An diesem Tag"). Offline — kein Geocoding, keine Netzaufrufe."""
from __future__ import annotations

from datetime import date, datetime

from app.models import ConfirmState, DatePrecision, Event, Location, Source
from app.routers.events import on_this_day
from app.routers.tracks import _name_defect, _resolve_candidates


def _loc(db, user, name: str, lat=53.5, lng=10.0) -> Location:
    l = Location(user_id=user.id, name=name, lat=lat, lng=lng)
    db.add(l)
    db.commit()
    return l


def _ev(db, user, title, start, end=None,
        precision=DatePrecision.day, parent=None) -> Event:
    e = Event(user_id=user.id, title=title, category="trip",
              date_start=start, date_end=end, date_precision=precision,
              confirmed=ConfirmState.confirmed, confirmed_by="manual",
              source=Source.manual, parent_event_id=parent)
    db.add(e)
    db.commit()
    return e


# --------------------------------------------------------------------------- #
# A28 — ein Lauf für alle Mängel
# --------------------------------------------------------------------------- #
PARTS = ["road", "city", "country"]      # erlaubt max. 2 Kommas


def test_name_defect_recognises_each_class():
    assert _name_defect("Ort (53.4900, 10.0000)", PARTS) == "unnamed"
    assert _name_defect("Zuhause", PARTS) == "unnamed"
    assert _name_defect("Οδός Ερμού, Αθήνα", PARTS) == "nonlatin"
    assert _name_defect("A, B, C, D, E", PARTS) == "verbose"
    assert _name_defect("Musterstraße 1, Hamburg, Deutschland", PARTS) is None


def test_name_defect_prefers_unnamed_over_others():
    """Reihenfolge zählt: ein Platzhalter wird als 'unnamed' gemeldet, auch
    wenn er formal auch zu lang wäre — er wird ohnehin komplett neu geholt."""
    assert _name_defect("Ort (1, 2), x, y, z", PARTS) == "unnamed"


def test_name_defect_old_label_is_a_cut_not_a_lookup():
    """Anmerkung 114: „Zuhause — Adresse" hat keinen Mangel, den ein Geocoder
    beheben könnte — nur ein Präfix zu viel. Eigene Klasse, damit der Lauf sie
    ohne Abruf erledigen kann."""
    assert _name_defect("Zuhause — Musterstraße 1, Hamburg, Deutschland",
                        PARTS) == "labeled"
    assert _name_defect("Arbeit", PARTS) == "unnamed"


def test_named_place_with_poi_is_not_forever_verbose():
    """Anmerkung 114: `short_name` stellt den Eigennamen eines POI VOR die
    Bausteine — der Name hat damit ein Komma mehr, als das Format zulässt.
    Nach reinem Komma-Zählen galt jeder benannte Ort für immer als zu lang,
    wurde bei jedem Lauf neu geocodet, kam unverändert zurück und blieb in der
    offenen Menge: die Endlos-Abruf-Falle zum fünften Mal (F12/A39/A42/P2.1).
    Mit den gespeicherten Bausteinen ist es keine Schätzung mehr."""
    addr = {"road": "Kaiserstraße", "house_number": "1", "city": "Detmold",
            "country": "Deutschland", "poi": "Café Central"}
    name = "Café Central, Kaiserstraße 1, Detmold, Deutschland"
    assert name.count(",") > len(PARTS) - 1        # das Komma-Zählen irrt sich
    assert _name_defect(name, PARTS, addr) is None  # die Rechnung nicht
    # Und ein Name, der wirklich nicht zum Format passt, fällt weiter auf
    assert _name_defect("Kaiserstraße 1, Detmold", PARTS, addr) == "verbose"


def test_candidates_are_deduplicated_and_unnamed_first(db, user):
    """Der Kern von A28: ein Ort mit mehreren Mängeln steht genau EINMAL in
    der Liste — vorher wurde er pro Scope-Lauf erneut geocodiert.

    Angepasst in 0.34 (A39): „fertig" heißt seither Name **und** Stadt. Der
    Lauf zieht auch Orte nach, deren Name stimmt, denen aber die Stadt fehlt —
    das Feld gab es vorher nicht. `fine` trägt hier deshalb eine Stadt; ohne
    sie wäre der Ort zu Recht Kandidat. Dass er dann genau einmal geholt wird
    und nicht bei jedem Lauf erneut, prüft `test_a39_city.py`.
    """
    greek_and_long = _loc(db, user, "Οδός Ερμού, Αθήνα, Αττική, Ελλάδα, EU")
    unnamed = _loc(db, user, "Ort (53.4900, 10.0000)")
    fine = _loc(db, user, "Musterstraße 1, Hamburg, Deutschland")
    fine.city = "Hamburg"
    greek_and_long.city = "Αθήνα"
    unnamed.city = ""
    db.flush()

    cands = _resolve_candidates(db, user.id, PARTS)
    ids = [c.id for c in cands]

    assert ids.count(greek_and_long.id) == 1     # nicht doppelt
    assert fine.id not in ids                    # fertige Orte bleiben unangetastet
    assert ids[0] == unnamed.id                  # „unnamed" zuerst
    assert set(ids) == {unnamed.id, greek_and_long.id}


def test_candidates_ignore_locations_without_coordinates(db, user):
    """Ohne Koordinaten gibt es nichts zum Rückwärts-Geocodieren."""
    l = Location(user_id=user.id, name="Ort (1, 2)", lat=None, lng=None)
    db.add(l)
    db.commit()
    assert _resolve_candidates(db, user.id, PARTS) == []


def test_candidates_are_scoped_to_the_user(db, user):
    from app.models import User, UserRole
    other = User(oidc_subject="other", email="o@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    _loc(db, other, "Ort (9, 9)")
    assert _resolve_candidates(db, user.id, PARTS) == []


# --------------------------------------------------------------------------- #
# F14 — „An diesem Tag"
# --------------------------------------------------------------------------- #
TODAY = date(2026, 7, 20)


def test_on_this_day_groups_by_year(db, user):
    _ev(db, user, "Vor einem Jahr", datetime(2025, 7, 20))
    _ev(db, user, "Vor fünf Jahren", datetime(2021, 7, 20))
    _ev(db, user, "Anderer Tag", datetime(2025, 7, 19))

    groups = on_this_day(db=db, user=user, date=TODAY)

    assert [g.years_ago for g in groups] == [1, 5]
    assert [e.title for e in groups[0].events] == ["Vor einem Jahr"]
    assert groups[0].date == date(2025, 7, 20)


def test_on_this_day_excludes_today_itself(db, user):
    """Was heute passiert ist, steht im Zeitstrahl — nicht im Rückblick."""
    _ev(db, user, "Heute", datetime(2026, 7, 20))
    assert on_this_day(db=db, user=user, date=TODAY) == []


def test_on_this_day_matches_spanning_events(db, user):
    """„Du warst an diesem Tag vor 5 Jahren auf Mallorca" — der Tag muss den
    Zeitraum treffen, nicht nur dessen Beginn."""
    _ev(db, user, "Mallorca", datetime(2021, 7, 15), datetime(2021, 7, 25))
    groups = on_this_day(db=db, user=user, date=TODAY)
    assert [e.title for e in groups[0].events] == ["Mallorca"]


def test_on_this_day_ignores_vague_precisions(db, user):
    """Bei Monats-/Jahresgenauigkeit ist der Tag unbekannt — „heute vor N
    Jahren" wäre eine Behauptung, die die Daten nicht hergeben."""
    _ev(db, user, "Juni-Urlaub", datetime(2021, 7, 20),
        precision=DatePrecision.month)
    _ev(db, user, "Irgendwann 2021", datetime(2021, 7, 20),
        precision=DatePrecision.year)
    assert on_this_day(db=db, user=user, date=TODAY) == []


def test_on_this_day_prefers_day_child_over_parent(db, user):
    """F7: Eltern und Tages-Kind sind dieselbe Erinnerung — nur das Kind zeigen."""
    parent = _ev(db, user, "Mallorca", datetime(2021, 7, 15), datetime(2021, 7, 25))
    _ev(db, user, "Mallorca — Tag 6", datetime(2021, 7, 20), parent=parent.id)

    groups = on_this_day(db=db, user=user, date=TODAY)
    assert [e.title for e in groups[0].events] == ["Mallorca — Tag 6"]


def test_on_this_day_respects_max_years(db, user):
    _ev(db, user, "Lange her", datetime(1996, 7, 20))
    assert on_this_day(db=db, user=user, date=TODAY, max_years=10) == []
    assert len(on_this_day(db=db, user=user, date=TODAY, max_years=50)) == 1


def test_on_this_day_is_scoped_to_the_user(db, user):
    from app.models import User, UserRole
    other = User(oidc_subject="other2", email="o2@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    _ev(db, other, "Fremde Erinnerung", datetime(2025, 7, 20))
    assert on_this_day(db=db, user=user, date=TODAY) == []
