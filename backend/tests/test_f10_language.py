"""Tests für 0.20.0: F10 — Sprachwahl wirkt bis ins Geocoding (A25-Rest).

Vorher war `Accept-Language: de,en` fest verdrahtet: eine englische Oberfläche
hätte deutsche Ortsnamen bekommen.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.auth import update_my_settings
from app.services import geocode as geo


# --------------------------------------------------------------------------- #
# Accept-Language-Kette
# --------------------------------------------------------------------------- #
def test_accept_language_follows_ui_language():
    assert geo.accept_language("de") == "de,en"
    assert geo.accept_language("en") == "en,de"


def test_accept_language_falls_back_to_german():
    """Unbekannte oder fehlende Sprache darf nie einen leeren Header ergeben."""
    for value in (None, "", "fr", "klingon"):
        assert geo.accept_language(value) == "de,en"


def test_name_keys_prefer_the_ui_language():
    assert geo._name_keys("de") == ("name:de", "name:en", "name")
    assert geo._name_keys("en") == ("name:en", "name:de", "name")


def test_lang_for_reads_user_setting(user):
    assert geo.lang_for(user) == "de"          # nichts gesetzt -> Default
    user.settings = {"lang": "en"}
    assert geo.lang_for(user) == "en"
    user.settings = {"lang": "fr"}             # ungültig -> Default
    assert geo.lang_for(user) == "de"
    assert geo.lang_for(None) == "de"


# --------------------------------------------------------------------------- #
# Namenswahl aus den namedetails
# --------------------------------------------------------------------------- #
def test_poi_name_uses_language_order():
    details = {"name:de": "Athen", "name:en": "Athens", "name": "Αθήνα"}
    assert geo._poi_name(details, "de") == "Athen"
    assert geo._poi_name(details, "en") == "Athens"


def test_poi_name_falls_back_through_the_chain():
    assert geo._poi_name({"name:en": "Athens", "name": "Αθήνα"}, "de") == "Athens"
    assert geo._poi_name({"name": "Αθήνα"}, "en") == "Αθήνα"
    assert geo._poi_name(None, "de") is None


def test_prefer_latin_uses_language_order():
    details = {"name:de": "Korfu", "name:en": "Corfu"}
    greek = "Κέρκυρα, Griechenland"
    assert geo._prefer_latin(greek, details, "de").startswith("Korfu")
    assert geo._prefer_latin(greek, details, "en").startswith("Corfu")


def test_prefer_latin_leaves_latin_names_alone():
    """Steht vorne schon lateinische Schrift, wird nichts ersetzt."""
    name = "Musterstraße, Detmold"
    assert geo._prefer_latin(name, {"name:en": "Example Street"}, "en") == name


# --------------------------------------------------------------------------- #
# Einstellung speichern
# --------------------------------------------------------------------------- #
def test_settings_accepts_supported_languages(db, user):
    for lang in ("en", "de"):
        view = update_my_settings(payload={"lang": lang}, db=db, user=user)
        assert view["lang"] == lang
        assert user.settings["lang"] == lang


def test_settings_rejects_unsupported_language(db, user):
    with pytest.raises(HTTPException) as err:
        update_my_settings(payload={"lang": "fr"}, db=db, user=user)
    assert err.value.status_code == 400


def test_language_reaches_the_geocoder(db, user, monkeypatch):
    """Der Lauf muss die Nutzersprache bis in den HTTP-Header durchreichen."""
    seen = {}

    def fake_fetch(url, what, lang=None):
        seen["lang"] = lang
        seen["header"] = geo.accept_language(lang)
        return {"display_name": "Corfu, Greece", "type": "city",
                "address": {"city": "Corfu", "country": "Greece"},
                "namedetails": {"name:en": "Corfu", "name:de": "Korfu"}}

    monkeypatch.setattr(geo, "_fetch_json", fake_fetch)
    geo.reverse_geocode(39.6, 19.9, "en")
    assert seen == {"lang": "en", "header": "en,de"}

    geo.reverse_geocode(39.6, 19.9, "de")
    assert seen["header"] == "de,en"
