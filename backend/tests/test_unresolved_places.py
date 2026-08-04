"""Anmerkung 148 — „9 nicht auflösbar" muss sagen, WELCHE neun.

Der gemeldete Fall: ein Lauf meldet „0 Ortsnamen bearbeitet, 9 nicht
auflösbar". Die Zahl stimmt und führt nirgendwohin — nochmal laufen lassen
bringt dieselbe Zahl, weil ein Punkt, den Nominatim nicht kennt, morgen auch
nicht bekannt ist. Der nächste Schritt kann nur Handarbeit sein, und dafür
muss man erst einmal sehen, um welche Orte es geht.

Der zweite Teil ist der wichtigere: ein von Hand gesetzter Name muss den
nächsten Lauf ÜBERLEBEN. Ohne Schutz überschriebe ihn der Geocoder wieder,
sobald er irgendetwas zurückgibt — ausgerechnet dann, wenn er nach einer
Störung wieder erreichbar ist. Das ist kein Randfall, sondern die Kernregel
des Projekts: Maschinen ändern Bestätigtes nie.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import (ConfirmState, DatePrecision, Event, Location, Source)
from app.routers.tracks import (rename_place, resolve_names_batch,
                                unresolved_places)
from app.schemas import PlaceRename
from datetime import datetime


def _place(db, user, name="Ort (51.90, 8.90)", **kw) -> Location:
    loc = Location(user_id=user.id, name=name, lat=51.9, lng=8.9, **kw)
    db.add(loc)
    db.commit()
    return loc


def _visit(db, user, loc) -> Event:
    ev = Event(user_id=user.id, title=f"Besuch: {loc.name}", category="visit",
               location_id=loc.id, date_start=datetime(2024, 5, 1),
               date_precision=DatePrecision.day, source=Source.google_timeline,
               confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.commit()
    return ev


# --------------------------------------------------------------------------- #
# Die Liste
# --------------------------------------------------------------------------- #
def test_the_open_places_are_listed_with_their_reason(db, user):
    loc = _place(db, user)
    _visit(db, user, loc)

    rows = unresolved_places(db=db, user=user)

    assert [r.id for r in rows] == [loc.id]
    assert rows[0].defect == "unnamed"
    assert rows[0].events == 1
    assert rows[0].lat == pytest.approx(51.9)


def test_never_asked_and_asked_in_vain_are_told_apart(db, user):
    """Die Drei-Zustände-Regel, hier als Auskunft an den Nutzer: „noch nicht
    gefragt" ist eine Warteschlange, „gefragt und nichts bekommen" ist
    Handarbeit."""
    fresh = _place(db, user)                       # address IS NULL
    tried = _place(db, user, name="Ort (52.10, 9.10)", address={})

    rows = {r.id: r for r in unresolved_places(db=db, user=user)}

    assert rows[fresh.id].looked_up is False
    assert rows[fresh.id].no_hit is False
    assert rows[tried.id].looked_up is True
    assert rows[tried.id].no_hit is True


def test_a_place_with_a_proper_name_is_not_in_the_list(db, user):
    """Und auch keiner, bei dem nur noch ein FELD fehlt: „Stadt noch nicht
    nachgetragen" ist kein Mangel, der jemanden zur Handarbeit ruft — und es
    wären genug, um die neun, um die es geht, unauffindbar zu machen."""
    _place(db, user, name="Waldweg", city=None, address=None)

    assert unresolved_places(db=db, user=user) == []


# --------------------------------------------------------------------------- #
# Die Handkorrektur
# --------------------------------------------------------------------------- #
def test_renaming_pulls_the_visit_titles_along(db, user):
    loc = _place(db, user)
    ev = _visit(db, user, loc)

    rename_place(loc.id, PlaceRename(name="Waldhütte am See"), db=db, user=user)

    assert db.get(Location, loc.id).name == "Waldhütte am See"
    assert db.get(Event, ev.id).title == "Besuch: Waldhütte am See"


def test_a_hand_written_name_leaves_the_queue(db, user):
    loc = _place(db, user)

    rename_place(loc.id, PlaceRename(name="Waldhütte am See"), db=db, user=user)

    assert unresolved_places(db=db, user=user) == []


def test_a_hand_written_name_survives_the_next_run(db, user, monkeypatch):
    """Der teure Fall: der Geocoder ist wieder da und liefert etwas. Ohne
    Schutzmarke wäre die Handarbeit genau dann weg."""
    from app.services import geocode as geocode_svc

    loc = _place(db, user)
    _visit(db, user, loc)
    rename_place(loc.id, PlaceRename(name="Waldhütte am See"), db=db, user=user)

    # Jetzt antwortet Nominatim — und zwar mit etwas ganz anderem.
    monkeypatch.setattr(geocode_svc, "reverse_geocode", lambda *a, **k: {
        "address": {"road": "Feldweg", "city": "Detmold", "country": "Deutschland"},
        "display_name": "Feldweg, Detmold", "type": "road",
    })
    monkeypatch.setattr(geocode_svc, "short_name", lambda *a, **k: "Feldweg, Detmold")

    resolve_names_batch(db, user, limit=50)

    assert db.get(Location, loc.id).name == "Waldhütte am See"


def test_the_fields_underneath_may_still_be_filled_in(db, user, monkeypatch):
    """Der Name ist eine Aussage und bleibt. Stadt und Land sind Anreicherung
    und dürfen kommen — sie widersprechen nicht, sie ergänzen (Kap. 3.1)."""
    from app.services import geocode as geocode_svc

    loc = _place(db, user)
    rename_place(loc.id, PlaceRename(name="Waldhütte am See"), db=db, user=user)
    monkeypatch.setattr(geocode_svc, "reverse_geocode", lambda *a, **k: {
        "address": {"road": "Feldweg", "city": "Detmold", "country": "Deutschland"},
        "display_name": "Feldweg, Detmold", "type": "road",
    })

    resolve_names_batch(db, user, limit=50)

    back = db.get(Location, loc.id)
    assert back.name == "Waldhütte am See"
    assert back.city == "Detmold"
    assert back.country == "Deutschland"


def test_an_empty_name_is_refused(db, user):
    loc = _place(db, user)
    with pytest.raises(HTTPException) as exc:
        rename_place(loc.id, PlaceRename(name="   "), db=db, user=user)
    assert exc.value.status_code == 400


def test_a_place_of_another_account_is_not_renameable(db, user, other_user):
    loc = _place(db, other_user)
    with pytest.raises(HTTPException) as exc:
        rename_place(loc.id, PlaceRename(name="Meins"), db=db, user=user)
    assert exc.value.status_code == 404


@pytest.fixture
def other_user(db):
    from app.models import User, UserRole
    u = User(oidc_subject="other-places", email="op@example.org", role=UserRole.user)
    db.add(u)
    db.commit()
    return u
