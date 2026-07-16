"""Tests für 0.8.0: A12 (semantische Orte → echte Adressen, min_probability)
und A6 (Nutzerverwaltung). Laufen offline — Reverse-Geocoding wird gemockt."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import ConfirmState, Event, Location, User, UserRole
from app.routers import tracks as tracks_router
from app.routers.admin import delete_user, list_users, update_user_role
from app.routers.tracks import import_timeline, resolve_place_names


# --------------------------------------------------------------------------- #
# Helfer
# --------------------------------------------------------------------------- #
def _device_payload(prob: float = 0.9, semantic: str = "HOME",
                    start: str = "2026-07-01T10:00:00.000+02:00",
                    end: str = "2026-07-01T12:00:00.000+02:00") -> dict:
    """Minimaler Geräte-Export mit einem visit-Segment."""
    return {"semanticSegments": [{
        "startTime": start, "endTime": end,
        "visit": {
            "probability": prob,
            "topCandidate": {
                "placeId": "pid-home",
                "semanticType": semantic,
                "placeLocation": {"latLng": "51.94°, 8.87°"},
            },
        },
    }]}


@pytest.fixture()
def fake_reverse(monkeypatch):
    """Ersetzt Nominatim-Reverse-Geocoding; ohne Drossel-Wartezeit."""
    monkeypatch.setattr(tracks_router, "NOMINATIM_DELAY_S", 0)
    monkeypatch.setattr(
        tracks_router.geocode_svc, "reverse_geocode",
        lambda lat, lng: {"name": "Musterstraße 1, 32756 Detmold, Deutschland",
                          "type": "house"},
    )


# --------------------------------------------------------------------------- #
# A12 — Import: semantische Orte & min_probability
# --------------------------------------------------------------------------- #
def test_import_semantic_visit(db, user):
    result = import_timeline(_device_payload(), auto_resolve=False, db=db, user=user)
    assert result.visits_created == 1
    # Semantisches Label zählt als "noch unaufgelöst" (A12)
    assert result.locations_unnamed == 1
    loc = db.query(Location).one()
    assert loc.name == "Zuhause"
    assert loc.type == "home"
    ev = db.query(Event).one()
    assert ev.title == "Besuch: Zuhause"
    assert ev.confirmed == ConfirmState.confirmed


def test_import_min_probability_filters(db, user):
    result = import_timeline(_device_payload(prob=0.35), auto_resolve=False,
                             min_probability=0.6, db=db, user=user)
    assert result.visits_created == 0
    assert result.skipped_low_probability == 1
    assert result.skipped_invalid == 0  # unsicher ≠ unlesbar
    assert db.query(Event).count() == 0


def test_import_min_probability_keeps_confident(db, user):
    result = import_timeline(_device_payload(prob=0.8), auto_resolve=False,
                             min_probability=0.6, db=db, user=user)
    assert result.visits_created == 1
    assert result.skipped_low_probability == 0


# --------------------------------------------------------------------------- #
# A12 — Auflösung: Label bleibt Präfix, Typ bleibt, Overrides geschützt
# --------------------------------------------------------------------------- #
def test_resolve_semantic_keeps_label_prefix(db, user, fake_reverse):
    import_timeline(_device_payload(), auto_resolve=False, db=db, user=user)
    result = resolve_place_names(limit=10, scope="unnamed", db=db, user=user)
    assert result.resolved == 1 and result.remaining == 0

    loc = db.query(Location).one()
    assert loc.name == "Zuhause — Musterstraße 1, 32756 Detmold, Deutschland"
    assert loc.type == "home"  # Typ wird vom Geocoder NICHT überschrieben
    ev = db.query(Event).one()
    assert ev.title == "Besuch: Zuhause — Musterstraße 1"


def test_resolve_is_idempotent(db, user, fake_reverse):
    """Ein bereits aufgelöster Ort („Label — Adresse") ist kein Kandidat mehr."""
    import_timeline(_device_payload(), auto_resolve=False, db=db, user=user)
    resolve_place_names(limit=10, scope="unnamed", db=db, user=user)
    again = resolve_place_names(limit=10, scope="unnamed", db=db, user=user)
    assert again.resolved == 0 and again.remaining == 0


def test_resolve_protects_manual_title(db, user, fake_reverse):
    import_timeline(_device_payload(), auto_resolve=False, db=db, user=user)
    ev = db.query(Event).one()
    ev.title = "Mein Zuhause-Besuch"
    ev.field_overrides = {"title": True}
    db.commit()

    resolve_place_names(limit=10, scope="unnamed", db=db, user=user)
    db.refresh(ev)
    assert ev.title == "Mein Zuhause-Besuch"  # manuell umbenannt -> unantastbar


def test_resolve_coordinate_names_unchanged_behaviour(db, user, fake_reverse):
    """Koordinaten-Namen („Ort (lat, lng)") funktionieren weiter wie bisher."""
    payload = _device_payload(semantic="UNKNOWN")
    import_timeline(payload, auto_resolve=False, db=db, user=user)
    loc = db.query(Location).one()
    assert loc.name.startswith("Ort (")

    resolve_place_names(limit=10, scope="unnamed", db=db, user=user)
    db.refresh(loc)
    assert loc.name == "Musterstraße 1, 32756 Detmold, Deutschland"
    assert loc.type == "house"  # ohne Label übernimmt der Geocoder-Typ
    assert db.query(Event).one().title == "Besuch: Musterstraße 1"


# --------------------------------------------------------------------------- #
# A6 — Nutzerverwaltung
# --------------------------------------------------------------------------- #
def test_list_users_with_counts(db, user):
    import_timeline(_device_payload(), auto_resolve=False, db=db, user=user)
    rows = list_users(db=db)
    assert len(rows) == 1
    assert rows[0]["role"] == "admin"
    assert rows[0]["events"] == 1
    assert rows[0]["fragments"] == 1  # der Import-Sammelbeleg (Stufe 1)


def test_last_admin_cannot_be_demoted(db, user):
    with pytest.raises(HTTPException) as exc:
        update_user_role(user.id, role=UserRole.user, db=db)
    assert exc.value.status_code == 400
    assert db.get(User, user.id).role == UserRole.admin


def test_role_change_with_second_admin(db, user):
    other = User(oidc_subject="other-sub", email="other@example.org",
                 role=UserRole.admin)
    db.add(other)
    db.commit()
    result = update_user_role(other.id, role=UserRole.user, db=db)
    assert result["role"] == "user"


def test_delete_user_removes_account_and_data(db, user):
    other = User(oidc_subject="other-sub", email="other@example.org")
    db.add(other)
    db.commit()
    import_timeline(_device_payload(), auto_resolve=False, db=db, user=other)
    assert db.query(Event).filter(Event.user_id == other.id).count() == 1

    result = delete_user(other.id, admin=user, db=db)
    assert result["deleted"]["events"] == 1
    assert db.get(User, other.id) is None
    assert db.query(Event).filter(Event.user_id == other.id).count() == 0
    assert db.query(Location).filter(Location.user_id == other.id).count() == 0


def test_delete_own_account_blocked(db, user):
    with pytest.raises(HTTPException) as exc:
        delete_user(user.id, admin=user, db=db)
    assert exc.value.status_code == 400
    assert db.get(User, user.id) is not None
