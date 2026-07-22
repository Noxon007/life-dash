"""P2.1 — Fotos aus Immich an Ereignisse hängen (Schicht-4-Ableitung).

Getrennt vom reinen API-Client (`immich.py`), damit der Client ohne Datenbank
testbar bleibt und die Zuordnungsregeln an einer Stelle stehen.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Event, MediaRef, Source
from app.services import immich as api
from app.sqlutil import day_parts

log = logging.getLogger("lifedash.immich")

PROVIDER = "immich"
# Höchstens so viele Fotos je Ziel verknüpfen. Ein Urlaubstag kann 300
# Bilder haben — die gehören in Immich, nicht als Kachelwand in den Zeitstrahl.
MAX_PER_EVENT = 12
# Von einer MASCHINE erzeugte Einträge (Anmerkung 111). Sie bekommen ihre Fotos
# über den Tag, nicht direkt — der eine Satz, aus dem `candidates` und
# `day_candidates` beide folgen. Vorher stand `google_timeline` an beiden
# Stellen einzeln, und als Stufe 2 eine zweite maschinelle Quelle hinzufügte,
# stimmten die beiden Listen nicht mehr überein.
MACHINE_SOURCES = (Source.google_timeline, Source.immich)


def candidates(db: Session, user_id: str) -> list[Event]:
    """Datierte Ereignisse, die noch keine Immich-Fotos tragen.

    Vage datierte Ereignisse fallen schon in `window_for` heraus; sie hier
    mitzuzählen würde den Fortschrittsbalken dauerhaft bei „noch offen"
    stehen lassen.

    F7: Hat ein Ereignis **Tages-Kinder**, bekommt es selbst KEINE Fotos —
    die Anreicherung hängt an den Kindern, pro Tag (genau wie das Wetter). Der
    Reise-Eintrag zeigt die Fotos seiner Tage aggregiert. Sonst lägen an einer
    Woche Urlaub die ersten zwölf Bilder am Reise-Eintrag und nichts an den
    einzelnen Tagen — die Beschwerde, die zu dieser Regel führte.

    **Maschinell erzeugte Einträge sind hier NICHT dabei** (Anmerkung 106,
    erweitert in 111): sie bekommen ihre Fotos über den TAG, siehe
    `day_candidates`. Das sind zwei Quellen:

    * `google_timeline` — ein Besuch ist „ich war um 14:00 in der
      Kaiserstraße", und ein Foto von 20:00 gehört nicht dorthin, nur weil
      dieser Besuch zufällig als erster geprüft wurde.
    * `immich` — die Fotovorschläge aus Stufe 2 (P2.1). Sie sind aus denselben
      Fotos ENTSTANDEN; ihnen die Bilder anzuhängen hieße, dass ein Vorschlag
      seinen eigenen Anlass besitzt, bevor ein Mensch ihn bestätigt hat.

    Der gemeinsame Nenner ist nicht „importiert", sondern **von einer Maschine
    gemacht**. Was ein Mensch selbst erfasst hat, ist eine Aussage über den Tag
    und bekommt seine Fotos direkt; alles andere sammelt der Tag ein.
    """
    from sqlalchemy.orm import selectinload

    # Kinder und Medien mitladen (selectinload), sonst löst der Filter unten
    # pro Ereignis zwei Lazy-Queries aus — bei zehntausenden Ereignissen wird
    # der Kandidaten-Aufbau sonst zur eigentlichen Bremse (N+1).
    rows = (db.query(Event)
            .options(selectinload(Event.children), selectinload(Event.media))
            .filter(Event.user_id == user_id, Event.date_start.isnot(None),
                    Event.source.notin_(MACHINE_SOURCES))
            .all())
    return [e for e in rows
            if api.window_for(e) is not None
            and not e.children
            and not any(m.provider == PROVIDER for m in e.media)]


# --------------------------------------------------------------------------- #
# Anmerkung 106 — der Tag als Ziel, nicht ein beliebiger Besuch
#
# Nach einem Timeline-Import trägt ein Tag dutzende Besuche. Jeder hatte ein
# Fenster von ±6 Stunden (`exact`-Präzision), und drei Orte einer Stadt liegen
# alle im 25-km-Umkreis — der Ort unterschied also nichts. Ein Foto landete
# beim ERSTEN Besuch, dessen Fenster es erwischte, und „erster" war die
# Reihenfolge einer Abfrage ohne ORDER BY. Dazu zeigt der verdichtete
# Zeitstrahl (A39) den Vertreter `min(id)` — bei UUIDs praktisch zufällig, also
# fast nie derselbe. Gemessen: vier Fotos verknüpft, null sichtbar.
#
# F18 hat den richtigen Behälter schon gebaut: `MediaRef` ohne `event_id`, am
# Kalendertag von `captured_at`. Er war nur nie an Immich angeschlossen.
# --------------------------------------------------------------------------- #
def day_candidates(db: Session, user_id: str) -> list[date]:
    """Tage mit maschinell erzeugten Einträgen, an denen noch keine Fotos hängen.

    Bewusst nur solche Tage: Tage ohne jeden Eintrag sind nicht Teil der
    Lebensdatenbank, und Fotos an sie zu hängen hieße, die halbe Immich-
    Bibliothek zu importieren.

    Anmerkung 111: Neben den importierten Besuchen zählen jetzt auch die Tage
    der **Fotovorschläge** aus Stufe 2 — und zwar aus einem greifbaren Grund:
    ein Vorschlag „34 Fotos in Detmold" für ein Jahr ohne Timeline-Daten hätte
    sonst überhaupt kein Bild neben sich, und der Nutzer soll ihn ja gerade
    ANHAND der Fotos beurteilen. Die Bilder hängen am Tag, nicht am Vorschlag —
    lehnt er ab, ist nichts rückgängig zu machen.
    """
    y, m, d = day_parts(Event.date_start)
    days = (db.query(y, m, d)
            .filter(Event.user_id == user_id,
                    Event.source.in_(MACHINE_SOURCES),
                    Event.date_start.isnot(None))
            .group_by(y, m, d).all())
    ym, mm, dm = day_parts(MediaRef.captured_at)
    done = (db.query(ym, mm, dm)
            .filter(MediaRef.user_id == user_id,
                    MediaRef.provider == PROVIDER,
                    MediaRef.event_id.is_(None),
                    MediaRef.captured_at.isnot(None))
            .group_by(ym, mm, dm).all())
    have = {(int(a), int(b), int(c)) for a, b, c in done}
    return sorted(date(int(a), int(b), int(c)) for a, b, c in days
                  if (int(a), int(b), int(c)) not in have)


def _spread_over_day(assets: list[dict], seen: set[str]) -> list[dict]:
    """Die zwölf Bilder GLEICHMÄSSIG über den Tag greifen, nicht vorne abschneiden.

    Anmerkung 111: Immich liefert neueste zuerst. Ein Urlaubstag mit 300 Fotos
    bekam damit die zwölf **spätesten** — also den Abend, und vom Tag nichts.
    Chronologisch sortieren und gleichmäßig greifen zeigt stattdessen den
    Verlauf. Dieselbe Überlegung wie bei der Fotoleiste im Zeitstrahl
    (Anmerkung 110), hier auf der Serverseite.

    Deterministisch, nicht zufällig: derselbe Tag soll bei einem zweiten Lauf
    nicht plötzlich andere Bilder tragen.
    """
    usable = [a for a in assets if a.get("id") not in seen]
    usable.sort(key=lambda a: (api.asset_time(a) or datetime.max, a.get("id") or ""))
    if len(usable) <= MAX_PER_EVENT:
        return usable
    step = len(usable) / MAX_PER_EVENT
    return [usable[int(i * step)] for i in range(MAX_PER_EVENT)]


def link_day(db: Session, user, day: date, url: str, key: str,
             seen: set[str]) -> int:
    """Sucht Fotos für EINEN Tag und hängt sie an das Datum. Ohne Commit.

    Kein Orts-Abgleich, anders als beim Ereignis: der Tag ist ein Behälter der
    ZEITachse (Anmerkung 87), und ein Ortsfilter auf einen Behälter, der
    ausdrücklich nicht vom Ort handelt, wäre in sich widersprüchlich. Wer
    vormittags Besuche in Düsseldorf hat und abends in München fotografiert,
    hat ein Foto von diesem Tag — und sonst hätte es gar keinen Platz.
    """
    start = datetime(day.year, day.month, day.day)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    added = 0
    for asset in _spread_over_day(api.search_assets(url, key, start, end), seen):
        if added >= MAX_PER_EVENT:
            break
        when = api.asset_time(asset)
        if when is None:          # ohne Zeit kein Tag — der Behälter ist das Datum
            continue
        db.add(MediaRef(
            user_id=user.id, event_id=None, provider=PROVIDER,
            external_id=asset["id"], captured_at=when,
            mime=asset.get("originalMimeType"),
            width=(asset.get("exifInfo") or {}).get("exifImageWidth"),
            height=(asset.get("exifInfo") or {}).get("exifImageHeight"),
            sort_order=1000 + added,
        ))
        seen.add(asset["id"])
        added += 1
    return added


def detach_machine_links(db: Session, user_id: str) -> int:
    """Löst Immich-Verweise von maschinell erzeugten Einträgen (Anm. 106/111).

    Einmalig wirksam, danach ein Nulldurchlauf. Erlaubt, weil Verweise eine
    Ableitung sind (Anmerkung 57) — die Bilder liegen in Immich. Ohne das
    behielten bereits verknüpfte Fotos ihr altes Ziel, und der neue Lauf fände
    sie über `seen` als „schon vergeben": die Korrektur käme nie bei den
    Bestandsdaten an. Genau diese Falle beschreibt Anmerkung 106, und sie gilt
    für die zweite maschinelle Quelle unverändert — Instanzen, die 0.37
    gefahren haben, tragen Fotos an Fotovorschlägen.
    """
    ids = [r[0] for r in
           db.query(MediaRef.id)
           .join(Event, Event.id == MediaRef.event_id)
           .filter(MediaRef.user_id == user_id, MediaRef.provider == PROVIDER,
                   Event.source.in_(MACHINE_SOURCES)).all()]
    if not ids:
        return 0
    (db.query(MediaRef).filter(MediaRef.id.in_(ids))
     .delete(synchronize_session=False))
    db.commit()
    log.info("Immich: %d Verknüpfungen von maschinellen Einträgen gelöst — "
             "sie werden an den Tag gehängt (user=%s)", len(ids), user_id)
    return len(ids)


# Alter Name, damit nichts still bricht, was ihn noch ruft.
detach_visit_links = detach_machine_links


def linked_asset_ids(db: Session, user_id: str) -> set[str]:
    """Alle Immich-Asset-IDs, die diesem Nutzer schon irgendwo hängen.

    Grundlage der Entduplizierung: Ein Foto gehört zu EINEM Moment, nicht zu
    jedem Timeline-Besuch desselben Tages. An einem Städtetag liegen dutzende
    Besuche im selben Tagesfenster und (bei GPS-Fotos) im selben 25-km-Umkreis;
    ohne diese Menge landete dasselbe Bild an ihnen allen (und GPS-lose Fotos
    an wirklich jedem Ereignis des Tages)."""
    rows = (db.query(MediaRef.external_id)
            .filter(MediaRef.user_id == user_id, MediaRef.provider == PROVIDER)
            .all())
    return {r[0] for r in rows}


def link_event(db: Session, user, event: Event, url: str, key: str,
               seen: set[str] | None = None) -> int:
    """Sucht Fotos für EIN Ereignis und verknüpft sie. Ohne Commit.

    `seen`: Asset-IDs, die diesem Nutzer schon (an DIESEM oder einem anderen
    Ereignis) hängen. Wird über den ganzen Lauf mitgeführt, damit jedes Foto
    genau einmal verknüpft wird — beim ersten passenden Ereignis. Wer den Satz
    nicht übergibt (Einzelaufruf/Test), bekommt wenigstens die Entduplizierung
    innerhalb des Ereignisses.
    """
    window = api.window_for(event)
    if window is None:
        return 0
    assets = api.search_assets(url, key, *window)
    known = {m.external_id for m in event.media} if seen is None else seen
    added = 0
    for asset in assets:
        if added >= MAX_PER_EVENT:
            break
        if asset["id"] in known or not api.matches(event, asset):
            continue
        db.add(MediaRef(
            user_id=user.id, event_id=event.id, provider=PROVIDER,
            external_id=asset["id"], captured_at=api.asset_time(asset),
            mime=asset.get("originalMimeType"),
            width=(asset.get("exifInfo") or {}).get("exifImageWidth"),
            height=(asset.get("exifInfo") or {}).get("exifImageHeight"),
            sort_order=1000 + added,   # hinter den selbst hochgeladenen Bildern
        ))
        known.add(asset["id"])   # sofort merken -> kein zweites Ereignis bekommt es
        added += 1
    return added


def targets(db: Session, user_id: str) -> list[tuple[str, object]]:
    """Was in dieser Runde Fotos bekommen kann — **die Regel, an einer Stelle.**

    Reihenfolge ist Absicht: erst die Ereignisse, dann die Tage. Ein selbst
    erfasstes Ereignis ist eine Aussage darüber, was dieser Tag war, und sein
    Zeitfenster ist enger; der Tag sammelt danach auf, was übrig bleibt.

    Steht hier und nicht im Job-Runner, weil es vorher zwei Schleifen mit zwei
    leicht verschiedenen Regeln gab — die eine reichte `seen` durch, die andere
    nicht. Zwei Antworten auf „wohin gehört dieses Foto?" sind eine zu viel.
    """
    return ([("event", e) for e in candidates(db, user_id)]
            + [("day", d) for d in day_candidates(db, user_id)])


def link_target(db: Session, user, kind: str, item, url: str, key: str,
                seen: set[str]) -> int:
    """Ein Ziel aus `targets` verknüpfen — Ereignis oder Tag."""
    if kind == "event":
        return link_event(db, user, item, url, key, seen=seen)
    return link_day(db, user, item, url, key, seen)


def link_batch(db: Session, user, limit: int = 25) -> tuple[int, int, int]:
    """Verknüpft einen Stapel Ziele (Ereignisse und Tage).

    Gibt (Ziele bearbeitet, Fotos verknüpft, noch offen) zurück.
    **Wichtig:** Ein Ziel gilt auch dann als bearbeitet, wenn Immich nichts
    liefert — sonst liefe der Batch-Lauf ewig über dieselben fotolosen Tage.
    Dafür merkt sich ein leerer Treffer nichts; erkannt wird er daran, dass
    der Aufrufer nach `limit` Zielen weiterrückt.
    """
    cfg = api.config_for(user)
    if cfg is None:
        raise api.ImmichError("Immich ist für dieses Konto nicht eingerichtet "
                              "(Verwaltung → Meine Daten → Immich)")
    url, key = cfg
    pending = targets(db, user.id)
    batch = pending[:limit]
    # Über den ganzen Stapel entduplizieren: jedes Foto genau einmal, beim
    # ersten passenden Ziel. Ohne diese Menge bekäme jedes Ziel dieselben Fotos
    # noch einmal — der Defekt, den der Job-Runner längst vermied und diese
    # Funktion nicht.
    seen = linked_asset_ids(db, user.id)
    linked = 0
    for kind, item in batch:
        try:
            n = link_target(db, user, kind, item, url, key, seen)
            if n:
                db.commit()
                linked += n
        except IntegrityError:
            db.rollback()      # paralleler Lauf war schneller — kein Schaden
        except api.ImmichError:
            db.rollback()
            raise              # Dienst weg: abbrechen statt hunderte Fehlversuche
    return len(batch), linked, max(0, len(pending) - len(batch))


def reset(db: Session, user_id: str) -> int:
    """Verwirft ALLE Immich-Verknüpfungen des Nutzers.

    Erlaubt, weil Verweise eine Ableitung sind (Anmerkung 57) — die Bilder
    liegen in Immich und bleiben dort. Hochgeladene Dateien (`provider=local`)
    fasst diese Funktion NICHT an; das wäre Datenverlust.
    """
    n = (db.query(MediaRef)
         .filter(MediaRef.user_id == user_id, MediaRef.provider == PROVIDER)
         .delete(synchronize_session=False))
    db.commit()
    log.info("Immich-Verknüpfungen verworfen: %d (user=%s)", n, user_id)
    return n
