"""Anmerkung 173 — Umschrift fremdschriftlicher Ortsnamen.

Der gemeldete Zustand: „Was der Lauf nicht benennen konnte" listete acht
griechische Orte, und die Liste blieb bei jedem Durchgang dieselbe. Der Lauf
fragte den Geocoder, bekam denselben griechischen Namen zurück, `_name_defect`
sagte weiterhin „nonlatin" — ein Abruf, der nichts ändern KANN.

Geprüft wird deshalb in beide Richtungen (Anmerkung 108): dass die Umschrift
die gemeldeten Namen wirklich lesbar macht, UND dass sie dort schweigt, wo sie
nichts zu suchen hat (lateinische Namen, OSM-eigene `name:de`).
"""
from __future__ import annotations

import pytest

from app.services import geocode as geocode_svc
from app.services.geocode import latinize, short_name
from app.services.translit import romanize


# --------------------------------------------------------------------------- #
# Die acht gemeldeten Namen, wörtlich aus der Rückmeldung vom 2026-08-04
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("greek", "latin"), [
    ("Βίγλα", "Vigla"),
    ("Κέρκυρα - Αχίλλειο", "Kerkyra - Achilleio"),
    ("Καλλιθέα", "Kallithea"),
    ("Αεροδρόμιο", "Aerodromio"),
    ("Ελευθερίου Βενιζέλου", "Eleftheriou Venizelou"),
    ("Αγίων Πατέρων", "Agion Pateron"),
    ("Αγία Κυριακή", "Agia Kyriaki"),
    ("Πυρπόλητη Γεώργiου Ανεμογιάννη", "Pyrpoliti Georgiou Anemogianni"),
])
def test_reported_greek_names(greek, latin):
    assert romanize(greek) == latin


def test_greek_digraphs_are_not_letter_by_letter():
    """ου/ευ/αυ sind der Unterschied zwischen lesbar und Buchstabensalat.

    Buchstabe für Buchstabe hieße „Ελευθερίου" nämlich „Eleytherioy" — und
    genau daran erkennt man eine Umschrift, die niemand benutzt hat."""
    assert romanize("Ελευθερίου") == "Eleftheriou"      # ευ vor θ: stimmlos
    assert romanize("Ευαγγελισμός") == "Evangelismos"   # ευ vor α: stimmhaft
    assert romanize("Αύγουστος") == "Avgoustos"
    assert romanize("Άγγελος") == "Angelos"             # γγ


def test_diaeresis_breaks_the_digraph():
    """„Μάιος" ist nicht „Μάυος" — das Trema trennt, es betont nicht."""
    assert romanize("Μάιος") == "Maios"


def test_case_follows_the_next_letter():
    """Ein Θ wird zu zwei Buchstaben, und ob „Th" oder „TH" entscheidet das
    nächste Zeichen. Ohne diesen Blick nach vorn schriee jede Abkürzung."""
    assert romanize("Θεσσαλονίκη") == "Thessaloniki"
    assert romanize("ΑΘΗΝΑ") == "ATHINA"
    assert romanize("Αθήνα") == "Athina"


def test_precomposed_letters_keep_their_own_row():
    """й und ї sind eigene Buchstaben, keine Buchstaben mit Zeichen darauf.

    Wer blind nach NFD zerlegt, macht aus „Київ" ein „Kiiv": die Zerlegung ist
    die Notlösung für Akzente, nicht der Regelweg."""
    assert romanize("Київ") == "Kiyiv"
    assert romanize("Николай") == "Nikolay"
    assert romanize("Москва") == "Moskva"
    assert romanize("Улица Щорса") == "Ulitsa Shchorsa"


def test_latin_text_is_left_alone():
    """Keine Tafel zuständig heißt: nichts zu tun, und das ist kein Ergebnis."""
    assert romanize("Detmold") is None
    assert romanize("") is None
    assert romanize(None) is None
    # latinize kennt denselben Fall — gibt den Text aber unverändert zurück,
    # denn „schon lateinisch" ist ein Erfolg und kein Fehlschlag.
    assert latinize("Hangsteinstraße 5") == "Hangsteinstraße 5"


@pytest.mark.parametrize("foreign", ["東京", "القاهرة", "กรุงเทพ", "서울"])
def test_scripts_without_a_table_say_so(foreign):
    """`None` heißt „geht hier nicht" — es darf nicht wie „nichts zu tun"
    aussehen, sonst hielte ein Lauf den unlesbaren Namen für erledigt."""
    assert latinize(foreign) is None


# --------------------------------------------------------------------------- #
# short_name: wo die Umschrift wirkt und wo sie aufhört
# --------------------------------------------------------------------------- #
def test_short_name_romanizes_every_part():
    hit = {"address": {"road": "Ελευθερίου Βενιζέλου", "suburb": "Mantouki",
                       "city": "Κέρκυρα", "country": "Griechenland"}}
    assert short_name(hit) == "Eleftheriou Venizelou, Mantouki, Kerkyra, Griechenland"


def test_unwritable_part_drops_only_if_something_named_remains():
    """Der Rückfall darf den Ort nicht ENTNAMEN.

    Ein Segment ohne Umschrift fällt weg — aber nur, solange danach noch etwas
    steht, das diesen Ort von seinem Nachbarn unterscheidet. Bliebe bloß das
    Land übrig, wäre aus einer Kapelle ein „Japan" geworden, und zwei solche
    Orte sähen fortan gleich aus."""
    only_country = {"address": {"road": "東京タワー", "country": "Japan"}}
    assert short_name(only_country) == "東京タワー, Japan"

    with_city = {"address": {"road": "東京タワー", "city": "Tokio",
                             "country": "Japan"}}
    assert short_name(with_city) == "Tokio, Japan"


def test_duplicate_parts_are_merged_after_romanizing():
    """Zwei Bausteine, die dasselbe ergeben, sind derselbe Baustein —
    sonst stünde „Kerkyra, Kerkyra" da."""
    hit = {"poi": "Κέρκυρα", "address": {"city": "Kerkyra",
                                         "country": "Griechenland"}}
    assert short_name(hit) == "Kerkyra, Griechenland"


def test_city_uses_the_same_spelling_as_the_name():
    """Zwei Schreibweisen derselben Stadt wären zwei Städte im Kompendium."""
    hit = {"address": {"city": "Κέρκυρα", "country": "Griechenland"}}
    assert geocode_svc.city_of(hit) == "Kerkyra"
    # Ohne Umschrift bleibt der Originalname: ein unlesbarer Stadtname ist
    # immer noch eine Auskunft, gar keiner nicht.
    assert geocode_svc.city_of({"address": {"city": "東京"}}) == "東京"


def test_osm_name_beats_our_transliteration():
    """Erst die Quelle, dann wir. „München" ist der Name der Stadt,
    „Minchen" wäre nur, wie man ihn buchstabiert."""
    out = geocode_svc._prefer_latin("Μόναχο, Bayern",
                                    {"name:de": "München"}, "de")
    assert out == "München, Bayern"


def test_transliteration_is_the_fallback_when_osm_has_no_latin_name():
    out = geocode_svc._prefer_latin("Αγία Κυριακή, Griechenland", None, "de")
    assert out == "Agia Kyriaki, Griechenland"
    # Ohne Tafel bleibt der Name, wie er kam — nichts zu erfinden ist besser,
    # als etwas Falsches hinzuschreiben.
    assert geocode_svc._prefer_latin("東京タワー, Japan", None, "de") == "東京タワー, Japan"


def test_resolved_greek_name_no_longer_counts_as_a_defect():
    """Der eigentliche Punkt: der Lauf kommt VORAN.

    `_name_defect` meldete „nonlatin", der Abruf lieferte denselben Namen, und
    der Ort stand beim nächsten Durchgang wieder ganz vorn — die
    Endlos-Abruf-Falle in ihrer stillsten Form (der Lauf tat etwas, es nützte
    nur nichts)."""
    from app.routers.tracks import _name_defect
    parts = ["road", "suburb", "city", "country"]
    before = "Αγία Κυριακή, Griechenland"
    assert _name_defect(before, parts) == "nonlatin"
    hit = {"address": {"road": "Αγία Κυριακή", "country": "Griechenland"}}
    assert _name_defect(short_name(hit, parts), parts) is None
