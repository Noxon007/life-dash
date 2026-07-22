"""Durchsicht der Immich-Integration nach 0.37 (Anmerkung 111).

Zwei Befunde, die 404 bestehende Tests nicht bemerkt haben — beide an einer
Naht: die eine zwischen Life-Dash und der fremden API, die andere zwischen
Stufe 1 und Stufe 2.

**(a) Die falsche Zeitangabe.** `AssetResponseDto` hat zwei Zeitfelder, und die
Spezifikation sagt ausdrücklich, welches wofür ist: `fileCreatedAt` ist
**UTC**, `localDateTime` ist „the local date and time … timezone-agnostic …
used for timeline grouping by *local* days". Life-Dash schnitt bei beiden
einfach die Zone ab und bekam damit UTC-Wanduhrzeit — ein Foto vom 13. Mai
01:30 Uhr aus Berlin landete auf dem **12.** Am Tag hängen aber der Behälter
(F18) und der Platz eines Vorschlags.

**(b) Zwei Stufen, zwei Meinungen über die Fotos eines Tages.** Stufe 2 legt
unbestätigte Vorschläge an; Stufe 1 sah in ihnen ganz normale Ereignisse und
hängte ihnen Fotos an — obwohl Anmerkung 107 (Fall 6) festhält, dass ein
Vorschlag seine Bilder erst BESITZT, wenn ein Mensch bestätigt hat. Derselbe
Fehler wie in Anmerkung 106: eine Regel an zwei Orten widerspricht sich still.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, MediaRef, Source,
                        User, UserRole)
from app.services import immich as api
from app.services.immich_link import (MACHINE_SOURCES, candidates,
                                      day_candidates, detach_machine_links,
                                      targets)


# --------------------------------------------------------------------------- #
# (a) Ortszeit, nicht UTC
# --------------------------------------------------------------------------- #
def test_local_date_time_wins_over_utc():
    """Der gemeldete Kern: 13. Mai 01:30 in Berlin darf nicht der 12. sein."""
    asset = {"fileCreatedAt": "2024-05-12T23:30:00.000Z",
             "localDateTime": "2024-05-13T01:30:00.000Z"}
    when = api.asset_time(asset)
    assert when == datetime(2024, 5, 13, 1, 30)
    assert when.date() == date(2024, 5, 13)


def test_exif_with_offset_is_read_as_local_time():
    """`dateTimeOriginal` trägt üblicherweise den ursprünglichen Versatz —
    ohne Zone gelesen ist das genau die Ortszeit."""
    asset = {"exifInfo": {"dateTimeOriginal": "2024-05-13T01:30:00.000+02:00"}}
    assert api.asset_time(asset) == datetime(2024, 5, 13, 1, 30)


def test_utc_only_is_converted_not_truncated():
    """Bleibt nur `fileCreatedAt`, ist es laut Spezifikation UTC. Die Zone
    abzuschneiden wäre der ursprüngliche Fehler; umgerechnet wird sie."""
    asset = {"fileCreatedAt": "2024-05-12T23:30:00.000Z"}
    when = api.asset_time(asset)
    reference = datetime.fromisoformat("2024-05-12T23:30:00+00:00").astimezone()
    assert when == reference.replace(tzinfo=None)


def test_an_asset_without_any_time_has_none():
    assert api.asset_time({}) is None
    assert api.asset_time({"localDateTime": "kaputt"}) is None


def test_the_day_bucket_follows_the_local_day(db, user):
    """Warum die Zeitzone hier überhaupt zählt: der Behälter IST das Datum.
    Eine Stunde daneben ist harmlos, ein Tag daneben legt das Foto unter den
    falschen Tageskopf — und bei einem Fotovorschlag unter den falschen Platz."""
    from app.services.immich_source import cluster_assets

    assets = [{"id": f"a{i}", "ownerId": "me", "visibility": "timeline",
               "localDateTime": f"2024-05-13T0{i}:30:00.000Z",
               "fileCreatedAt": f"2024-05-12T2{i}:30:00.000Z",
               "exifInfo": {"latitude": 52.5, "longitude": 13.4, "city": "Berlin"}}
              for i in range(1, 5)]
    props = cluster_assets(assets, "me")
    assert len(props) == 1
    assert props[0].slot == "immich:day:2024-05-13:Berlin"


# --------------------------------------------------------------------------- #
# (b) Wem gehören die Fotos eines Tages?
# --------------------------------------------------------------------------- #
def _proposal(db, user, *, confirmed=False, day=date(2024, 7, 12)):
    ev = Event(user_id=user.id, title="34 Fotos in Detmold", category="event",
               date_start=datetime(day.year, day.month, day.day),
               date_end=datetime(day.year, day.month, day.day, 23, 59, 59),
               date_precision=DatePrecision.day, source=Source.immich,
               confirmed=ConfirmState.confirmed if confirmed
               else ConfirmState.unconfirmed,
               external_id=f"immich:day:{day.isoformat()}:Detmold")
    db.add(ev)
    db.commit()
    return ev


def test_a_photo_proposal_does_not_get_its_own_photos(db, user):
    """Anmerkung 107, Fall 6: Ein Vorschlag ZEIGT die Fotos, besitzt sie aber
    erst nach dem Bestätigen. Stufe 1 hielt ihn für ein gewöhnliches Ereignis
    und hätte ihm zwölf Bilder angehängt — dann hätte eine Ablehnung sehr wohl
    etwas rückgängig zu machen."""
    _proposal(db, user)
    assert candidates(db, user.id) == []


def test_a_confirmed_proposal_stays_out_too(db, user):
    """Auch bestätigt bleibt es ein maschinell erzeugter Eintrag. Die Fotos
    stehen unter dem Tageskopf direkt daneben — eine Regel, nicht zwei."""
    _proposal(db, user, confirmed=True)
    assert candidates(db, user.id) == []


def test_a_self_recorded_event_still_gets_its_photos(db, user):
    """Die Gegenprobe: Was ein MENSCH erfasst hat, ist eine Aussage über den
    Tag und bekommt seine Bilder weiterhin direkt. Ein Filter, der zu viel
    wegnimmt, ist von einem fehlenden nicht zu unterscheiden."""
    db.add(Event(user_id=user.id, title="Konzert", category="concert",
                 date_start=datetime(2024, 7, 12, 20),
                 date_end=datetime(2024, 7, 12, 23),
                 date_precision=DatePrecision.exact, source=Source.manual,
                 confirmed=ConfirmState.confirmed))
    db.commit()
    assert [e.title for e in candidates(db, user.id)] == ["Konzert"]


def test_the_day_of_a_proposal_becomes_a_photo_target(db, user):
    """Die Kehrseite, ohne die der Fix eine Verschlechterung wäre: Ein
    Vorschlag für ein Jahr ohne Timeline-Daten hätte sonst ÜBERHAUPT kein Bild
    neben sich — und beurteilen soll man ihn ja gerade an den Fotos."""
    _proposal(db, user)
    assert day_candidates(db, user.id) == [date(2024, 7, 12)]


def test_one_rule_feeds_both_lists(db, user):
    """`targets()` ist die eine Stelle, an der steht, wohin ein Foto gehört
    (Anmerkung 106). Nach dem Fix muss der Vorschlag dort als TAG auftauchen
    und nicht als Ereignis — sonst gäbe es die Regel wieder zweimal."""
    _proposal(db, user)
    kinds = [kind for kind, _ in targets(db, user.id)]
    assert kinds == ["day"]


def test_existing_links_on_proposals_are_released(db, user):
    """Anmerkung 106 hat es teuer gelernt: Ohne das Lösen gälten genau die
    betroffenen Fotos über `seen` als vergeben, und die Korrektur erreichte
    die Bestandsdaten nie. Instanzen, die 0.37 gefahren haben, tragen Fotos an
    Fotovorschlägen."""
    ev = _proposal(db, user)
    db.add(MediaRef(user_id=user.id, event_id=ev.id, provider="immich",
                    external_id="asset-1"))
    db.commit()

    assert detach_machine_links(db, user.id) == 1
    assert db.query(MediaRef).count() == 0
    assert detach_machine_links(db, user.id) == 0, "zweiter Lauf: Nulldurchlauf"


def test_uploaded_files_are_never_detached(db, user):
    """Anmerkung 57, die Grenze, an der es teuer würde: `provider='local'` ist
    eine hochgeladene Datei und gehört zur Lebensdatenbank. Sie darf von einer
    Neuberechnung nie angefasst werden."""
    ev = _proposal(db, user)
    db.add(MediaRef(user_id=user.id, event_id=ev.id, provider="local",
                    external_id="mein-bild.jpg"))
    db.commit()

    detach_machine_links(db, user.id)
    assert db.query(MediaRef).count() == 1


def test_machine_sources_is_the_single_list(db):
    """Der Grund für den Fehler war, dass `google_timeline` an zwei Stellen
    einzeln stand. Wächst die Liste, muss sie an EINER Stelle wachsen."""
    assert set(MACHINE_SOURCES) == {Source.google_timeline, Source.immich}


def test_a_day_shows_its_whole_course_not_just_the_evening(db, user):
    """Immich liefert neueste zuerst; die ersten zwölf eines Urlaubstags mit 300
    Fotos waren damit die zwölf spätesten — der Abend, und vom Tag nichts.
    Dieselbe Lehre wie bei der Fotoleiste (Anmerkung 110), nur serverseitig."""
    from app.services.immich_link import MAX_PER_EVENT, _spread_over_day

    assets = [{"id": f"a{h:02d}", "localDateTime": f"2024-07-12T{h:02d}:00:00.000Z"}
              for h in range(23, -1, -1)]          # neueste zuerst, wie Immich
    picked = _spread_over_day(assets, set())

    assert len(picked) == MAX_PER_EVENT
    hours = [api.asset_time(a).hour for a in picked]
    assert hours == sorted(hours), "nicht chronologisch"
    assert hours[0] <= 2 and hours[-1] >= 20, f"nur ein Ausschnitt: {hours}"
    # Zweiter Lauf, dieselbe Auswahl — sonst tauschen sich die Bilder eines
    # Tages bei jedem Durchgang aus.
    assert [a["id"] for a in _spread_over_day(assets, set())] == \
           [a["id"] for a in picked]


def test_already_linked_photos_are_not_picked_again(db, user):
    """`seen` ist die Entduplizierung des ganzen Laufs — sie muss VOR dem
    Greifen wirken, sonst verbraucht ein schon vergebenes Foto einen der zwölf
    Plätze und der Tag zeigt elf."""
    from app.services.immich_link import _spread_over_day

    assets = [{"id": f"a{i}", "localDateTime": f"2024-07-12T{i:02d}:00:00.000Z"}
              for i in range(20)]
    picked = _spread_over_day(assets, {"a0", "a1", "a2"})
    assert {"a0", "a1", "a2"}.isdisjoint({a["id"] for a in picked})
    assert len(picked) == 12


def test_other_users_links_are_not_detached(db, user):
    """A12: in JEDER Abfrage."""
    other = User(oidc_subject="o", email="o@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    ev = _proposal(db, other)
    db.add(MediaRef(user_id=other.id, event_id=ev.id, provider="immich",
                    external_id="fremd-1"))
    db.commit()

    assert detach_machine_links(db, user.id) == 0
    assert db.query(MediaRef).count() == 1
