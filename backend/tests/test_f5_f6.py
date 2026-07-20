"""Tests für 0.18.0: F5 (Welt-Reiter) und F6 (Achievements). Offline."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.data import countries as ref
from app.models import ConfirmState, Entity, Event, EventEntityLink
from app.routers.world import world
from app.services.achievements import compute


def _country(db, user, name, confirmed=True):
    entity = Entity(user_id=user.id, type="country", name=name,
                    confirmed=ConfirmState.confirmed if confirmed
                    else ConfirmState.unconfirmed)
    db.add(entity)
    db.flush()
    return entity


def _visit(db, user, entity, when, confirmed=True):
    ev = Event(user_id=user.id, title=f"Besuch {entity.name}", date_start=when,
               confirmed=ConfirmState.confirmed if confirmed
               else ConfirmState.unconfirmed)
    db.add(ev)
    db.flush()
    db.add(EventEntityLink(event_id=ev.id, entity_id=entity.id, role="mentioned"))
    db.flush()
    return ev


# --------------------------------------------------------------------------- #
# Länder-Stammdaten — die Brücke zwischen Entity-Namen und Karte
# --------------------------------------------------------------------------- #
def test_resolve_matches_german_english_alias_and_iso():
    assert ref.resolve("Deutschland").iso == "DE"
    assert ref.resolve("Germany").iso == "DE"
    assert ref.resolve("USA").iso == "US"
    assert ref.resolve("DE").iso == "DE"
    # Umlaute/Akzente dürfen fehlen — Quellen schreiben mal so, mal so
    assert ref.resolve("Osterreich").iso == "AT"
    assert ref.resolve("Türkei").iso == "TR"
    assert ref.resolve("  ägypten ").iso == "EG"
    assert ref.resolve("Atlantis") is None
    assert ref.resolve(None) is None
    assert ref.resolve("") is None


def test_every_geojson_country_has_reference_data():
    """Sonst bliebe eine Fläche auf der Karte grau, obwohl man dort war."""
    path = Path(__file__).resolve().parents[2] / "frontend" / "world-countries.geojson"
    geo = json.loads(path.read_text(encoding="utf-8"))
    iso_on_map = {f["properties"]["iso"] for f in geo["features"]}
    assert iso_on_map, "GeoJSON enthält keine Länder"
    assert not (iso_on_map - set(ref.BY_ISO)), "Karte kennt Länder ohne Stammdaten"


def test_by_continent_covers_all_countries_once():
    per = ref.by_continent()
    assert set(per) == set(ref.CONTINENTS)
    assert sum(len(v) for v in per.values()) == len(ref.BY_ISO)


# --------------------------------------------------------------------------- #
# F5 — Welt-Endpoint
# --------------------------------------------------------------------------- #
def test_world_aggregates_visits_per_continent(db, user):
    de = _country(db, user, "Deutschland")
    _visit(db, user, de, datetime(2020, 5, 1))
    _visit(db, user, de, datetime(2022, 8, 3))
    jp = _country(db, user, "Japan")
    _visit(db, user, jp, datetime(2024, 3, 9))
    db.commit()

    result = world(db=db, user=user)
    assert result.countries_visited == 2
    assert result.continents_visited == 2
    assert result.countries_total == len(ref.BY_ISO)

    europe = next(c for c in result.continents if c.code == "EU")
    germany = next(c for c in europe.countries if c.iso == "DE")
    assert germany.event_count == 2
    assert germany.first_visit == datetime(2020, 5, 1)
    assert germany.last_visit == datetime(2022, 8, 3)
    assert "Frankreich" in europe.missing and "Deutschland" not in europe.missing
    assert europe.visited + len(europe.missing) == europe.total

    # „Zuletzt neu besucht" sortiert nach dem ERSTEN Besuch
    assert [c.iso for c in result.recent] == ["JP", "DE"]


def test_world_merges_aliases_of_same_country(db, user):
    """„USA" und „Vereinigte Staaten" sind ein Land, nicht zwei."""
    a = _country(db, user, "USA")
    b = _country(db, user, "Vereinigte Staaten")
    _visit(db, user, a, datetime(2019, 1, 1))
    _visit(db, user, b, datetime(2021, 1, 1))
    db.commit()

    result = world(db=db, user=user)
    assert result.countries_visited == 1
    america = next(c for c in result.continents if c.code == "NA")
    usa = next(c for c in america.countries if c.iso == "US")
    assert usa.event_count == 2
    assert usa.first_visit == datetime(2019, 1, 1)


def test_world_ignores_unconfirmed_and_reports_unknown_names(db, user):
    """Vorschläge färben die Karte nicht ein; Unbekanntes wird sichtbar."""
    proposal = _country(db, user, "Japan", confirmed=False)
    _visit(db, user, proposal, datetime(2024, 1, 1), confirmed=False)
    _country(db, user, "Absurdistan")
    db.commit()

    result = world(db=db, user=user)
    assert result.countries_visited == 0
    assert result.unmatched == ["Absurdistan"]


def test_world_is_per_user(db, user):
    from app.models import User, UserRole
    other = User(oidc_subject="other", email="o@example.org",
                 display_name="Andere", role=UserRole.user)
    db.add(other)
    db.flush()
    mine = _country(db, user, "Italien")
    _visit(db, user, mine, datetime(2023, 6, 1))
    theirs = _country(db, other, "Brasilien")
    _visit(db, other, theirs, datetime(2023, 6, 1))
    db.commit()

    assert {c.iso for cont in world(db=db, user=user).continents
            for c in cont.countries} == {"IT"}
    assert {c.iso for cont in world(db=db, user=other).continents
            for c in cont.countries} == {"BR"}


# --------------------------------------------------------------------------- #
# F6 — Achievements
# --------------------------------------------------------------------------- #
def test_achievement_tiers_and_progress(db, user):
    """Weltenbummler: Bronze ab 3, Silber ab 10 — bei 5 Ländern also Bronze."""
    for name in ("Deutschland", "Japan", "Italien", "Spanien", "Portugal"):
        _country(db, user, name)
    db.commit()

    globetrotter = next(a for a in compute(db, user.id).achievements
                        if a.id == "globetrotter")
    assert globetrotter.value == 5
    assert globetrotter.tier == "bronze"
    assert globetrotter.tier_index == 1
    assert globetrotter.next_tier == "silber"
    assert globetrotter.next_threshold == 10
    # Fortschritt zählt ab der erreichten Stufe (3), nicht ab null
    assert globetrotter.progress == (5 - 3) / (10 - 3)


def test_globetrotter_matches_the_world_map(db, user):
    """Der Erfolg muss dieselbe Zahl nennen wie der Welt-Reiter — sonst zählt
    die Karte 6 Länder und das Abzeichen 8 (Aliasse und Unbekanntes)."""
    for name in ("Deutschland", "Italien", "Japan", "Vereinigte Staaten",
                 "USA", "Ägypten", "Australien", "Absurdistan"):
        _country(db, user, name)
    db.commit()

    on_map = world(db=db, user=user).countries_visited
    globetrotter = next(a for a in compute(db, user.id).achievements
                        if a.id == "globetrotter")
    assert on_map == 6
    assert globetrotter.value == on_map


def test_achievement_below_first_tier_is_locked(db, user):
    _country(db, user, "Deutschland")
    db.commit()
    globetrotter = next(a for a in compute(db, user.id).achievements
                        if a.id == "globetrotter")
    assert globetrotter.tier is None
    assert globetrotter.tier_index == 0
    assert globetrotter.progress == 1 / 3


def test_achievement_top_tier_has_no_next(db, user):
    """Kontinent-Springer: Platin bei 7 von 7 Kontinenten."""
    for name in ("Deutschland", "Japan", "Ägypten", "Brasilien",
                 "Vereinigte Staaten", "Australien", "Antarktis"):
        _country(db, user, name)
    db.commit()

    hopper = next(a for a in compute(db, user.id).achievements
                  if a.id == "continent_hopper")
    assert hopper.value == 7
    assert hopper.tier == "platin"
    assert hopper.next_tier is None
    assert hopper.progress == 1.0


def test_achievements_count_only_confirmed(db, user):
    for name in ("Deutschland", "Japan", "Italien"):
        _country(db, user, name, confirmed=False)
    db.commit()
    globetrotter = next(a for a in compute(db, user.id).achievements
                        if a.id == "globetrotter")
    assert globetrotter.value == 0
    assert globetrotter.tier is None


def test_event_metric_counts_confirmed_events_of_category(db, user):
    for i in range(4):
        db.add(Event(user_id=user.id, title=f"Konzert {i}", category="concert",
                     confirmed=ConfirmState.confirmed))
    db.add(Event(user_id=user.id, title="Vorschlag", category="concert",
                 confirmed=ConfirmState.unconfirmed))
    db.commit()

    concerts = next(a for a in compute(db, user.id).achievements
                    if a.id == "concert_goer")
    assert concerts.value == 4
    assert concerts.tier == "bronze"


def test_achievements_respect_tracked_modules(db, user):
    """A15: Abgewählte Module tauchen auch bei den Erfolgen nicht auf."""
    _country(db, user, "Deutschland")
    user.settings = {"tracked_modules": ["animal"]}
    db.commit()

    modules = {a.module for a in compute(db, user.id).achievements}
    assert modules == {"animal"}


def test_achievements_summary_counts_points(db, user):
    for name in ("Deutschland", "Japan", "Italien"):
        _country(db, user, name)
    db.commit()

    result = compute(db, user.id)
    assert result.total == len(result.achievements)
    # Weltenbummler Bronze (3 Länder) + Kontinent-Springer Bronze (2 Kontinente)
    assert result.earned == 2
    assert result.points == 2
