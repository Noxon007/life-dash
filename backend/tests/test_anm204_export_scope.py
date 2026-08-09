"""Anmerkung 204 — der Export liest nur sein eigenes Konto.

`metrics` und `event_entity_links` tragen kein `user_id`; ihr Besitzer ist das
Ereignis, an dem sie hängen. Der Export lud sie deshalb VOLLSTÄNDIG — jede
Zeile jedes Kontos — und suchte in Python die eigenen heraus. Herausgekommen
ist dabei immer das Richtige; bezahlt hat es der Nutzer mit einer Sicherung,
die mit dem Bestand FREMDER Konten wächst. Am Demo-Bestand gemessen: ein
zweites Konto kostete ein Drittel der Exportzeit (4,8 s → 6,4 s), für Daten,
von denen keine Zeile in die Datei kommt.

**Zwei Zusicherungen, und die zweite ist die eigentliche.** Dass nichts
Fremdes in der Datei landet, war nie das Problem — das galt vorher auch. Der
Defekt war, dass es dafür GELESEN wurde. Ein Test, der nur den Inhalt prüft,
bliebe grün, wenn der Filter morgen wieder nach Python wanderte.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import event

from app.models import (ConfirmState, Entity, Event, EventEntityLink, Location,
                        Metric, Source, User, UserRole)
from app.routers.data import export_data


def _life(db, owner, tag: str) -> str:
    """Ein winziges Leben: Ort, Ereignis, Entität, Verknüpfung, Messwert."""
    loc = Location(user_id=owner.id, name=f"Ort {tag}", lat=53.5, lng=9.9,
                   city="Hamburg", country="Deutschland")
    db.add(loc)
    db.flush()
    ev = Event(user_id=owner.id, title=f"Eintrag {tag}", category="event",
               date_start=datetime(2020, 5, 1), location_id=loc.id,
               confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.flush()
    ent = Entity(user_id=owner.id, type="animal", name=f"Tier {tag}",
                 confirmed=ConfirmState.confirmed)
    db.add(ent)
    db.flush()
    db.add(EventEntityLink(event_id=ev.id, entity_id=ent.id, role="subject"))
    db.add(Metric(event_id=ev.id, key="temperature_c", value=21.0,
                  source=Source.weather))
    db.commit()
    return ev.id


@pytest.fixture()
def stranger(db):
    other = User(oidc_subject="stranger", email="stranger@example.org",
                 display_name="Fremdes Konto", role=UserRole.user)
    db.add(other)
    db.commit()
    return other


def test_a_foreign_account_never_reaches_the_file(db, user, stranger):
    """Die Zusicherung, die schon vorher galt — hier, damit die Reparatur sie
    nicht im Vorbeigehen kaputt macht."""
    mine = _life(db, user, "meins")
    theirs = _life(db, stranger, "fremd")

    payload = export_data(db=db, user=user)
    assert [e["id"] for e in payload["events"]] == [mine]
    assert {m["event_id"] for m in payload["metrics"]} == {mine}
    assert {l["event_id"] for l in payload["event_entity_links"]} == {mine}
    assert theirs not in {m["event_id"] for m in payload["metrics"]}


def test_the_foreign_rows_are_not_even_read(db, user, stranger):
    """**Der eigentliche Befund.** Gezählt werden die Zeilen, die aus der
    Datenbank KOMMEN — nicht die, die in der Datei landen.

    Das ist der Unterschied zwischen „filtert richtig" und „fragt richtig",
    und nur der zweite wächst nicht mit fremden Konten. Der Zähler hängt an
    den ORM-Objekten und nicht an der Zeichenkette der Abfrage: ob dort
    `JOIN` oder `IN (SELECT …)` steht, ist die Entscheidung des Autors — dass
    keine fremde Zeile geladen wird, ist die Zusage.
    """
    _life(db, user, "meins")
    for i in range(5):
        _life(db, stranger, f"fremd{i}")

    seen: list[str] = []

    def watch(_conn, _cursor, statement, *_rest):
        seen.append(" ".join(statement.split()).lower())

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", watch)
    try:
        loaded = {"metrics": 0, "links": 0}

        def count(target, _ctx):
            if isinstance(target, Metric):
                loaded["metrics"] += 1
            elif isinstance(target, EventEntityLink):
                loaded["links"] += 1

        event.listen(Metric, "load", count)
        event.listen(EventEntityLink, "load", count)
        try:
            export_data(db=db, user=user)
        finally:
            event.remove(Metric, "load", count)
            event.remove(EventEntityLink, "load", count)
    finally:
        event.remove(engine, "before_cursor_execute", watch)

    # Ein eigener Messwert, eine eigene Verknüpfung — und fünf fremde von
    # jedem. Wer sie alle lädt, kommt auf sechs.
    assert loaded == {"metrics": 1, "links": 1}, (
        f"{loaded} — der Export lädt fremde Zeilen und wirft sie danach weg; "
        "genau daran wächst die Exportzeit mit dem Bestand anderer Konten")
