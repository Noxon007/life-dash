"""0.36.0 — P5.1 (offline erfassen) und die zweite Hälfte von F1 (Tages-Vorschlag).

Beide Pakete haben ihren gefährlichen Teil NICHT dort, wo man ihn vermutet:

* Bei P5.1 ist das Puffern selbst Frontend-Sache (localStorage, geprüft von
  `tools/check-p51-outbox.js`). Am Server hängt nur eine Eigenschaft, und die
  entscheidet, ob aus „nie etwas verlieren" ein „alles doppelt" wird: dieselbe
  Erfassung darf beim Wiederholen kein zweites Fragment erzeugen — und ohne
  `client_id` MUSS sie es sehr wohl, weil zwei gleiche Sätze von Hand zwei
  Erfassungen sind.
* Bei F1 ist der Vorschlag schnell gebaut; die Zusage aus 0.15.0 ist das
  Empfindliche: **die KI fasst `note` nie an.** Ein Endpunkt, der „hilfreich"
  gleich speichert, bräche sie, ohne dass ein Bildschirm es zeigt.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Fragment, Location,
                        MediaRef, Metric, Source, User, UserRole)
from app.routers import ingest as ingest_router
from app.routers.ingest import ingest
from app.routers.journal import suggest_day
from app.schemas import FragmentCreate

DAY = date(2026, 7, 12)


@pytest.fixture(autouse=True)
def clear_seen():
    """Das Doppel-Gedächtnis lebt im Prozess — zwischen zwei Tests wäre es
    sonst ein gemeinsamer Zustand und der zweite Test läse den ersten."""
    ingest_router._seen.clear()
    yield
    ingest_router._seen.clear()


def _second_user(db):
    u = User(oidc_subject="other-sub", email="other@example.org",
             display_name="Zweiter", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def _event(db, user, *, title="Adler gesehen", confirmed=True, hour=9,
           category="sighting", location=None, note=None):
    ev = Event(
        user_id=user.id, title=title, category=category, note=note,
        date_start=datetime(DAY.year, DAY.month, DAY.day, hour, 30),
        date_end=datetime(DAY.year, DAY.month, DAY.day, hour, 30),
        date_precision=DatePrecision.exact, source=Source.manual,
        confirmed=ConfirmState.confirmed if confirmed else ConfirmState.unconfirmed,
        location_id=location.id if location else None,
    )
    db.add(ev)
    db.commit()
    return ev


# --------------------------------------------------------------------------- #
# P5.1 — die Warteschlange darf wiederholen, ohne zu verdoppeln
# --------------------------------------------------------------------------- #
def test_same_client_id_creates_one_fragment(db, user):
    """Der Fall, für den es das Feld gibt: die Antwort ging unterwegs verloren,
    der Client sendet dieselbe Erfassung erneut."""
    payload = FragmentCreate(raw_text="Adler in Detmold gesehen", client_id="abc-1")
    first = ingest(payload, db=db, user=user)
    second = ingest(payload, db=db, user=user)

    assert db.query(Fragment).count() == 1
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.fragment.id == first.fragment.id
    # Und der zweite Aufruf liefert dieselben Vorschläge, nicht eine leere Liste:
    # die Warteschlange zeigt danach dasselbe wie beim ersten Versuch.
    assert [e.id for e in second.events] == [e.id for e in first.events]


def test_same_text_without_client_id_stays_two_captures(db, user):
    """Ohne Kennung ist Doppeltes Absicht — zweimal „Kaffee" sind zwei Kaffees.
    Eine Entduplizierung nach Textgleichheit wäre stilles Datenschlucken."""
    ingest(FragmentCreate(raw_text="Kaffee getrunken"), db=db, user=user)
    ingest(FragmentCreate(raw_text="Kaffee getrunken"), db=db, user=user)
    assert db.query(Fragment).count() == 2


def test_different_client_id_creates_two(db, user):
    ingest(FragmentCreate(raw_text="Kaffee getrunken", client_id="a"), db=db, user=user)
    ingest(FragmentCreate(raw_text="Kaffee getrunken", client_id="b"), db=db, user=user)
    assert db.query(Fragment).count() == 2


def test_client_id_is_scoped_per_user(db, user):
    """A12: Die Kennung kommt vom Client und ist damit frei wählbar. Ohne die
    Nutzer-Bindung könnte ein fremdes `client_id` das Fragment eines anderen
    zurückliefern — aus einer Bequemlichkeit würde ein Datenleck."""
    other = _second_user(db)
    ingest(FragmentCreate(raw_text="Mein Text", client_id="kollision"), db=db, user=user)
    mine = ingest(FragmentCreate(raw_text="Fremder Text", client_id="kollision"),
                  db=db, user=other)
    assert mine.duplicate is False
    assert mine.fragment.raw_text == "Fremder Text"
    assert db.query(Fragment).count() == 2


# --------------------------------------------------------------------------- #
# F1 — der Vorschlag ist ein Vorschlag
# --------------------------------------------------------------------------- #
def test_suggestion_never_writes(db, user):
    """Die Kernzusage: der Endpunkt liest. Kein neues Ereignis, keine Notiz."""
    _event(db, user)
    before_events = db.query(Event).count()
    before_notes = [e.note for e in db.query(Event).all()]

    res = suggest_day(day=DAY, db=db, user=user)

    assert res.text
    assert db.query(Event).count() == before_events
    assert [e.note for e in db.query(Event).all()] == before_notes


def test_suggestion_uses_confirmed_and_reports_the_rest(db, user):
    _event(db, user, title="Adler gesehen", confirmed=True, hour=9)
    _event(db, user, title="Vermutete Wanderung", confirmed=False, hour=14)

    res = suggest_day(day=DAY, db=db, user=user)

    assert res.used_events == 1
    assert res.skipped_unconfirmed == 1
    assert "Adler" in res.text
    # Der unbestätigte Titel darf nicht im Vorschlag stehen — sonst wäre eine
    # Vermutung als eigene Erinnerung formuliert.
    assert "Wanderung" not in res.text


def test_empty_day_says_so_instead_of_inventing(db, user):
    res = suggest_day(day=DAY, db=db, user=user)
    assert res.text is None
    assert res.used_events == 0


def test_journal_entry_does_not_summarise_itself(db, user):
    """Sonst fasst der zweite Aufruf den ersten Vorschlag zusammen — der Text
    frisst sich selbst und wird mit jedem Klick länger und leerer."""
    _event(db, user, title="Tagebuch — 12.07.2026", category="journal",
           note="Ein langer Tag mit vielen Gedanken.")
    res = suggest_day(day=DAY, db=db, user=user)
    assert res.text is None
    assert res.used_events == 0


def test_material_carries_place_and_weather(db, user):
    """Was der Vorschlag nicht sieht, kann er nicht schreiben — Ort und Wetter
    sind die zwei Angaben, die einen Tag am ehesten wiedererkennbar machen."""
    loc = Location(user_id=user.id, name="Detmold", lat=51.93, lng=8.87)
    db.add(loc)
    db.commit()
    ev = _event(db, user, location=loc)
    db.add(Metric(event_id=ev.id, key="temp_max_c", value=29.0, unit="°C",
                  source=Source.weather))
    db.add(Metric(event_id=ev.id, key="weather", value_text="Klar",
                  source=Source.weather))
    db.commit()

    from app.services.journal import day_material
    lines, used, skipped = day_material(db, user.id, DAY)

    assert used == 1
    assert "Detmold" in lines[0]
    assert "29 °C" in lines[0] and "Klar" in lines[0]


def test_day_photos_count_as_material(db, user):
    """F18/Anmerkung 106: Fotos hängen wahlweise am TAG. Wer sie über Ereignisse
    sucht, findet genau die nicht — derselbe Fehler wie beim Löschen und im
    Export, und hier hieße er „an dem Tag war nichts"."""
    db.add(MediaRef(user_id=user.id, provider="local", external_id="a.jpg",
                    captured_at=datetime(DAY.year, DAY.month, DAY.day, 15, 0)))
    db.commit()

    from app.services.journal import day_material
    lines, used, _ = day_material(db, user.id, DAY)

    assert used == 0                       # ein Foto ist kein Ereignis
    assert any("Foto" in line for line in lines)


def test_other_users_day_stays_invisible(db, user):
    """A12: in JEDER Abfrage."""
    other = _second_user(db)
    _event(db, other, title="Fremdes Ereignis")
    res = suggest_day(day=DAY, db=db, user=user)
    assert res.text is None


def test_provider_outage_is_an_answer_not_an_empty_draft(db, user, monkeypatch):
    from fastapi import HTTPException

    from app.ai.base import ProviderUnavailable

    _event(db, user)

    def _boom(self, day, lines):
        raise ProviderUnavailable("Modell offline")

    monkeypatch.setattr("app.ai.mock.MockProvider.summarize_day", _boom)
    with pytest.raises(HTTPException) as exc:
        suggest_day(day=DAY, db=db, user=user)
    assert exc.value.status_code == 503


def test_provider_without_the_ability_returns_no_text(db, user, monkeypatch):
    """Der Standard in `LLMProvider` ist None — ein Provider, der das nicht kann,
    liefert keinen erfundenen Text, sondern nichts. Die Oberfläche sagt es dann."""
    _event(db, user)
    monkeypatch.setattr("app.ai.mock.MockProvider.summarize_day",
                        lambda self, day, lines: None)
    res = suggest_day(day=DAY, db=db, user=user)
    assert res.text is None
    assert res.used_events == 1        # gesehen hat er den Tag trotzdem
