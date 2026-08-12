"""Anmerkung 220 — der Statistik-Reiter darf nicht nach außen korrelieren.

**Warum dieser Test die FORM prüft und nicht das Ergebnis.** Die alte Fassung
von `weather_values` war fachlich richtig: sie fand genau die Elternzeilen, die
sie finden sollte. Sie brauchte dafür auf dem ausgelieferten Demo-Bestand
fünfzehn Sekunden — für null Zeilen. Ein Test über die Ergebnismenge wäre also
grün gewesen, und war es die ganze Zeit.

**Warum kein Zeittest.** Der naheliegende Wächter („die Abfrage muss unter
einer Sekunde bleiben") wäre hier ausgerechnet auf die Weise blind, die den
Defekt verursacht hat. Ob die kaputte Fassung schnell oder langsam ist, hängt
davon ab, welchen Index SQLite wählt, und das hängt an der Reihenfolge, in der
die Indizes angelegt wurden — `Table.indexes` ist eine `set`. Gemessen an drei
unabhängig gebauten Demo-Beständen: 1,33 s, 14,6 s, 15,0 s. Ein Zeittest wäre
auf jedem dritten Bau grün gewesen. Genau daran ist `tools/_measure_api.py`
gescheitert: es misst eine Datenbank, die es sich selbst anlegt, und hatte
Glück (Befund 2 der Durchsicht vom 2026-08-12).

Was NICHT vom Zufall abhängt, ist die Form der Abfrage. Eine Unterabfrage, die
nach außen korreliert, wird je Zeile der äußeren Tabelle einmal ausgewertet;
eine, die für sich steht, einmal insgesamt. Das ist eine Eigenschaft des SQL,
nicht des Planers — und deshalb prüfbar, ohne eine Uhr zu befragen.

**Gefahren gegen den kaputten Stand — und der erste Entwurf war grün.** Er
prüfte `parents_with_weather()` direkt und blieb es auch, als `weather_values`
testweise wieder das alte `EXISTS` schrieb: die Funktion gab es ja noch, nur
rief sie niemand mehr (CLAUDE.md, „grün, weil es die Funktion GIBT — nicht,
weil der Aufrufer sie BENUTZT"). Deshalb schreibt der Test an der VERBINDUNG
mit und prüft die Anweisungen, die tatsächlich abgeschickt wurden.

**Der zweite Entwurf war dann in der CI rot, und zwar zu Recht.** Er las
`EXPLAIN QUERY PLAN` und verlangte, dass nirgends `CORRELATED` steht — das
hielt auf SQLite 3.53 und fiel auf der älteren SQLite der CI sofort um, an
einer völlig gesunden Abfrage: die reparierte Fassung trägt in ihrer
eigenständigen Unterabfrage weiterhin ein `EXISTS` auf `metrics`. Ob ein
Planer das so benennt oder wegoptimiert, ist eine Eigenschaft der VERSION —
also derselbe Fehler wie beim Index, nur eine Ebene höher. Geprüft wird
deshalb, was oben schon steht: die Form des abgeschickten SQL.
"""
from __future__ import annotations

import contextlib
import datetime

from sqlalchemy import event
from sqlalchemy.orm import aliased

from app.models import Event, Location, Metric, Source, User, UserRole
from app.services import stats_overview as so


@contextlib.contextmanager
def _recording(db):
    """Sammelt die Anweisungen, die WIRKLICH über die Verbindung gehen.

    **Das ist der ganze Unterschied zwischen diesem Wächter und seinem ersten
    Entwurf.** Der prüfte `parents_with_weather()` direkt — und blieb grün,
    als ich `weather_values` testweise auf den kaputten Stand zurücksetzte:
    die Funktion GAB es ja noch, nur rief sie niemand mehr. Genau die Sorte
    Prüfung, die CLAUDE.md unter „Prüfungen, die nichts prüfen" führt.

    Mitgeschrieben wird deshalb an der Verbindung. Was hier ankommt, ist das,
    was der Aufrufer tatsächlich abgeschickt hat.
    """
    seen: list[tuple[str, object]] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        seen.append((statement, parameters))

    event.listen(db.bind, "before_cursor_execute", _before)
    try:
        yield seen
    finally:
        event.remove(db.bind, "before_cursor_execute", _before)


def _wx():
    return (Metric.source == Source.weather,
            Metric.key.in_(so._WX_KEYS), Metric.value.isnot(None))


def test_the_parent_lookup_does_not_correlate_outwards(db, user):
    """Die Eltern-Suche steht für sich, statt je äußerer Zeile neu zu laufen.

    **Warum hier nicht auf einen bestimmten Index geprüft wird.** Der erste
    Entwurf dieses Tests verlangte `ix_events_parent_event_id` im Plan — und
    fiel damit auf dieselbe Nase wie der Defekt: welchen Index SQLite nimmt,
    steht nicht in unserer Hand. Auf der leeren Testdatenbank wählte sogar die
    KAPUTTE Fassung den richtigen. Ein Wächter, dessen Aussage vom Zufall
    abhängt, ist keiner.

    **Und warum inzwischen auch nicht mehr auf den PLAN.** Die zweite Fassung
    verlangte, dass in `EXPLAIN QUERY PLAN` nirgends `CORRELATED` steht. Das
    hat lokal (SQLite 3.53) gehalten und ist in der CI (ältere SQLite) sofort
    rot geworden — an einer Abfrage, die völlig in Ordnung ist: die reparierte
    Fassung trägt in ihrer eigenständigen Unterabfrage weiterhin ein `EXISTS`
    auf `metrics`, korreliert auf das KIND, und das ist gewollt (es läuft über
    `ix_metrics_event_id`). Ob ein Planer das `CORRELATED SCALAR SUBQUERY`
    nennt oder wegoptimiert, ist eine Eigenschaft der Version — **derselbe
    Fehler wie beim Index, eine Ebene höher.**

    Der Docstring dieser Datei sagt es selbst: *„Was NICHT vom Zufall abhängt,
    ist die Form der Abfrage… eine Eigenschaft des SQL, nicht des Planers."*
    Also wird das SQL geprüft, und zwar an der einen Stelle, an der sich die
    beiden Fassungen unterscheiden:

        kaputt:     … EXISTS (SELECT … FROM events AS events_1
                              WHERE events_1.parent_event_id = events.id …)
        repariert:  … events.id IN (SELECT events_1.parent_event_id
                              FROM events AS events_1 WHERE …)

    Die kaputte Fassung NENNT die äußere Zeile in der Unterabfrage; die
    reparierte nicht. Das steht im abgeschickten Text und gilt in jeder
    SQLite-Version und auf PostgreSQL genauso — der Test läuft deshalb auch
    nicht mehr nur auf einem Dialekt.
    """
    with _recording(db) as seen:
        so.weather_values(db, user.id)

    sent = [" ".join(sql.split())
            for sql, _p in seen if sql.lstrip().upper().startswith("SELECT")]
    assert sent, "weather_values hat gar nichts abgefragt"

    # Die Korrelation nach außen: die Unterabfrage über die Kindzeilen nennt
    # die Kennung der ÄUSSEREN Zeile. Genau das lief je äußerer Zeile einmal.
    guilty = [s for s in sent if "events_1.parent_event_id = events.id" in s]
    assert not guilty, (
        "Die Eltern-Suche korreliert wieder nach außen — sie wird damit je "
        "Zeile der äußeren Tabelle neu ausgewertet, und genau das hat den "
        "Statistik-Reiter fünfzehn Sekunden gekostet.\n\n" + "\n\n".join(guilty))

    # Die Gegenprobe: die Eltern-Suche muss überhaupt noch stattfinden. Ohne
    # sie wäre der Test auch dann grün, wenn jemand die zweite Abfrage einfach
    # entfernt — und die wärmste Reise hieße wieder wie ihr erstes Kind.
    assert any("in (select events_1.parent_event_id" in s.lower() for s in sent), (
        "Keine eigenständige Unterabfrage über die Elternkennungen — sucht "
        "weather_values die Elternzeilen noch (Anmerkung 199)?")


def test_weather_values_still_finds_the_parent(db, user):
    """Die Form hat sich geändert, die Antwort nicht.

    Ein Eltern-Ereignis trägt selbst kein Wetter und muss trotzdem in
    `events` stehen — daran hängt der Name der wärmsten Reise (Anmerkung 199).
    """
    loc = Location(user_id=user.id, name="Sevilla, Spanien", city="Sevilla",
                   lat=37.39, lng=-5.99)
    db.add(loc)
    db.flush()
    parent = Event(user_id=user.id, title="Andalusien", category="trip",
                   date_start=datetime.datetime(2019, 5, 1), location_id=loc.id)
    db.add(parent)
    db.flush()
    kid = Event(user_id=user.id, title="Andalusien — Tag 1", category="trip",
                date_start=datetime.datetime(2019, 5, 1), location_id=loc.id,
                parent_event_id=parent.id)
    db.add(kid)
    db.flush()
    db.add(Metric(event_id=kid.id, key="temperature_c", value=31.5,
                  source=Source.weather))
    db.commit()

    src = so.weather_values(db, user.id)
    assert parent.id in src.events, (
        "Das Eltern-Ereignis fehlt — die wärmste Reise fiele auf den "
        "Kindtitel „Andalusien — Tag 1“ zurück (Anmerkung 199).")
    assert kid.id in src.events
    assert src.events[parent.id].title == "Andalusien"


def test_parent_of_another_user_stays_out(db, user):
    """Das Kind eines fremden Kontos zieht kein fremdes Elternteil herein."""
    stranger = User(oidc_subject="anm220-fremd", email="fremd@example.org",
                    display_name="Fremder", role=UserRole.user)
    db.add(stranger)
    db.flush()
    theirs = Event(user_id=stranger.id, title="Fremde Reise", category="trip",
                   date_start=datetime.datetime(2019, 5, 1))
    db.add(theirs)
    db.flush()
    kid = Event(user_id=stranger.id, title="Fremd — Tag 1", category="trip",
                date_start=datetime.datetime(2019, 5, 1),
                parent_event_id=theirs.id)
    db.add(kid)
    db.flush()
    db.add(Metric(event_id=kid.id, key="temperature_c", value=31.5,
                  source=Source.weather))
    db.commit()

    assert theirs.id not in so.weather_values(db, user.id).events
