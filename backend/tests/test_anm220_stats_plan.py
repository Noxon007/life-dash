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
weil der Aufrufer sie BENUTZT"). Deshalb schreibt der Test jetzt an der
VERBINDUNG mit und prüft die Anweisungen, die tatsächlich abgeschickt wurden.
In dieser Fassung meldet SQLite auf dem kaputten Stand
`CORRELATED SCALAR SUBQUERY`, und der Test wird rot.
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


def _plan_lines(db, statement: str, parameters) -> list[str]:
    """EXPLAIN QUERY PLAN für eine bereits abgeschickte Anweisung."""
    raw = db.connection().connection
    cur = raw.cursor()
    try:
        cur.execute("EXPLAIN QUERY PLAN " + statement, parameters or ())
        return [row[-1] for row in cur.fetchall()]
    finally:
        cur.close()


def _wx():
    return (Metric.source == Source.weather,
            Metric.key.in_(so._WX_KEYS), Metric.value.isnot(None))


def test_plan_evaluates_the_parent_lookup_once(db, user):
    """Der Plan wertet die Eltern-Suche EINMAL aus, nicht je äußerer Zeile.

    **Warum hier nicht auf einen bestimmten Index geprüft wird.** Der erste
    Entwurf dieses Tests verlangte `ix_events_parent_event_id` im Plan — und
    fiel damit auf dieselbe Nase wie der Defekt: welchen Index SQLite nimmt,
    steht nicht in unserer Hand. Auf der leeren Testdatenbank wählte sogar die
    KAPUTTE Fassung den richtigen. Ein Wächter, dessen Aussage vom Zufall
    abhängt, ist keiner.

    Was nicht vom Zufall abhängt, ist die Zeile daneben:

        LIST SUBQUERY 2              ← einmal, Ergebnis gemerkt
        CORRELATED SCALAR SUBQUERY 1 ← je Zeile der äußeren Tabelle neu

    Das ist eine Eigenschaft des SQL und nicht der Schätzung. Sie unterscheidet
    die beiden Fassungen in jedem Fall, auf jedem Bestand.
    """
    if db.bind.dialect.name != "sqlite":
        return                      # EXPLAIN QUERY PLAN gibt es nur hier

    with _recording(db) as seen:
        so.weather_values(db, user.id)

    plans = [(sql, _plan_lines(db, sql, params))
             for sql, params in seen if sql.lstrip().upper().startswith("SELECT")]
    assert plans, "weather_values hat gar nichts abgefragt"

    guilty = [(sql, lines) for sql, lines in plans
              if any("CORRELATED" in line for line in lines)]
    assert not guilty, (
        "weather_values schickt eine Abfrage mit korrelierter Unterabfrage — "
        "die wird je Zeile der äußeren Tabelle neu ausgewertet, und genau das "
        "hat den Statistik-Reiter fünfzehn Sekunden gekostet.\n\n"
        + "\n\n".join(f"{sql}\n  " + "\n  ".join(lines) for sql, lines in guilty))

    # Die Gegenprobe: die Eltern-Suche muss überhaupt noch stattfinden. Ohne
    # sie wäre der Test auch dann grün, wenn jemand die zweite Abfrage einfach
    # entfernt — und die wärmste Reise hieße wieder wie ihr erstes Kind.
    assert any(any("LIST SUBQUERY" in line for line in lines)
               for _sql, lines in plans), (
        "Keine eigenständige Unterabfrage im Plan — sucht weather_values die "
        "Elternzeilen noch (Anmerkung 199)?")


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
