"""A46 — importierte Besuche enden am Tag, an dem sie begonnen haben.

Gemeldet aus dem Betrieb: über 2.000 Zwei-Tages-Ereignisse aus dem
Google-Import, hunderte davon für den Wohnort. Ursache war eine einzige
Zeile — `date_start`/`date_end` roh aus dem Besuch übernommen, also wurde
jede Nacht im eigenen Bett ein mehrtägiges Ereignis.

Geprüft werden zwei Seiten und die Naht dazwischen:

* der **Import** schneidet neue Besuche,
* der **Aufräum-Lauf** schneidet die vorhandenen,
* und beide erkennen sich gegenseitig wieder. Das ist der teure Teil: Zeilen
  aus der Zeit vor A46 tragen den nackten Hash. Wer beim Re-Import nur nach
  den neuen Teil-Schlüsseln fragt, hält jeden Alt-Bestand für unbekannt und
  legt ihn ein zweites Mal an — DANEBEN, nicht anstatt.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import ConfirmState, Event, Source
from app.routers.events import multiday_visits, split_multiday_visits
from app.routers.tracks import import_timeline
from app.services import visitsplit


# --------------------------------------------------------------------------- #
# Helfer
# --------------------------------------------------------------------------- #
def _visit(start: str, end: str, place: str = "pid-home") -> dict:
    """Geräte-Export mit einem einzigen visit-Segment."""
    return {"semanticSegments": [{
        "startTime": start, "endTime": end,
        "visit": {
            "probability": 1.0,
            "topCandidate": {
                "placeId": place,
                "semanticType": "HOME",
                "placeLocation": {"latLng": "51.94°, 8.87°"},
            },
        },
    }]}


def _events(db, user) -> list[Event]:
    return (db.query(Event)
            .filter(Event.user_id == user.id, Event.source == Source.google_timeline)
            .order_by(Event.date_start).all())


# --------------------------------------------------------------------------- #
# Die Regel selbst
# --------------------------------------------------------------------------- #
def test_day_pieces_leaves_a_single_day_alone():
    lo = datetime(2026, 7, 1, 10, 0)
    hi = datetime(2026, 7, 1, 12, 30)
    assert visitsplit.day_pieces(lo, hi) == [(lo, hi)]


def test_day_pieces_cuts_at_midnight_without_overlap():
    lo = datetime(2026, 7, 1, 22, 0)
    hi = datetime(2026, 7, 2, 7, 0)
    pieces = visitsplit.day_pieces(lo, hi)
    assert pieces == [
        (lo, datetime(2026, 7, 1, 23, 59, 59)),
        (datetime(2026, 7, 2, 0, 0, 0), hi),
    ]
    # Kein Stück reicht in den Tag des anderen — sonst hätte man den Fehler
    # nur um eine Sekunde schmaler gemacht.
    assert pieces[0][1] < pieces[1][0]
    assert pieces[0][1].date() != pieces[1][0].date()


def test_day_pieces_covers_every_day_in_between():
    pieces = visitsplit.day_pieces(datetime(2026, 7, 1, 22, 0),
                                   datetime(2026, 7, 4, 6, 0))
    assert [p[0].day for p in pieces] == [1, 2, 3, 4]


def test_day_pieces_refuses_absurd_spans():
    """Ein „Besuch" über Wochen ist keine Nacht — daraus 30 Zeilen zu machen
    wäre genau das Rauschen, gegen das A46 antritt. Die leere Liste zwingt den
    Aufrufer, die Entscheidung zu sehen."""
    assert visitsplit.day_pieces(datetime(2026, 1, 1),
                                 datetime(2026, 3, 1)) == []


def test_piece_id_keeps_the_bare_key_for_one_piece():
    """Ein eintägiger Besuch muss sich beim Re-Import selbst wiedererkennen —
    und Bestandszeilen tragen genau diesen nackten Schlüssel."""
    assert visitsplit.piece_id("abc", 0, 1) == "abc"
    assert visitsplit.piece_ids("abc", 3) == ["abc#1", "abc#2", "abc#3"]


# --------------------------------------------------------------------------- #
# Der Import
# --------------------------------------------------------------------------- #
def test_import_splits_a_visit_over_midnight(db, user):
    result = import_timeline(
        _visit("2026-07-01T22:00:00+02:00", "2026-07-02T07:00:00+02:00"),
        auto_resolve=False, db=db, user=user)

    assert result.visits_created == 2
    assert result.visits_split == 1
    rows = _events(db, user)
    assert [e.date_start.day for e in rows] == [1, 2]
    # Kein Ereignis reicht mehr über eine Tagesgrenze — das ist die Zusage.
    assert all(e.date_start.date() == e.date_end.date() for e in rows)
    # Die Zeitpunkte selbst bleiben auf die Sekunde erhalten: korrigiert wird
    # die Übernahme, nicht die Beobachtung.
    assert rows[0].date_start.hour == 22
    assert rows[1].date_end.hour == 7


def test_import_leaves_a_same_day_visit_untouched(db, user):
    result = import_timeline(
        _visit("2026-07-01T10:00:00+02:00", "2026-07-01T12:00:00+02:00"),
        auto_resolve=False, db=db, user=user)
    assert result.visits_created == 1
    assert result.visits_split == 0
    assert "#" not in (_events(db, user)[0].external_id or "")


def test_import_reports_what_it_could_not_split(db, user):
    """Zu lang zum Schneiden heißt: bleibt eine Zeile — und wird GENANNT.
    Eine Aktion, die still anders handelt als angekündigt, ist der Defekt,
    den dieses Projekt am häufigsten findet."""
    result = import_timeline(
        _visit("2026-01-01T10:00:00+01:00", "2026-03-01T10:00:00+01:00"),
        auto_resolve=False, db=db, user=user)
    assert result.visits_created == 1
    assert result.visits_too_long == 1
    assert result.visits_split == 0


def test_reimport_of_split_visits_creates_nothing(db, user):
    payload = _visit("2026-07-01T22:00:00+02:00", "2026-07-02T07:00:00+02:00")
    import_timeline(payload, auto_resolve=False, db=db, user=user)
    again = import_timeline(payload, auto_resolve=False, db=db, user=user)
    assert again.visits_created == 0
    assert again.skipped_duplicates == 1
    assert len(_events(db, user)) == 2


def test_reimport_recognises_rows_from_before_a46(db, user):
    """**Der teure Fall.** Eine Zeile aus einem Import vor A46 trägt den
    NACKTEN Hash und reicht über zwei Tage. Der nächste Re-Import darf sie
    nicht für unbekannt halten — sonst stünden die zwei Tagesstücke NEBEN
    dem alten Zwei-Tages-Ereignis, und der Bestand wäre schlechter als vorher.
    """
    payload = _visit("2026-07-01T22:00:00+02:00", "2026-07-02T07:00:00+02:00")
    # Den Zustand HERSTELLEN, nicht simulieren: so sah die Zeile bis 0.38 aus.
    from app.routers.tracks import _normalize
    visits, _ = _normalize(payload)
    db.add(Event(user_id=user.id, title="Besuch: Zuhause",
                 date_start=datetime(2026, 7, 1, 22, 0),
                 date_end=datetime(2026, 7, 2, 7, 0),
                 category="event", confirmed=ConfirmState.confirmed,
                 source=Source.google_timeline,
                 external_id=visits[0]["hash"]))
    db.commit()

    result = import_timeline(payload, auto_resolve=False, db=db, user=user)
    assert result.visits_created == 0
    assert result.skipped_duplicates == 1
    assert len(_events(db, user)) == 1


# --------------------------------------------------------------------------- #
# Der Aufräum-Lauf für den Bestand
# --------------------------------------------------------------------------- #
@pytest.fixture()
def legacy_visits(db, user):
    """Drei Zeilen, wie sie ein Import vor A46 hinterlassen hat."""
    rows = [
        Event(user_id=user.id, title="Besuch: Zuhause",
              date_start=datetime(2026, 7, 1, 22, 0),
              date_end=datetime(2026, 7, 2, 7, 0),
              category="event", confirmed=ConfirmState.confirmed,
              source=Source.google_timeline, external_id="hash-a"),
        Event(user_id=user.id, title="Besuch: Zuhause",
              date_start=datetime(2026, 7, 3, 23, 0),
              date_end=datetime(2026, 7, 4, 6, 0),
              category="event", confirmed=ConfirmState.confirmed,
              source=Source.google_timeline, external_id="hash-b"),
        # Eintägig — hat nichts zu tun mit dem Lauf.
        Event(user_id=user.id, title="Besuch: Bäcker",
              date_start=datetime(2026, 7, 5, 8, 0),
              date_end=datetime(2026, 7, 5, 8, 20),
              category="event", confirmed=ConfirmState.confirmed,
              source=Source.google_timeline, external_id="hash-c"),
    ]
    db.add_all(rows)
    db.commit()
    return rows


def test_preview_names_the_number_of_rows_afterwards(db, user, legacy_visits):
    """Anmerkung 110: Was eine Aktion tut, muss VORHER dastehen — und die
    eigentliche Zahl ist nicht „2 Ereignisse", sondern „4 Zeilen danach"."""
    preview = multiday_visits(db=db, user=user)
    assert preview["events"] == 2
    assert preview["rows_after"] == 4
    assert len(preview["list"]) == 2


def test_split_run_matches_its_own_preview(db, user, legacy_visits):
    preview = multiday_visits(db=db, user=user)
    result = split_multiday_visits(db=db, user=user)
    assert result["events"] == preview["events"]
    # Die Vorschau nennt Zeilen NACHHER, der Lauf neue Zeilen — dieselbe
    # Aussage von zwei Seiten. Gehen sie auseinander, hat der Nutzer etwas
    # anderes gesehen als bekommen.
    assert result["created"] == preview["rows_after"] - preview["events"]

    # 2 geschnittene Besuche → 4 Zeilen, dazu der eintägige, den der Lauf
    # nicht anfassen darf.
    rows = _events(db, user)
    assert len(rows) == 5
    assert all(e.date_start.date() == e.date_end.date() for e in rows)


def test_split_run_keeps_the_existing_row_as_the_first_piece(db, user,
                                                            legacy_visits):
    """An einem Besuch können Fotos und Metriken hängen; die zeigen auf DIESE
    ID. Das erste Stück muss deshalb die vorhandene Zeile bleiben."""
    keep = legacy_visits[0].id
    split_multiday_visits(db=db, user=user)
    survivor = db.get(Event, keep)
    assert survivor is not None
    assert survivor.date_start == datetime(2026, 7, 1, 22, 0)
    assert survivor.date_end.date() == survivor.date_start.date()
    # Der Schlüssel wird auf die Teil-Form gezogen, damit ein späterer
    # Re-Import den Besuch wiedererkennt.
    assert survivor.external_id == "hash-a#1"


def test_split_run_is_idempotent(db, user, legacy_visits):
    split_multiday_visits(db=db, user=user)
    again = split_multiday_visits(db=db, user=user)
    assert again["events"] == 0
    assert again["created"] == 0
    assert len(_events(db, user)) == 5


def test_split_run_never_touches_other_sources(db, user):
    """Von Hand erfasst bleibt mehrtägig — genau darum geht es. Der Lauf
    korrigiert eine Übernahme, keine Aussage."""
    mine = Event(user_id=user.id, title="Urlaub auf Mallorca",
                 date_start=datetime(2026, 7, 1), date_end=datetime(2026, 7, 5),
                 category="trip", confirmed=ConfirmState.confirmed,
                 source=Source.manual)
    proposal = Event(user_id=user.id, title="Dänemark 2024",
                     date_start=datetime(2026, 8, 1), date_end=datetime(2026, 8, 3),
                     category="trip", confirmed=ConfirmState.unconfirmed,
                     source=Source.immich, external_id="immich:album:x")
    db.add_all([mine, proposal])
    db.commit()

    assert multiday_visits(db=db, user=user)["events"] == 0
    split_multiday_visits(db=db, user=user)
    assert db.get(Event, mine.id).date_end == datetime(2026, 7, 5)
    assert db.get(Event, proposal.id).date_end == datetime(2026, 8, 3)


def test_split_run_skips_events_with_day_children_and_says_so(db, user):
    """Ein geschnittener Elternteil ließe seine F7-Kinder auf einer Spanne
    sitzen, die es nicht mehr gibt."""
    parent = Event(user_id=user.id, title="Besuch: Zuhause",
                   date_start=datetime(2026, 7, 1, 22, 0),
                   date_end=datetime(2026, 7, 2, 7, 0),
                   category="event", confirmed=ConfirmState.confirmed,
                   source=Source.google_timeline, external_id="hash-p")
    db.add(parent)
    db.commit()
    db.add(Event(user_id=user.id, title="Besuch: Zuhause — Tag 1",
                 date_start=datetime(2026, 7, 1), date_end=datetime(2026, 7, 1),
                 category="event", confirmed=ConfirmState.confirmed,
                 source=Source.google_timeline, parent_event_id=parent.id))
    db.commit()

    preview = multiday_visits(db=db, user=user)
    assert preview["events"] == 0
    assert preview["with_children"] == 1


def test_split_run_reports_spans_it_refuses(db, user):
    db.add(Event(user_id=user.id, title="Besuch: Ferienhaus",
                 date_start=datetime(2026, 1, 1), date_end=datetime(2026, 3, 1),
                 category="event", confirmed=ConfirmState.confirmed,
                 source=Source.google_timeline, external_id="hash-long"))
    db.commit()
    preview = multiday_visits(db=db, user=user)
    assert preview["events"] == 0
    assert preview["too_long_count"] == 1
    assert preview["max_days"] == visitsplit.SPLIT_MAX_DAYS


def test_import_after_the_cleanup_run_creates_nothing(db, user):
    """Die Naht: erst schneidet der Lauf den Bestand, dann kommt derselbe
    Export noch einmal. Erkennen sich die beiden Seiten nicht wieder, ist
    jede Nacht danach doppelt da."""
    payload = _visit("2026-07-01T22:00:00+02:00", "2026-07-02T07:00:00+02:00")
    from app.routers.tracks import _normalize
    visits, _ = _normalize(payload)
    db.add(Event(user_id=user.id, title="Besuch: Zuhause",
                 date_start=datetime(2026, 7, 1, 22, 0),
                 date_end=datetime(2026, 7, 2, 7, 0),
                 category="event", confirmed=ConfirmState.confirmed,
                 source=Source.google_timeline,
                 external_id=visits[0]["hash"]))
    db.commit()

    split_multiday_visits(db=db, user=user)
    assert len(_events(db, user)) == 2

    result = import_timeline(payload, auto_resolve=False, db=db, user=user)
    assert result.visits_created == 0
    assert len(_events(db, user)) == 2
