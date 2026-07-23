"""Anmerkung 119 — „Wo steht das Wetter, wenn ein Tag zwei Orte hat?"

Wetter ist eine Eigenschaft von (Tag, Ort) und wird je EREIGNIS gespeichert.
Aus dieser Naht sind zwei Defekte gewachsen, und beide sind still:

* **Vier Regeln für einen Begriff.** Zeitstrahl (Wetter des
  Verdichtungs-Vertreters `min(id)`, bei UUIDs also zufällig), Sammelkarte
  (gar keins), Erfolge (`min` je Tag), Statistik (erstes Ereignis des Tages).
  Jede für sich plausibel, zusammen widersprüchlich — Anmerkung 106.
* **Dieselbe Frage mehrfach gestellt.** Fünf Besuche an einem Tag, vier davon
  am selben Ort: fünf Abrufe bei Open-Meteo, fünfmal dieselbe Antwort.

Geprüft wird deshalb nicht „kommt eine Zahl heraus", sondern dass ALLE
Lesestellen dieselbe Zahl nennen und dass der Abruf sich nicht wiederholt.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Location, Metric,
                        Source)
from app.services import weather as weather_svc
from app.services import weather_day


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
def _loc(db, user, name, lat, lng):
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng, city="Hamburg")
    db.add(loc)
    db.flush()
    return loc


def _event(db, user, when, *, place=None, category="event", title="Eintrag",
           parent=None, **wx):
    e = Event(user_id=user.id, title=title, category=category, date_start=when,
              date_precision=DatePrecision.exact, location=place,
              parent_event_id=parent, confirmed=ConfirmState.confirmed)
    db.add(e)
    db.flush()
    for key, value in wx.items():
        if isinstance(value, str):
            db.add(Metric(event_id=e.id, key=key, value_text=value,
                          source=Source.weather))
        else:
            db.add(Metric(event_id=e.id, key=key, value=value,
                          source=Source.weather))
    db.commit()
    return e


# --------------------------------------------------------------------------- #
# Der Abruf: derselbe Tag am selben Ort wird EINMAL gefragt
# --------------------------------------------------------------------------- #
@pytest.fixture()
def http(monkeypatch):
    """Zählt die tatsächlichen Open-Meteo-Aufrufe.

    Bewusst auf der Ebene von `urlopen` und nicht auf `fetch_weather`: der
    Cache sitzt IN `fetch_weather`, ein Doppel davor würde ihn wegnehmen und
    dieser Test bestünde immer. Genau die Sorte Test-Doppel, die in
    Anmerkung 116 eine Endlosschleife verdeckt hat.
    """
    weather_svc.reset_cache()
    calls: list[str] = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return (b'{"daily": {"temperature_2m_max": [22.0],'
                    b' "temperature_2m_min": [12.0], "weathercode": [3],'
                    b' "sunshine_duration": [3600.0]}}')

    def _open(req, timeout=None):
        calls.append(req.full_url)
        return _Resp()

    monkeypatch.setattr(weather_svc.urllib.request, "urlopen", _open)
    yield calls
    weather_svc.reset_cache()


def test_derselbe_ort_am_selben_tag_wird_einmal_gefragt(http):
    day = date(2026, 5, 13)
    weather_svc.fetch_weather(53.5511, 9.9937, day)
    weather_svc.fetch_weather(53.5511, 9.9937, day)
    # Ein paar Meter weiter — dieselbe Gitterzelle, dieselbe Auskunft
    weather_svc.fetch_weather(53.5513, 9.9935, day)

    assert len(http) == 1, "drei Ereignisse desselben Ortes, ein Abruf"


def test_ein_anderer_tag_wird_erneut_gefragt(http):
    weather_svc.fetch_weather(53.55, 9.99, date(2026, 5, 13))
    weather_svc.fetch_weather(53.55, 9.99, date(2026, 5, 14))
    assert len(http) == 2


def test_ein_anderer_ort_wird_erneut_gefragt(http):
    day = date(2026, 5, 13)
    weather_svc.fetch_weather(53.55, 9.99, day)
    weather_svc.fetch_weather(48.14, 11.58, day)     # München
    assert len(http) == 2


def test_die_anfrage_nennt_die_koordinaten_des_schluessels(http):
    """Sonst läge unter dem Schlüssel eine Antwort für einen anderen Punkt."""
    weather_svc.fetch_weather(53.55119, 9.99372, date(2026, 5, 13))
    assert "latitude=53.55" in http[0] and "longitude=9.99" in http[0]


def test_ein_fehlschlag_wird_nicht_gemerkt(monkeypatch):
    """Die Gegenrichtung zur Endlos-Abruf-Falle: ein Prozess-Cache darf einen
    Netzaussetzer nicht zur dauerhaften Auskunft machen."""
    weather_svc.reset_cache()
    calls = []

    def _boom(req, timeout=None):
        calls.append(req.full_url)
        raise TimeoutError("weg")

    monkeypatch.setattr(weather_svc.urllib.request, "urlopen", _boom)
    assert weather_svc.fetch_weather(53.55, 9.99, date(2026, 5, 13)) is None
    assert weather_svc.fetch_weather(53.55, 9.99, date(2026, 5, 13)) is None
    assert len(calls) == 2, "der Fehlschlag hätte den Ort vergiftet"
    weather_svc.reset_cache()


def test_ein_importtag_fragt_je_ort_einmal(db, user, http):
    """Der Fall aus der Nutzung: fünf Besuche, vier davon an derselben Adresse.

    Gemessen wird der ganze Lauf, nicht `fetch_weather` allein — die Ersparnis
    entsteht nur, wenn die Anreicherung wirklich durch dieselbe Funktion geht.

    **Zwei Abrufe, nicht einer**, und das ist Absicht: die beiden Adressen
    liegen gut einen Kilometer auseinander und damit in verschiedenen
    Cache-Zellen. Gröber zu runden würde mehr sparen und dabei einem Ort die
    Auskunft eines anderen unterschieben — der Cache bleibt bewusst unter der
    Auflösung der Quelle, statt sie zu überschreiten (siehe `_QUANT`).
    """
    from app.services.enrichment import enrich_weather

    ort_a = _loc(db, user, "Kaiserstraße", 53.5511, 9.9937)
    ort_b = _loc(db, user, "Hauptbahnhof", 53.5528, 10.0067)
    for hour in (9, 11, 13, 15):
        _event(db, user, datetime(2026, 5, 13, hour), place=ort_a)
    _event(db, user, datetime(2026, 5, 13, 19), place=ort_b)

    enriched, _ = enrich_weather(db, user_id=user.id)
    assert enriched == 5, "alle fünf Einträge bekommen ihr Wetter"
    assert len(http) == 2, f"je Adresse ein Abruf statt fünf — waren {len(http)}"


def test_der_cache_gibt_kopien_heraus(http):
    """Der Aufrufer hängt die Werte an ein Ereignis — ein gemeinsam benutztes
    Dict wäre ein Weg, den Cache von außen zu verändern."""
    day = date(2026, 5, 13)
    first = weather_svc.fetch_weather(53.55, 9.99, day)
    first["temp_max_c"] = -99
    assert weather_svc.fetch_weather(53.55, 9.99, day)["temp_max_c"] == 22.0


# --------------------------------------------------------------------------- #
# Die Regel: ein Wert je (Tag, Schlüssel)
# --------------------------------------------------------------------------- #
def test_gleiche_werte_am_tag_ergeben_denselben_tageswert(db, user):
    """Der Normalfall: fünf Besuche, ein Ort, ein Wetter."""
    place = _loc(db, user, "Hamburg", 53.55, 9.99)
    for hour in range(9, 14):
        _event(db, user, datetime(2026, 5, 13, hour), place=place,
               sunshine_h=2.0, rain_mm=3.2)

    wx = weather_day.day_values(db, user.id)
    assert wx["2026-05-13"] == {"sunshine_h": 2.0, "rain_mm": 3.2}


def test_reisetag_nennt_den_vorsichtigen_wert(db, user):
    nord = _loc(db, user, "Hamburg", 53.55, 9.99)
    sued = _loc(db, user, "München", 48.14, 11.58)
    _event(db, user, datetime(2026, 5, 13, 9), place=nord, sunshine_h=11.0)
    _event(db, user, datetime(2026, 5, 13, 20), place=sued, sunshine_h=3.0)

    assert weather_day.day_values(db, user.id)["2026-05-13"]["sunshine_h"] == 3.0


def test_text_steht_nur_da_wenn_der_tag_sich_einig_ist(db, user):
    """Ein alphabetisch kleinster Wetterzustand wäre keine Auskunft, sondern
    eine Sortierung."""
    nord = _loc(db, user, "Hamburg", 53.55, 9.99)
    sued = _loc(db, user, "München", 48.14, 11.58)
    _event(db, user, datetime(2026, 5, 13, 9), place=nord,
           weather="Nebel", temp_max_c=18.0)
    _event(db, user, datetime(2026, 5, 13, 20), place=sued,
           weather="Regen", temp_max_c=24.0)
    _event(db, user, datetime(2026, 5, 14, 9), place=nord,
           weather="klar", temp_max_c=21.0)
    _event(db, user, datetime(2026, 5, 14, 20), place=nord,
           weather="klar", temp_max_c=21.0)

    wx = weather_day.day_values(db, user.id)
    # Die Zahl steht da (vorsichtig), der Zustand nicht — „Nebel" ist nicht
    # der Tag, sondern nur alphabetisch vorn.
    assert wx["2026-05-13"]["temp_max_c"] == 18.0
    assert "weather" not in wx["2026-05-13"]
    assert wx["2026-05-14"]["weather"] == "klar"


def test_der_interne_marker_ist_keine_auskunft(db, user):
    place = _loc(db, user, "Hamburg", 53.55, 9.99)
    _event(db, user, datetime(2026, 5, 13, 9), place=place,
           sunshine_h=2.0, weather_rev=2.0)
    assert weather_day.day_values(db, user.id)["2026-05-13"] == {"sunshine_h": 2.0}


def test_fremde_tage_bleiben_draussen(db, user):
    from app.models import User, UserRole
    other = User(oidc_subject="fremd", email="f@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    place = _loc(db, other, "Hamburg", 53.55, 9.99)
    _event(db, other, datetime(2026, 5, 13, 9), place=place, sunshine_h=9.0)

    assert weather_day.day_values(db, user.id) == {}


# --------------------------------------------------------------------------- #
# Regionen: der Grund, aus dem ein Tag überhaupt mehrdeutig sein kann
# --------------------------------------------------------------------------- #
def test_ein_ort_ist_eine_region(db, user):
    place = _loc(db, user, "Hamburg", 53.55, 9.99)
    for hour in (9, 13, 19):
        _event(db, user, datetime(2026, 5, 13, hour), place=place, sunshine_h=2.0)

    assert weather_day.day_regions(db, user.id)["2026-05-13"] == 1


def test_nachbaradressen_sind_eine_region(db, user):
    """Zwei Adressen in derselben Stadt teilen sich die Gitterzelle — sonst
    stünde an jedem gewöhnlichen Tag „2 Wettergegenden"."""
    a = _loc(db, user, "Kaiserstraße", 53.551, 9.993)
    b = _loc(db, user, "Hauptbahnhof", 53.553, 9.997)
    _event(db, user, datetime(2026, 5, 13, 9), place=a, sunshine_h=2.0)
    _event(db, user, datetime(2026, 5, 13, 19), place=b, sunshine_h=2.0)

    assert weather_day.day_regions(db, user.id)["2026-05-13"] == 1


def test_ein_reisetag_hat_zwei_regionen(db, user):
    nord = _loc(db, user, "Hamburg", 53.55, 9.99)
    sued = _loc(db, user, "München", 48.14, 11.58)
    _event(db, user, datetime(2026, 5, 13, 9), place=nord, sunshine_h=11.0)
    _event(db, user, datetime(2026, 5, 13, 20), place=sued, sunshine_h=3.0)

    assert weather_day.day_regions(db, user.id)["2026-05-13"] == 2


def test_ein_eintrag_ohne_wetter_macht_den_tag_nicht_mehrdeutig(db, user):
    """Ein Tagebucheintrag ohne Wetter sagt über das Wetter nichts."""
    place = _loc(db, user, "Hamburg", 53.55, 9.99)
    fern = _loc(db, user, "Lissabon", 38.72, -9.14)
    _event(db, user, datetime(2026, 5, 13, 9), place=place, sunshine_h=2.0)
    _event(db, user, datetime(2026, 5, 13, 21), place=fern, title="Notiz")

    assert weather_day.day_regions(db, user.id)["2026-05-13"] == 1


# --------------------------------------------------------------------------- #
# Der Kern: alle Lesestellen nennen dieselbe Zahl
# --------------------------------------------------------------------------- #
def test_zeitstrahl_statistik_und_erfolge_stimmen_ueberein(db, user):
    """Der eigentliche Sinn von Anmerkung 119.

    Ein Reisetag mit 11 h und 3 h Sonne. Vor der Vereinheitlichung nannte die
    Statistik 11 (erstes Ereignis des Tages), der Zeitstrahl je nach UUID mal
    11 und mal 3, die Erfolge 3. Drei Antworten auf eine Frage — und keine
    davon fiel je auf, weil jede für sich plausibel aussah.
    """
    from app.services.stats_overview import compute_overview

    nord = _loc(db, user, "Hamburg", 53.55, 9.99)
    sued = _loc(db, user, "München", 48.14, 11.58)
    _event(db, user, datetime(2026, 5, 13, 9), place=nord, sunshine_h=11.0)
    _event(db, user, datetime(2026, 5, 13, 20), place=sued, sunshine_h=3.0)

    aus_der_regel = weather_day.day_values(db, user.id)["2026-05-13"]["sunshine_h"]
    aus_der_statistik = compute_overview(db, user.id)["weather"]["sun_hours"]
    aus_den_erfolgen = (
        weather_day.day_value_query(db, user.id, "sunshine_h").all()[0].value)

    assert aus_der_regel == 3.0
    assert aus_der_statistik == 3, "die Statistik nahm den ersten Eintrag des Tages"
    assert aus_den_erfolgen == 3.0


def test_die_schwelle_fragt_weiter_ob_der_tag_es_erreicht_hat(db, user):
    """Die zweite Frage, bewusst anders beantwortet als die erste.

    Ob ein Tag zählt (Schwelle) und welchen Wert er beisteuert (Summe) sind
    zwei Fragen. Ein Tag, an dem irgendwo elf Stunden die Sonne schien, war ein
    Sonnentag; das nachträglich abzuerkennen, weil man abends weitergefahren
    ist, verschwiege eine Tatsache. `test_f19_badges.py` hält das seit 0.35
    fest — hier steht, dass der Umbau es nicht umgeworfen hat.
    """
    nord = _loc(db, user, "Hamburg", 53.55, 9.99)
    sued = _loc(db, user, "München", 48.14, 11.58)
    _event(db, user, datetime(2026, 5, 13, 9), place=nord, sunshine_h=11.0)
    _event(db, user, datetime(2026, 5, 13, 20), place=sued, sunshine_h=3.0)

    treffer = weather_day.day_value_query(db, user.id, "sunshine_h",
                                          min_value=10).all()
    assert len(treffer) == 1, "der Tag hat die Schwelle erreicht"
    assert treffer[0].value == 3.0, "beisteuern tut er den vorsichtigen Wert"


def test_unbestaetigtes_zaehlt_in_den_erfolgen_nicht(db, user):
    place = _loc(db, user, "Hamburg", 53.55, 9.99)
    e = _event(db, user, datetime(2026, 5, 13, 9), place=place, sunshine_h=11.0)
    e.confirmed = ConfirmState.unconfirmed
    db.commit()

    assert weather_day.day_value_query(db, user.id, "sunshine_h").all() == []
    assert "2026-05-13" in weather_day.day_values(db, user.id), \
        "der Zeitstrahl zeigt Vorschläge, also fasst der Tageskopf sie mit"


# --------------------------------------------------------------------------- #
# Der Endpunkt
# --------------------------------------------------------------------------- #
def test_endpunkt_liefert_werte_und_regionen(db, user):
    from app.routers.weather import day_weather_range

    nord = _loc(db, user, "Hamburg", 53.55, 9.99)
    sued = _loc(db, user, "München", 48.14, 11.58)
    _event(db, user, datetime(2026, 5, 13, 9), place=nord, sunshine_h=11.0)
    _event(db, user, datetime(2026, 5, 13, 20), place=sued, sunshine_h=3.0)

    out = day_weather_range(date_from=date(2026, 5, 13), date_to=date(2026, 5, 13),
                            db=db, user=user)
    assert out["2026-05-13"]["values"]["sunshine_h"] == 3.0
    assert out["2026-05-13"]["regions"] == 2


def test_das_zeitfenster_umfasst_ganze_kalendertage(db, user):
    """`from == to` muss den ganzen Tag treffen, nicht seine erste Sekunde."""
    from app.routers.weather import day_weather_range

    place = _loc(db, user, "Hamburg", 53.55, 9.99)
    _event(db, user, datetime(2026, 5, 13, 23, 30), place=place, sunshine_h=2.0)

    out = day_weather_range(date_from=date(2026, 5, 13), date_to=date(2026, 5, 13),
                            db=db, user=user)
    assert out["2026-05-13"]["values"]["sunshine_h"] == 2.0


def test_ein_verdrehter_zeitraum_wird_abgewiesen(db, user):
    from fastapi import HTTPException

    from app.routers.weather import day_weather_range

    with pytest.raises(HTTPException):
        day_weather_range(date_from=date(2026, 5, 20), date_to=date(2026, 5, 13),
                          db=db, user=user)


def test_ein_ganzes_leben_passt_in_eine_anfrage(db, user):
    """Die Spanne einer Seite ist die Spanne ihrer Ereignisse — in einem dünn
    gefüllten Bestand sind das Jahrzehnte. Eine Grenze, die das abweist, macht
    aus dem Tageswetter eine stille Auslassung."""
    from app.routers.weather import day_weather_range

    place = _loc(db, user, "Hamburg", 53.55, 9.99)
    _event(db, user, datetime(1994, 3, 2, 9), place=place, sunshine_h=1.0)
    _event(db, user, datetime(2026, 5, 13, 9), place=place, sunshine_h=2.0)

    out = day_weather_range(date_from=date(1994, 3, 2), date_to=date(2026, 5, 13),
                            db=db, user=user)
    assert set(out) == {"1994-03-02", "2026-05-13"}
