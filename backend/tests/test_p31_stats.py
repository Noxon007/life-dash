"""Tests für 0.30.0: P3.1 — deklarative Statistik-Widgets aus den Modul-YAMLs."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Source, User, UserRole)
from app.services.stats import compute_widgets


@pytest.fixture(autouse=True)
def modules(modules_loaded):
    """Registry ist geladen (Fixture aus conftest)."""
    return modules_loaded


def _event(db, user, category, when=datetime(2024, 5, 1), confirmed=True) -> Event:
    e = Event(user_id=user.id, title="x", category=category, date_start=when,
              date_precision=DatePrecision.day, source=Source.manual,
              confirmed=ConfirmState.confirmed if confirmed else ConfirmState.unconfirmed)
    db.add(e)
    db.commit()
    return e


def _entity(db, user, etype, name, attrs=None, confirmed=True) -> Entity:
    ent = Entity(user_id=user.id, type=etype, name=name, attributes=attrs or {},
                 confirmed=ConfirmState.confirmed if confirmed else ConfirmState.unconfirmed)
    db.add(ent)
    db.commit()
    return ent


def _widget(widgets, wid):
    return next((w for w in widgets if w["id"] == wid), None)


# --------------------------------------------------------------------------- #
# Die drei Typen
# --------------------------------------------------------------------------- #
def test_count_counts_confirmed_events_in_category(db, user):
    _event(db, user, "milestone")
    _event(db, user, "milestone")
    _event(db, user, "milestone", confirmed=False)   # Vorschlag zählt nicht
    w = _widget(compute_widgets(db, user.id), "milestones_count")
    assert w is not None and w["type"] == "count" and w["value"] == 2


def test_count_distinct_by_name(db, user):
    _entity(db, user, "game", "Zelda")
    _entity(db, user, "game", "zelda")               # gleiche Schreibweise -> 1
    _entity(db, user, "game", "Elden Ring")
    w = _widget(compute_widgets(db, user.id), "game_count")
    assert w is not None and w["value"] == 2


def test_count_distinct_by_attribute(db, user):
    # animal: species_count zählt entity.species (Attribut)
    _entity(db, user, "animal", "Seeadler", {"species": "Adler"})
    _entity(db, user, "animal", "Steinadler", {"species": "adler"})   # gleiche Art
    _entity(db, user, "animal", "Rotkehlchen", {"species": "Rotkehlchen"})
    w = _widget(compute_widgets(db, user.id), "species_count")
    assert w is not None and w["value"] == 2


def test_timeseries_counts_events_per_year(db, user):
    _event(db, user, "trip", datetime(2022, 6, 1))
    _event(db, user, "trip", datetime(2024, 6, 1))
    _event(db, user, "trip", datetime(2024, 8, 1))
    w = _widget(compute_widgets(db, user.id), "trips_per_year")
    assert w is not None and w["type"] == "timeseries"
    assert w["series"] == {"2022": 1, "2024": 2}
    assert w["value"] == 3            # Summe als Kennzahl


# --------------------------------------------------------------------------- #
# Leere Widgets fallen heraus, Vorschläge zählen nicht, Nutzertrennung
# --------------------------------------------------------------------------- #
def test_empty_widgets_are_omitted(db, user):
    """Ohne Daten keine „0"-Kachel — das wäre nur Rauschen."""
    assert compute_widgets(db, user.id) == []


def test_unconfirmed_entities_do_not_count(db, user):
    _entity(db, user, "game", "Nur Vorschlag", confirmed=False)
    assert _widget(compute_widgets(db, user.id), "game_count") is None


def test_widgets_are_scoped_to_the_user(db, user):
    other = User(oidc_subject="other-stats", email="os@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    _entity(db, other, "game", "Fremd")
    assert compute_widgets(db, user.id) == []


# --------------------------------------------------------------------------- #
# Tracking (A15) wird respektiert
# --------------------------------------------------------------------------- #
def test_untracked_modules_are_skipped(db, user):
    _entity(db, user, "game", "Zelda")
    _event(db, user, "milestone")
    # Nur „milestone" tracken -> game-Widget fällt weg
    user.settings = {"tracked_modules": ["milestone"]}
    db.commit()
    ids = {w["id"] for w in compute_widgets(db, user.id)}
    assert "milestones_count" in ids
    assert "game_count" not in ids


# --------------------------------------------------------------------------- #
# Neues Modul bringt seine Statistik allein durch das YAML mit (der Kern von P3.1)
# --------------------------------------------------------------------------- #
def test_new_module_widget_appears_without_frontend_change(db, user):
    """game/movie/book hatten bis 0.30.0 keine Statistik — jetzt schon,
    allein durch den statistics-Block im YAML."""
    _entity(db, user, "movie", "Oppenheimer")
    _entity(db, user, "book", "Der Steppenwolf")
    ids = {w["id"] for w in compute_widgets(db, user.id)}
    assert {"movie_count", "book_count"} <= ids
