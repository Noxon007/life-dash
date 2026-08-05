"""Anmerkungen 196–198 — drei Befunde aus der Rückmeldung vom 2026-08-05.

Alle drei sind Fälle derselben Sorte: nichts ist kaputt, es ist nur still
auseinandergelaufen.

**(a) Ein Land, zwei Namen (198).** „Deutschland · 14.087 Einträge" und „Germany ·
2.685 Einträge" standen als zwei Zeilen in derselben Rangliste. Die Namen
kommen aus zwei Quellen — Nominatim antwortet in der angefragten Sprache,
Immichs EXIF-Geokodierung immer englisch. In der Rangliste ist das eine
doppelte Zeile; in „Reichweite je Jahr" ist es eine FALSCHE ZAHL, weil dort
verschiedene Länder gezählt werden.

**(b) Ein Zuhause, zwei Orte (197).** Der eingetragene Wohnort und das, was ein
Geräte-Export für dieselbe Wohnung hält (die Nebenstraße), standen als zwei
Orte untereinander — einer mit allen Tagen und keinem Eintrag, der andere
umgekehrt.

**(c) „Foto in Groningen" ohne ein Foto (196).** Der Foto-Ereignis-Lauf legt
tausende Einträge an; die Leiste „Fotos dieses Tages" hing an einem zweiten
Lauf, der jeden Tag einzeln bei Immich nachfragt.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.data import countries as ref
from app.models import (BaselineLocation, ConfirmState, DatePrecision, Event,
                        Location, MediaRef, Source)
from app.services import baseline
from app.services.stats_overview import compute_overview
from app.services.stats_toplists import compute_toplists


def _place(db, user, name, *, lat=53.58, lng=10.01, city=None, country=None):
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng,
                   city=city, country=country)
    db.add(loc)
    db.flush()
    return loc


def _event(db, user, loc, day, *, title="Eintrag", source=Source.manual,
           external_id=None):
    ev = Event(user_id=user.id, title=title, category="event",
               date_start=datetime.combine(day, datetime.min.time()),
               date_precision=DatePrecision.day, source=source,
               confirmed=ConfirmState.confirmed, location=loc,
               external_id=external_id)
    db.add(ev)
    return ev


# --------------------------------------------------------------------------- #
# (a) Ein Land, ein Name
# --------------------------------------------------------------------------- #
def test_the_reference_table_knows_both_spellings():
    """Die Stammdaten können es längst — es fragte nur niemand."""
    assert ref.display("Deutschland", "de") == "Deutschland"
    assert ref.display("Germany", "de") == "Deutschland"
    assert ref.display("Deutschland", "en") == "Germany"
    assert ref.display("Nederland", "de") == "Niederlande"


def test_an_unknown_country_keeps_its_name():
    """Die Gegenprobe, ohne die der Fix eine Verschlechterung wäre: ein Name,
    den die Tabelle nicht kennt, darf nicht verschwinden. Eine Zeile still zu
    verschlucken ist teurer als eine, die ungewöhnlich heißt."""
    assert ref.display("Freistaat Utopia", "de") == "Freistaat Utopia"
    assert ref.display("", "de") is None


def test_two_spellings_become_one_row(db, user):
    """Der gemeldete Fall: zwei Zeilen, ein Land. Beide Zahlen müssen dabei
    ankommen — eine zusammengeführte Zeile, die nur die Hälfte zählt, wäre
    genauso falsch, nur unauffälliger."""
    de = _place(db, user, "Kaiserstraße 5", country="Deutschland")
    en = _place(db, user, "Bahnhofstraße 1", lat=53.6, lng=10.1,
                country="Germany")
    _event(db, user, de, date(2024, 3, 1))
    _event(db, user, de, date(2024, 3, 2))
    _event(db, user, en, date(2024, 3, 3))
    db.commit()

    lands = compute_toplists(db, user.id, lang="de")["countries"]
    assert [r["name"] for r in lands] == ["Deutschland"]
    assert lands[0]["events"] == 3
    assert lands[0]["days"] == 3


def test_the_language_decides_how_the_country_is_called(db, user):
    """F10: dieselbe Zahl, der Name der Oberfläche."""
    loc = _place(db, user, "Kaiserstraße 5", country="Germany")
    _event(db, user, loc, date(2024, 3, 1))
    db.commit()

    assert compute_toplists(db, user.id, lang="de")["countries"][0]["name"] \
        == "Deutschland"
    assert compute_toplists(db, user.id, lang="en")["countries"][0]["name"] \
        == "Germany"


def test_reach_per_year_counted_one_country_twice(db, user):
    """**Der teure Teil des Befunds.** Die Rangliste zeigte die Doppelung
    sichtbar, „Reichweite je Jahr" verrechnete sie still: zwei Schreibweisen
    desselben Landes machten aus einem Land zwei, und „2025 · 10 Länder" war
    um eins zu hoch. Vor der Korrektur steht hier 2."""
    de = _place(db, user, "Kaiserstraße 5", city="Hamburg", country="Deutschland")
    en = _place(db, user, "Bahnhofstraße 1", lat=53.6, lng=10.1,
                city="Hamburg", country="Germany")
    _event(db, user, de, date(2024, 3, 1))
    _event(db, user, en, date(2024, 3, 2))
    db.commit()

    reach = compute_toplists(db, user.id, lang="de")["reach"]
    assert [(r["year"], r["countries"]) for r in reach] == [(2024, 1)]


def test_the_residence_country_joins_the_same_row(db, user):
    """Die andere Hälfte: die Wohnort-Tage kommen mit dem ROHEN Namen herein.
    Ohne dieselbe Umschrift stünde „Germany · 0 Einträge · 400 Tage" als
    zweite Zeile unter „Deutschland" — derselbe Defekt eine Ebene tiefer."""
    home = _place(db, user, "Musterweg 1", lat=54.0, lng=10.3, city="Kiel",
                  country="Germany")
    other = _place(db, user, "Kaiserstraße 5", lat=53.58, lng=10.01,
                   city="Hamburg", country="Deutschland")
    db.add(BaselineLocation(user_id=user.id, location_id=home.id,
                            date_start=date(2024, 1, 1),
                            date_end=date(2024, 1, 31)))
    _event(db, user, other, date(2024, 1, 5))
    db.commit()

    lands = compute_toplists(db, user.id, lang="de")["countries"]
    assert [r["name"] for r in lands] == ["Deutschland"]
    # 30 abgeleitete Tage (der 5. gehört dem Eintrag) + 1 Ereignistag
    assert lands[0]["days"] == 31
    assert lands[0]["events"] == 1


# --------------------------------------------------------------------------- #
# (b) Ein Zuhause, ein Ort
# --------------------------------------------------------------------------- #
def _home_and_sidestreet(db, user):
    """Wohnort und die Nebenstraße, die ein Geräte-Export dafür hält —
    rund 80 m auseinander, also innerhalb von `HOME_RADIUS_KM`."""
    home = _place(db, user, "Barmbeker Straße 13, Hamburg, Deutschland",
                  lat=53.5800, lng=10.0100, city="Hamburg")
    near = _place(db, user, "Knickweg, Hamburg, Deutschland",
                  lat=53.5807, lng=10.0100, city="Hamburg")
    db.add(BaselineLocation(user_id=user.id, location_id=home.id,
                            date_start=date(2024, 1, 1),
                            date_end=date(2024, 1, 31)))
    return home, near


def test_a_place_within_the_radius_is_the_residence(db, user):
    """Der gemeldete Fall: „Barmbeker Straße 13 · 0 Einträge" und „Knickweg ·
    1.161 Einträge" sind ein Ort. Vor der Korrektur stehen hier zwei Zeilen."""
    _home, near = _home_and_sidestreet(db, user)
    _event(db, user, near, date(2024, 1, 10))
    _event(db, user, near, date(2024, 1, 11))
    db.commit()

    places = compute_toplists(db, user.id)["places"]
    assert [r["name"] for r in places] == ["Barmbeker Straße 13"]
    # 29 abgeleitete Tage + 2 Ereignistage, und die Einträge sind nicht
    # verlorengegangen — genau die Zusammenführung, um die es geht.
    assert places[0]["events"] == 2
    assert places[0]["days"] == 31


def test_a_place_outside_the_radius_stays_its_own(db, user):
    """Die Gegenprobe. Ein Umkreis, der alles einsammelt, ist von einer
    kaputten Rangliste nicht zu unterscheiden — 1,3 km sind nicht zu Hause."""
    _home, _near = _home_and_sidestreet(db, user)
    far = _place(db, user, "Marktplatz 2, Hamburg, Deutschland",
                 lat=53.5920, lng=10.0100, city="Hamburg")
    _event(db, user, far, date(2024, 1, 10))
    db.commit()

    names = [r["name"] for r in compute_toplists(db, user.id)["places"]]
    assert "Marktplatz 2" in names


def test_bars_and_list_tell_the_same_story(db, user):
    """**Die eigentliche Regel dieser Datei.** Die Balken im Überblick und die
    Rangliste darunter stehen im selben Reiter untereinander. Zwei
    Umbenennungen wären zwei Antworten auf dieselbe Frage — und genau so fiele
    es auf: oben „Knickweg", unten „Barmbeker Straße 13"."""
    _home, near = _home_and_sidestreet(db, user)
    _event(db, user, near, date(2024, 1, 10))
    db.commit()

    bars = [name for name, _n in compute_overview(db, user.id)["top_places"]]
    assert bars[0] == "Barmbeker Straße 13"
    assert "Knickweg" not in bars


def test_without_a_residence_nothing_is_renamed(db, user):
    """Ohne Wohnort gibt es kein „zu Hause", also auch keine Umbenennung —
    und die Liste sieht aus wie vorher."""
    near = _place(db, user, "Knickweg, Hamburg, Deutschland",
                  lat=53.5807, lng=10.0100)
    _event(db, user, near, date(2024, 1, 10))
    db.commit()

    assert [r["name"] for r in compute_toplists(db, user.id)["places"]] \
        == ["Knickweg"]


def test_a_place_without_coordinates_is_left_alone(db, user):
    """Geraten wird nicht. Ohne Koordinate lässt sich „im Umkreis" nicht
    beantworten, und ein Name allein ist keine Antwort darauf."""
    _home_and_sidestreet(db, user)
    nowhere = Location(user_id=user.id, name="Irgendwo, Hamburg")
    db.add(nowhere)
    db.flush()
    _event(db, user, nowhere, date(2024, 1, 10))
    db.commit()

    assert "Irgendwo" in [r["name"] for r in compute_toplists(db, user.id)["places"]]


# --------------------------------------------------------------------------- #
# (c) Die Fotos an ihrem Tag
# --------------------------------------------------------------------------- #
def _asset(aid: str, when: str) -> dict:
    return {"id": aid, "localDateTime": f"{when}.000Z",
            "originalMimeType": "image/jpeg"}


def _photo_event(db, user, day: date, asset_id: str):
    """Ein Foto-Ereignis, wie `create_photo_events` es anlegt."""
    from app.services.photo_points import slot_photo

    loc = _place(db, user, f"Ort {asset_id}", city="Groningen")
    return _event(db, user, loc, day, title="Foto in Groningen",
                  source=Source.immich, external_id=slot_photo(asset_id))


def test_the_day_of_a_photo_event_gets_its_strip(db, user):
    """Der gemeldete Defekt: „Foto in Groningen" stand ohne ein einziges Bild
    daneben. Vor der Korrektur legt der Lauf nur das Ereignis an."""
    from app.services import photo_points as pp

    _photo_event(db, user, date(2024, 5, 13), "a1")
    db.commit()

    added = pp.fill_day_strips(db, user, [_asset("a1", "2024-05-13T10:00:00"),
                                          _asset("a2", "2024-05-13T14:00:00")])
    db.commit()
    assert added == 2
    rows = db.query(MediaRef).filter(MediaRef.user_id == user.id).all()
    assert {m.external_id for m in rows} == {"a1", "a2"}
    assert all(m.event_id is None for m in rows), \
        "die Bilder hängen am TAG, nicht am Vorschlag (Anmerkung 111)"


def test_a_day_without_an_entry_stays_empty(db, user):
    """Die Grenze, die `day_candidates` schon zieht: ein Tag ohne jeden
    Eintrag ist nicht Teil der Lebensdatenbank. Ohne diese Prüfung importierte
    der Lauf die halbe Immich-Bibliothek."""
    from app.services import photo_points as pp

    _photo_event(db, user, date(2024, 5, 13), "a1")
    db.commit()

    added = pp.fill_day_strips(db, user, [_asset("a9", "2024-08-01T10:00:00")])
    assert added == 0


def test_a_day_that_already_has_a_strip_is_left_alone(db, user):
    """Die Endlos-Abruf-Falle von der anderen Seite: ohne die Marke hinge nach
    jedem Lauf dasselbe Bild ein weiteres Mal am selben Tag."""
    from app.services import photo_points as pp

    _photo_event(db, user, date(2024, 5, 13), "a1")
    db.add(MediaRef(user_id=user.id, event_id=None, provider="immich",
                    external_id="a1", captured_at=datetime(2024, 5, 13, 10)))
    db.commit()

    assert pp.fill_day_strips(db, user, [_asset("a1", "2024-05-13T10:00:00"),
                                         _asset("a2", "2024-05-13T14:00:00")]) == 0


def test_twelve_per_day_spread_over_the_day(db, user):
    """Dieselbe Deckelung wie beim Verknüpfungs-Lauf, weil es dieselbe
    Funktion ist (`immich_link.add_day_media`). Ein Urlaubstag mit 300 Bildern
    gehört nach Immich, nicht als Kachelwand in den Zeitstrahl — und gegriffen
    wird über den Tag gestreut, nicht vorne abgeschnitten."""
    from app.services import photo_points as pp

    _photo_event(db, user, date(2024, 5, 13), "a0")
    db.commit()

    assets = [_asset(f"a{i}", f"2024-05-13T{i // 3:02d}:{i % 3 * 20:02d}:00")
              for i in range(60)]
    assert pp.fill_day_strips(db, user, assets) == 12
    db.commit()
    got = sorted(m.captured_at for m in
                 db.query(MediaRef).filter(MediaRef.user_id == user.id).all())
    assert got[0].hour == 0 and got[-1].hour >= 18, \
        "vorne abgeschnitten hieße: vom Tag nur der Morgen"


def test_the_local_day_decides_not_utc(db, user):
    """Anmerkung P2.1(a) gilt hier genauso: ein Foto vom 13. Mai 01:30 aus
    Berlin darf nicht auf dem 12. landen. Die Zeit kommt aus derselben
    Funktion (`api.asset_time`), damit Ereignis und Leiste denselben Tag
    meinen."""
    from app.services import photo_points as pp

    _photo_event(db, user, date(2024, 5, 13), "a1")
    db.commit()

    late = {"id": "a2", "fileCreatedAt": "2024-05-12T23:30:00.000Z",
            "localDateTime": "2024-05-13T01:30:00.000Z"}
    assert pp.fill_day_strips(db, user, [late]) == 1


# --------------------------------------------------------------------------- #
# Der Umkreis selbst
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("km,expected", [(0.05, "Zuhause"), (0.5, "Knickweg")])
def test_home_naming_answers_by_distance(db, user, km, expected):
    """Die Regel ohne die Statistik drumherum — 150 m ist die Grenze."""
    home = _place(db, user, "Zuhause", lat=53.58, lng=10.01)
    db.add(BaselineLocation(user_id=user.id, location_id=home.id,
                            date_start=date(2024, 1, 1)))
    db.commit()
    named = baseline.home_naming(db, user.id)
    # 1 Breitengrad ≈ 111 km — daraus der Abstand in Grad
    assert named("Knickweg", 53.58 + km / 111.0, 10.01) == expected
