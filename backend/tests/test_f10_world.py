"""F10-Rest — der Welt-Reiter war deutsch verdrahtet.

`world.py` nahm `name_de`, und die Kontinent-Namen kamen als deutscher Text aus
`data/countries.py` und hatten im Frontend keinen Katalog-Eintrag. Eine
englische Oberfläche zeigte also „Nordamerika" über einer Liste, in der
„Deutschland" und „Vereinigte Staaten" standen — und zwar still: es war nichts
kaputt, es war nur nicht übersetzt.

**Beide Hälften gehören zusammen**, sonst ergäbe die eine allein einen halb
übersetzten Reiter — genau der Zustand, der nicht wie eine Lücke aussieht,
sondern wie ein Fehler (Anmerkung 114).
"""
from __future__ import annotations

from datetime import datetime

from app.data import countries as ref
from app.models import ConfirmState, Entity, Event, EventEntityLink
from app.routers.stats import toplists
from app.routers.world import world
from app.services import geocode as geo


def _visited(db, user, name, when=datetime(2020, 5, 1)):
    """Ein bestätigtes Land mit einem bestätigten Besuch."""
    entity = Entity(user_id=user.id, type="country", name=name,
                    confirmed=ConfirmState.confirmed)
    db.add(entity)
    db.flush()
    ev = Event(user_id=user.id, title=f"Besuch {name}", date_start=when,
               confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.flush()
    db.add(EventEntityLink(event_id=ev.id, entity_id=entity.id, role="mentioned"))
    db.flush()
    return entity


def _continent(result, code):
    return next(c for c in result.continents if c.code == code)


# --------------------------------------------------------------------------- #
# Stammdaten — die Kontinente sind die Hälfte, die keiner sucht
# --------------------------------------------------------------------------- #
def test_every_continent_has_both_names():
    """In BEIDE Richtungen: ein fehlender und ein erfundener Code sind Defekte.

    Nur „jeder deutsche hat einen englischen" zu prüfen, ließe einen
    englischen Eintrag durchgehen, den es auf der deutschen Seite gar nicht
    gibt — ein Kontinent, der in einer Sprache existiert und in der anderen
    nicht, ist in beiden Richtungen dieselbe Sorte Fehler.
    """
    assert set(ref.CONTINENTS) == set(ref.CONTINENTS_EN)
    assert all(ref.CONTINENTS_EN.values()), "leerer englischer Kontinentname"


def test_continent_name_follows_the_language():
    assert ref.continent_name("NA", "en") == "North America"
    assert ref.continent_name("NA", "de") == "Nordamerika"


def test_continent_name_falls_back_to_german_never_to_the_code():
    """Ein fehlender Eintrag zeigt Deutsch — nie „SA", das sähe nach Defekt aus."""
    for value in (None, "", "fr", "klingon"):
        assert ref.continent_name("SA", value) == "Südamerika"


def test_by_continent_sorts_by_the_displayed_name():
    """Sonst stünde eine englische Liste scheinbar zufällig da."""
    europe_en = [c.name_en for c in ref.by_continent("en")["EU"]]
    assert europe_en == sorted(europe_en)
    europe_de = [c.name_de for c in ref.by_continent("de")["EU"]]
    assert europe_de == sorted(europe_de)


# --------------------------------------------------------------------------- #
# Der Reiter selbst
# --------------------------------------------------------------------------- #
def test_world_names_countries_and_continents_in_english(db, user):
    _visited(db, user, "Deutschland")
    _visited(db, user, "Vereinigte Staaten", datetime(2021, 7, 4))
    db.commit()

    result = world(lang="en", db=db, user=user)
    assert {c.name for c in _continent(result, "EU").countries} == {"Germany"}
    assert {c.name for c in _continent(result, "NA").countries} == \
        {ref.BY_ISO["US"].name_en}
    assert _continent(result, "NA").label == "North America"
    assert _continent(result, "EU").label == "Europe"


def test_world_translates_the_missing_list_too(db, user):
    """Die Checkliste ist überwiegend die FEHLENDE Hälfte — sie ist der Reiter."""
    _visited(db, user, "Deutschland")
    db.commit()

    missing = _continent(world(lang="en", db=db, user=user), "EU").missing
    assert "France" in missing and "Frankreich" not in missing
    assert "Germany" not in missing, "besuchtes Land darf nicht fehlen"
    assert missing == sorted(missing), "englische Liste nach deutschen Namen sortiert"


def test_world_stays_german_by_default(db, user):
    _visited(db, user, "Deutschland")
    db.commit()

    result = world(db=db, user=user)
    assert {c.name for c in _continent(result, "EU").countries} == {"Deutschland"}
    assert _continent(result, "EU").label == "Europa"


def test_world_follows_the_account_when_nothing_is_asked(db, user):
    """Ohne Angabe entscheidet das Konto — der Lauf ohne Aufrufer braucht das."""
    _visited(db, user, "Deutschland")
    user.settings = {"lang": "en"}
    db.commit()

    result = world(db=db, user=user)
    assert {c.name for c in _continent(result, "EU").countries} == {"Germany"}


def test_asked_language_beats_the_stored_one(db, user):
    """Der Sprachknopf zeichnet neu, BEVOR der PATCH ankommt.

    Hinge die Anzeige am gespeicherten Konto, käme der Reiter beim Umschalten
    in der alten Sprache zurück und bliebe bis zum nächsten Neuladen so stehen.
    """
    _visited(db, user, "Deutschland")
    user.settings = {"lang": "de"}
    db.commit()

    result = world(lang="en", db=db, user=user)
    assert {c.name for c in _continent(result, "EU").countries} == {"Germany"}
    assert _continent(result, "EU").label == "Europe"


def test_unmatched_keeps_the_stored_spelling(db, user):
    """Was niemand zuordnen konnte, lässt sich auch nicht übersetzen.

    Und es ist genau die Schreibweise, die der Nutzer im Kompendium korrigieren
    soll — sie zu glätten hieße, den Hinweis unbrauchbar zu machen.
    """
    _visited(db, user, "Atlantis")
    db.commit()

    assert world(lang="en", db=db, user=user).unmatched == ["Atlantis"]


# --------------------------------------------------------------------------- #
# Dieselbe Regel, zweiter Ort
# --------------------------------------------------------------------------- #
def test_display_lang_prefers_the_request_and_validates_it():
    class _U:
        settings = {"lang": "en"}

    assert geo.display_lang("de", _U()) == "de"
    assert geo.display_lang(None, _U()) == "en"
    # Unsinn aus der Adresszeile fällt auf das Konto zurück, nicht auf Deutsch
    assert geo.display_lang("klingon", _U()) == "en"
    assert geo.display_lang(None, None) == "de"


def test_toplists_take_the_asked_language(db, user, monkeypatch):
    """Die Ranglisten benennen Länder serverseitig — dieselbe Falle, zweiter Ort."""
    seen = {}
    monkeypatch.setattr("app.routers.stats.compute_toplists",
                        lambda db, uid, lang=None: seen.setdefault("lang", lang) or {})

    user.settings = {"lang": "de"}
    toplists(lang="en", db=db, user=user)
    assert seen["lang"] == "en"
