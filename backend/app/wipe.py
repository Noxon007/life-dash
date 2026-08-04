"""Löschen: das Losungswort und die Reihenfolge — an EINER Stelle.

Es gibt zwei Löschwege, und sie sind bewusst verschieden: `/api/data/wipe-mine`
räumt EIN Konto ab, `/api/admin/wipe-data` die ganze Instanz. Verschieden
bleiben darf, WEN es trifft. Zwei Dinge dürfen nicht auseinanderlaufen, weil
beide still falsch werden können (CLAUDE.md, „Regeln, die sich verdoppeln"):

1. **Das Losungswort.** Bis 0.39 verlangte die Kontoseite `LOESCHEN` und die
   Systemseite `LÖSCHEN`, und der englische Katalog hatte für dieselbe Frage
   zwei Antworten. Hier steht jetzt, was gilt — und zwar großzügig: eine
   Bestätigung ist kein Passwort. Sie soll verhindern, dass jemand aus
   Versehen klickt, nicht, dass jemand mit englischer Tastatur nicht
   weiterkommt.

2. **Die Reihenfolge.** Kinder vor Eltern. Ein Eintrag, der hier fehlt,
   fällt auf SQLite NIE auf (dort werden Fremdschlüssel nicht erzwungen) und
   bricht auf PostgreSQL das ganze Löschen ab — nachdem die Zeilen davor
   bereits als gelöscht protokolliert wurden. Genau so ist
   `baseline_locations` durchgerutscht: die Zeile zeigt auf `locations`,
   niemand löschte sie vorher, und das Log meldete einen Erfolg, den es nicht
   gab.

Wer eine neue Tabelle mit Nutzerdaten anlegt, trägt sie hier ein. Der Test
`test_wipe_covers_every_user_table` besteht darauf.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (  # noqa: F401 — die Modelle stehen in WIPE_ORDER
    BaselineLocation,
    DayMetric,
    Entity,
    Event,
    EventEntityLink,
    Fragment,
    Location,
    MediaRef,
    Metric,
    Track,
)

# Was als Bestätigung durchgeht — Groß/Klein und Leerraum egal.
# `LÖSCHEN` ist das deutsche Wort, `DELETE` das englische, `LOESCHEN` die
# umlautfreie Schreibweise für Tastaturen ohne Ö. Alle drei meinen dasselbe.
DELETE_WORDS = frozenset({"LÖSCHEN", "LOESCHEN", "DELETE"})


def is_delete_word(typed: str) -> bool:
    """Hat der Nutzer das Losungswort getippt?"""
    return (typed or "").strip().upper() in DELETE_WORDS


# Löschreihenfolge, Kinder zuerst. Das dritte Feld sagt, WORAN die Zeile
# hängt — nur der Konto-Weg braucht es, der Admin-Weg leert ganze Tabellen.
#
#   "user"          — die Zeile trägt selbst ein `user_id`
#   "event"         — die Zeile hängt ausschließlich an einem Ereignis
#   "user_or_event" — beides möglich; ein Bild kann dem Konto gehören, ohne
#                     an einem Ereignis zu hängen (F18). Nur über `event_id`
#                     gefiltert blieben genau diese Zeilen stehen — während
#                     ihre Dateien gelöscht würden.
WIPE_ORDER: tuple[tuple[type, str, str], ...] = (
    (Metric, "metrics", "event"),
    (DayMetric, "day_metrics", "user"),
    (MediaRef, "media_refs", "user_or_event"),
    (EventEntityLink, "event_entity_links", "event"),
    (BaselineLocation, "baseline_locations", "user"),
    (Track, "tracks", "user"),
    (Event, "events", "user"),
    (Entity, "entities", "user"),
    (Location, "locations", "user"),
    (Fragment, "fragments", "user"),
)

# Tabellen, die bewusst NICHT gelöscht werden — der Test unten liest diese
# Liste, damit „vergessen" und „absichtlich gelassen" unterscheidbar bleiben.
WIPE_KEEPS = {
    "users": "Konten bleiben; gelöscht werden Daten, nicht Menschen.",
    "jobs": "Lauf-Protokoll, keine Lebensdaten. Ein leerer Verlauf verschleiert.",
    "city_info": "Wikipedia-Zwischenspeicher, gehört keinem Konto (A42).",
}


def wipe_user_rows(db: Session, user_id: str,
                   log: logging.Logger | None = None) -> dict[str, int]:
    """Löscht alle Zeilen EINES Kontos — ohne das Konto selbst und ohne Dateien.

    Es gibt drei Aufrufer, die genau das brauchen: „Alle meine Daten löschen"
    (A33), „Nutzer löschen" im Admin-Bereich, und indirekt der Rundumschlag.
    Bis 0.39 stand die Reihenfolge dreimal ausgeschrieben da, und alle drei
    Kopien hatten dieselbe Lücke — was nicht überrascht: die dritte war eine
    Abschrift der zweiten. Die Dateien bleiben Sache des Aufrufers, weil die
    Reihenfolge dort entscheidend ist (Anmerkung 59: erst Zeilen, dann Bilder).

    Committet NICHT — der Aufrufer entscheidet, was in derselben Transaktion
    noch passieren muss (beim Nutzer-Löschen etwa die Konto-Zeile selbst).
    """
    events = select(Event.id).where(Event.user_id == user_id).scalar_subquery()
    deleted: dict[str, int] = {}
    for model, key, scope in WIPE_ORDER:
        if scope == "event":
            cond = model.event_id.in_(events)
        elif scope == "user_or_event":
            # F18: Ein Bild kann dem Konto gehören, ohne an einem Ereignis zu
            # hängen. Nur über `event_id` gefiltert blieben genau diese Zeilen
            # stehen — während ihre Dateien gelöscht werden.
            cond = (model.user_id == user_id) | model.event_id.in_(events)
        else:
            cond = model.user_id == user_id
        deleted[key] = db.query(model).filter(cond).delete(synchronize_session=False)
        if log:
            # A34: je Tabelle eine Zeile. Bei großen Beständen ist ein Lauf
            # ohne Spur von einem Hänger nicht zu unterscheiden.
            log.info("  %s: %d Zeilen gelöscht", key, deleted[key])
    return deleted
