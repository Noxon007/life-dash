"""F19 — Abzeichen, die nicht bei Platin aufhören (Anmerkungen 99/103).

Zwei Hälften, und die zweite ist die, die niemand gemeldet hat.

**(a) Die Leiter hört auf zu enden.** Platin war ein Endzustand; eine Datenbank
über ein ganzes Leben reißt jede feste Decke irgendwann. Oberhalb zählt der
Erfolg gegen eine erzeugte Marke weiter.

**(b) Die Wettermetriken zählten EINTRÄGE statt TAGE.** Genau der Defekt, den
A31 (Anmerkung 64) für die Statistik beseitigt hat — in den Erfolgen hatte er
überlebt. Deshalb kamen die Abzeichen nach einem Timeline-Import „vorverdient"
an: ein Tag mit dreißig Besuchen zählte dreißigmal. Das ist die eigentliche
Ursache, die Schwellen waren nur der sichtbare Teil.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Metric, Source,
                        User, UserRole)
from app.services.achievements import _beyond, _evaluate, compute
from app.modules.registry import Module


# --------------------------------------------------------------------------- #
# (a) Die Marken oberhalb der höchsten Stufe
# --------------------------------------------------------------------------- #
def _spec(**tiers):
    return {"id": "x", "label": "X", "metric": "event_count", "tiers": tiers}


MOD = Module(key="test", label="Test")


def test_unter_platin_bleibt_alles_wie_bisher():
    a = _evaluate(_spec(bronze=5, silber=25, gold=100, platin=500), MOD, 30)
    assert a.tier == "silber"
    assert a.next_tier == "gold" and a.next_threshold == 100
    assert a.beyond_top is False and a.marks_passed == 0


def test_ueber_platin_zaehlt_die_marke_weiter():
    """Der Fall aus Anmerkung 99: 1.240 bei Platin 500 -> nächste Marke 2.500."""
    a = _evaluate(_spec(bronze=5, silber=25, gold=100, platin=500), MOD, 1240)
    assert a.tier == "platin", "die Stufe bleibt die höchste erreichte"
    assert a.next_tier is None, "es gibt keine fünfte Stufe — nur eine Marke"
    assert a.beyond_top is True
    assert a.next_threshold == 2500
    assert a.marks_passed == 1, "1.000 ist passiert"
    assert 0 < a.progress < 1, "der Balken sagt wieder etwas"


def test_frisch_erreichtes_platin_startet_bei_null():
    """Wer Platin gerade eben erreicht, darf nicht „fast geschafft" anzeigen —
    der Boden ist die Stufe selbst, nicht die vorige Marke."""
    a = _evaluate(_spec(bronze=5, silber=25, gold=100, platin=500), MOD, 500)
    assert a.beyond_top is True
    assert a.next_threshold == 1000
    assert a.progress == 0.0


def test_marken_sind_erzeugt_und_hoeren_nie_auf():
    """Eine Regel statt einer Liste — eine Liste hätte wieder ein Ende."""
    value = 500
    for _ in range(30):                       # 30 Marken weit: immer noch eine da
        _, _, nxt = _beyond(value, 500)
        assert nxt > value
        value = nxt
    assert value > 10 ** 12


def test_marken_sind_runde_zahlen():
    for value, expect in [(600, 1000), (1000, 2500), (3000, 5000),
                          (6000, 10000), (11000, 25000)]:
        assert _beyond(value, 500)[2] == expect


# --------------------------------------------------------------------------- #
# (b) Wetter zählt Tage, nicht Einträge
# --------------------------------------------------------------------------- #
def _sunny_event(db, user, day: int, hours: float, title: str):
    """Ein bestätigtes Ereignis am 2024-06-<day> mit Sonnenstunden."""
    ev = Event(user_id=user.id, title=title, category="event",
               date_start=datetime(2024, 6, day, 12, 0),
               date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.google_timeline)
    db.add(ev)
    db.flush()
    db.add(Metric(event_id=ev.id, key="sunshine_h", value=hours,
                  source=Source.weather))
    return ev


def _achievement(db, user, ach_id: str):
    return next(a for a in compute(db, user.id).achievements if a.id == ach_id)


def test_sonnentage_zaehlen_tage_nicht_besuche(db, user):
    """Der importierte Tag: dreißig Besuche, ein Wetter. Vor F19 zählte das
    dreißig „Tage mit mindestens 10 Sonnenstunden"."""
    for i in range(30):
        _sunny_event(db, user, 3, 11.2, f"Besuch {i}")
    db.commit()

    assert _achievement(db, user, "sun_worshipper").value == 1


def test_verschiedene_tage_zaehlen_einzeln(db, user):
    for day in (3, 4, 5):
        for i in range(4):
            _sunny_event(db, user, day, 11.2, f"Besuch {day}-{i}")
    db.commit()

    assert _achievement(db, user, "sun_worshipper").value == 3


def test_sonnenstunden_werden_nicht_vervielfacht(db, user):
    """Die Summe ist die Summe über TAGE — sonst wächst sie mit der Zahl der
    Besuche, und ein Import macht aus 11 Stunden 330."""
    for i in range(30):
        _sunny_event(db, user, 3, 11.0, f"Besuch {i}")
    _sunny_event(db, user, 4, 9.0, "Einzelner Tag")
    db.commit()

    assert _achievement(db, user, "sun_collector").value == 20


def test_reisetag_zaehlt_den_vorsichtigeren_wert(db, user):
    """Der Sonderfall hinter dem Tages-Vertreter: an einem Reisetag tragen die
    Einträge NICHT dasselbe Wetter (die Anreicherung hängt an Ort und Datum).
    Dann zählt der niedrigere Wert — das verzögert einen Erfolg und löst ihn
    nie zu früh aus, und diese Richtung ist der ganze Sinn von Anmerkung 103."""
    _sunny_event(db, user, 3, 11.0, "Vormittags im Norden")
    _sunny_event(db, user, 3, 3.0, "Abends im Süden")
    db.commit()

    # Der Tag qualifiziert sich (ein Eintrag über der Schwelle) …
    assert _achievement(db, user, "sun_worshipper").value == 1
    # … und geht mit dem niedrigeren Wert in die Summe ein, nicht mit beiden.
    assert _achievement(db, user, "sun_collector").value == 3


def test_unbestaetigtes_zaehlt_weiterhin_nicht(db, user):
    ev = _sunny_event(db, user, 3, 11.2, "Vorschlag")
    ev.confirmed = ConfirmState.unconfirmed
    db.commit()

    assert _achievement(db, user, "sun_worshipper").value == 0


def test_fremde_daten_zaehlen_nicht(db, user):
    other = User(oidc_subject="other", email="o@example.org",
                 display_name="Andere", role=UserRole.user)
    db.add(other)
    db.commit()
    _sunny_event(db, other, 3, 11.2, "Fremder Besuch")
    db.commit()

    assert _achievement(db, user, "sun_worshipper").value == 0


def test_ereignis_ohne_datum_kippt_die_zaehlung_nicht(db, user):
    """Ohne Datum gibt es keinen Kalendertag — die Zeile darf die Gruppierung
    nicht zu einer Sammelgruppe „NULL" verschmelzen lassen."""
    ev = Event(user_id=user.id, title="Irgendwann", category="event",
               date_start=None, date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual)
    db.add(ev)
    db.flush()
    db.add(Metric(event_id=ev.id, key="sunshine_h", value=11.0,
                  source=Source.weather))
    _sunny_event(db, user, 3, 11.2, "Mit Datum")
    db.commit()

    assert _achievement(db, user, "sun_worshipper").value == 1


def test_schwellen_verlangen_mehr_als_einen_tag(db, user):
    """Die Bronze-Stufen bei 1 („einmal gefroren") waren keine Leistung."""
    from app.modules.registry import registry

    weather = next(m for m in registry.modules if m.key == "weather")
    for spec in weather.achievements:
        assert spec["tiers"]["bronze"] >= 3, spec["id"]
