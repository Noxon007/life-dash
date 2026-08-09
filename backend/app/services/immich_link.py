"""P2.1 — Fotos aus Immich an Ereignisse hängen (Schicht-4-Ableitung).

Getrennt vom reinen API-Client (`immich.py`), damit der Client ohne Datenbank
testbar bleibt und die Zuordnungsregeln an einer Stelle stehen.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Event, MediaRef, Source, User
from app.services import immich as api
from app.sqlutil import day_parts

log = logging.getLogger("lifedash.immich")

PROVIDER = "immich"
# Höchstens so viele Fotos je Ziel verknüpfen. Ein Urlaubstag kann 300
# Bilder haben — die gehören in Immich, nicht als Kachelwand in den Zeitstrahl.
MAX_PER_EVENT = 12
# Von einer MASCHINE erzeugte Einträge (Anmerkung 111). Sie bekommen ihre Fotos
# über den Tag, nicht direkt — der eine Satz, aus dem `candidates` und
# `detach_machine_links` beide folgen. Vorher stand `google_timeline` an beiden
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
    `link_month`. Das sind zwei Quellen:

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
#
# Anmerkung 205 — die Tagesliste kam aus der falschen Tabelle
#
# Bis hierher zählte `day_candidates` die Tage aus der EREIGNIS-Tabelle auf
# (`Event.source.in_(MACHINE_SOURCES)`), mit der Begründung: „Tage ohne jeden
# Eintrag sind nicht Teil der Lebensdatenbank." Dieser Satz war schon falsch,
# als er geschrieben wurde, und wurde es mit F20 endgültig:
#
#   * Ein **Wohnort-Tag** ist Lebensdatenbank — die vierte Sorte Aussage, eine
#     stehende Tatsache mit Gültigkeitszeitraum. Er hat nur keine Ereigniszeile,
#     und deshalb hat ihn diese Abfrage nie gesehen. Genau die Falle, die
#     CLAUDE.md unter „der Verräter ist die Überschrift" beschreibt: wer eine
#     Menge über TAGE aus der Ereignis-Tabelle bildet, liegt lautlos falsch.
#   * Ein Tag mit nur EINEM selbst erfassten Eintrag bekam ebenfalls keine
#     Leiste: das Ereignis holt seine Fotos ortsgefiltert (25 km), und ein Bild
#     von weiter weg fand an diesem Tag keinen Platz.
#
# Die Entscheidung des Users dazu ist die weiteste: **jeder Tag, an dem Immich
# Fotos hat, bekommt seine Leiste** — ohne Rückfrage an den eigenen Bestand.
# Damit verschwindet die Frage „welche Quelle stand an diesem Tag?" aus der
# Tageszeile, und mit ihr die Liste, an der sie hing.
#
# Was das für die KOSTEN heißt, ist der eigentliche Umbau. `link_day` fragte
# Immich **je Tag einzeln**; über 32 Jahre Wohnort wären das ~11.000 Anfragen
# je Lauf, und ein Tag ohne Fotos hinterließ keine Marke — er fragte in jedem
# folgenden Lauf erneut (die Endlos-Abruf-Falle, zehnte Auflage). Gefragt wird
# deshalb MONATSWEISE über `search_assets_paged`, und welche Monate überhaupt
# etwas hergeben, sagt `timeline_buckets` in EINEM Aufruf.
# --------------------------------------------------------------------------- #


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


def days_with_media(db: Session, user_id: str) -> set[tuple[int, int, int]]:
    """Tage, an denen schon eine Fotoleiste hängt — als (Jahr, Monat, Tag).

    Die Marke gegen Dubletten. Steht hier, weil sie zwei Leser hat:
    `link_month` (welche Tage sind noch offen?) und der Foto-Ereignis-Lauf
    (welche Tage darf ich noch füllen?). Zwei Fassungen von „dieser Tag ist
    versorgt" wären zwei Antworten, und die zweite hängte die Bilder ein
    zweites Mal an.

    **Gegen die Endlos-Abruf-Falle reicht sie nicht** — ein Tag ohne Fotos
    steht hier nie, egal wie oft nachgesehen wurde. Diese Marke ist die
    Fotozahl je Monat (`open_months`); die beiden gehören zusammen.
    """
    ym, mm, dm = day_parts(MediaRef.captured_at)
    rows = (db.query(ym, mm, dm)
            .filter(MediaRef.user_id == user_id,
                    MediaRef.provider == PROVIDER,
                    MediaRef.event_id.is_(None),
                    MediaRef.captured_at.isnot(None))
            .group_by(ym, mm, dm).all())
    return {(int(a), int(b), int(c)) for a, b, c in rows}


def add_day_media(db: Session, user, assets: list[dict], seen: set[str]) -> int:
    """Aus einer Menge Assets die Fotoleiste EINES Tages bauen. Ohne Commit.

    Die Assets kommen von außen und werden hier nicht geholt — genau deshalb
    gibt es diese Funktion (Anmerkung 196). Zwei Läufe brauchen dieselbe Regel
    aus zwei Richtungen: `link_day` sucht den Tag im Netz, der Foto-Ereignis-Lauf
    hat die Assets des ganzen Jahres längst in der Hand und soll dafür nicht
    dreitausend Tage einzeln nachfragen. Was beide teilen — höchstens zwölf,
    gleichmäßig über den Tag gestreut, jedes Foto nur einmal — steht damit an
    einer Stelle statt an zweien.
    """
    added = 0
    for asset in _spread_over_day(assets, seen):
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


# --------------------------------------------------------------------------- #
# Der Monat als Einheit des Laufs (Anmerkung 205)
# --------------------------------------------------------------------------- #
SETTINGS_KEY = "immich_days"


def month_window(month: str) -> tuple[datetime, datetime]:
    """„2024-05" -> (1. Mai 00:00:00, 31. Mai 23:59:59.999999)."""
    year, mon = int(month[:4]), int(month[5:7])
    start = datetime(year, mon, 1)
    nxt = datetime(year + (mon == 12), (mon % 12) + 1, 1)
    return start, nxt - timedelta(microseconds=1)


def scanned_months(user) -> dict[str, int]:
    """Was dieser Nutzer schon abgegrast hat: „JJJJ-MM" -> damalige Fotozahl."""
    block = (user.settings or {}).get(SETTINGS_KEY) or {}
    got = block.get("months")
    return {str(k): int(v) for k, v in got.items()} if isinstance(got, dict) else {}


def mark_month(user, month: str, count: int) -> None:
    """Merkt: dieser Monat ist durch, und er hatte dabei `count` Fotos.

    `user.settings` ist eine JSON-Spalte — neu ZUWEISEN, nicht an Ort und
    Stelle ändern, sonst bemerkt SQLAlchemy die Mutation nicht und schreibt
    nichts (dieselbe Falle wie bei `photo_points.mark_scanned`).
    """
    settings = dict(user.settings or {})
    block = dict(settings.get(SETTINGS_KEY) or {})
    block["months"] = dict(scanned_months(user)) | {str(month): int(count)}
    settings[SETTINGS_KEY] = block
    user.settings = settings


def open_months(user, buckets: dict[str, int]) -> list[str]:
    """Welche Monate dieser Lauf anfassen muss — jüngste zuerst.

    **Die Marke ist die Fotozahl, nicht ein Häkchen**, und das ist der ganze
    Trick gegen die Endlos-Abruf-Falle in beide Richtungen:

    * Ein Monat, der beim letzten Lauf 312 Fotos hatte und immer noch 312 hat,
      wird übersprungen — auch dann, wenn er gar keine Leiste ergeben hat.
      Ein Häkchen könnte das nicht: „nachgesehen, nichts bekommen" und „nie
      nachgesehen" wären dieselbe Auskunft, und der Nachtplan liefe jede Nacht
      erneut über die ganze Bibliothek.
    * Lädt jemand später Bilder von 2004 hoch, ändert sich die Zahl — und der
      Monat ist von selbst wieder offen. Eine Marke, die von der Wirklichkeit
      widerlegt werden kann, braucht keinen Knopf zum Zurücksetzen.

    Jüngste zuerst, weil ein gestoppter Lauf dann das gefüllt hat, wohin am
    ehesten geschaut wird — und weil die Reihenfolge sonst gar keine wäre.
    """
    done = scanned_months(user)
    return sorted((m for m, n in buckets.items() if done.get(m) != n), reverse=True)


def link_month(db: Session, user, month: str, url: str, key: str,
               seen: set[str], my_id: str | None, *,
               taken: set[tuple[int, int, int]], heartbeat=None) -> int:
    """Die Fotos EINES Monats an ihre Kalendertage hängen. Ohne Commit.

    Kein Orts-Abgleich, anders als beim Ereignis: der Tag ist ein Behälter der
    ZEITachse (Anmerkung 87), und ein Ortsfilter auf einen Behälter, der
    ausdrücklich nicht vom Ort handelt, wäre in sich widersprüchlich. Wer
    vormittags in Düsseldorf ist und abends in München fotografiert, hat ein
    Foto von diesem Tag — und sonst hätte es gar keinen Platz.

    `taken` sind die Tage, die schon eine Leiste tragen; die Menge wird
    fortgeschrieben, damit der Aufrufer sie nicht je Monat neu abfragt.

    **Fremde Bilder bleiben draußen** (`is_own`), und archivierte auch
    (`is_in_timeline`) — beides dieselbe Strenge wie beim Foto-Ereignis-Lauf.
    Ohne bekannte eigene Kennung wird allerdings NICHT geschwiegen, sondern
    ungefiltert verknüpft: eine Leiste ist eine verwerfbare Ableitung
    (Anmerkung 57), und dafür ist „lieber ein fremdes Bild zu viel" der
    billigere Fehler als „gar keine Fotos, ohne zu sagen warum". Der Aufrufer
    nennt es im Ergebnis.
    """
    start, end = month_window(month)
    assets = api.search_assets_paged(url, key, start, end, heartbeat=heartbeat)
    by_day: dict[tuple[int, int, int], list[dict]] = {}
    for asset in assets:
        if my_id is not None and not api.is_own(asset, my_id):
            continue
        if not api.is_in_timeline(asset):
            continue
        when = api.asset_time(asset)
        if when is None:          # ohne Zeit kein Tag — der Behälter ist das Datum
            continue
        day = (when.year, when.month, when.day)
        if day in taken:
            continue
        by_day.setdefault(day, []).append(asset)
    added = 0
    for day in sorted(by_day):
        n = add_day_media(db, user, by_day[day], seen)
        if n:
            taken.add(day)
            added += n
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

    Nur noch Ereignisse. Die TAGE kommen seit Anmerkung 205 nicht mehr aus dem
    eigenen Bestand, sondern aus Immichs Zeitachse (`open_months` →
    `link_month`); eine Tagesliste hier wäre die zweite Antwort auf dieselbe
    Frage, und zwei Antworten auf „wohin gehört dieses Foto?" sind eine zu viel.

    Die Reihenfolge bleibt trotzdem eine Aussage, sie steht nur jetzt im
    Job-Runner: **erst die Ereignisse, dann die Monate.** Ein selbst erfasstes
    Ereignis ist eine Aussage darüber, was dieser Tag war, und sein Zeitfenster
    ist enger; der Tag sammelt danach auf, was übrig bleibt.
    """
    return [("event", e) for e in candidates(db, user_id)]


def link_target(db: Session, user, kind: str, item, url: str, key: str,
                seen: set[str]) -> int:
    """Ein Ziel aus `targets` verknüpfen."""
    if kind != "event":
        raise ValueError(f"unbekannte Zielart: {kind}")
    return link_event(db, user, item, url, key, seen=seen)


def link_batch(db: Session, user, limit: int = 25) -> tuple[int, int, int]:
    """Verknüpft einen Stapel Ereignisse.

    Gibt (Ziele bearbeitet, Fotos verknüpft, noch offen) zurück.
    **Wichtig:** Ein Ziel gilt auch dann als bearbeitet, wenn Immich nichts
    liefert — sonst liefe der Batch-Lauf ewig über dieselben fotolosen
    Ereignisse. Dafür merkt sich ein leerer Treffer nichts; erkannt wird er
    daran, dass der Aufrufer nach `limit` Zielen weiterrückt.

    Die Tagesleisten macht diese Funktion seit Anmerkung 205 nicht mehr mit:
    sie hängen an einem Monatsdurchlauf über Immich, und der ist kein Stapel
    von `limit` Stück, sondern ein Lauf mit eigener Marke.
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
    """Verwirft ALLE Immich-Verknüpfungen des Nutzers — **und die Monatsmarke.**

    Erlaubt, weil Verweise eine Ableitung sind (Anmerkung 57) — die Bilder
    liegen in Immich und bleiben dort. Hochgeladene Dateien (`provider=local`)
    fasst diese Funktion NICHT an; das wäre Datenverlust.

    Die Marke geht mit, und das ist keine Kür (Anmerkung 205): `open_months`
    überspringt jeden Monat, dessen Fotozahl sich seit dem letzten Lauf nicht
    geändert hat. Bliebe sie stehen, hätte dieser Knopf die Leisten gelöscht
    und den Lauf, der sie wiederherstellt, gleich mit stillgelegt — er meldete
    „alles aktuell" über einem leeren Bestand. Dieselbe Regel wie beim
    Zurücksetzen der Foto-Ereignisse (`routers/photos.py`).
    """
    n = (db.query(MediaRef)
         .filter(MediaRef.user_id == user_id, MediaRef.provider == PROVIDER)
         .delete(synchronize_session=False))
    user = db.get(User, user_id)
    if user is not None:
        settings = dict(user.settings or {})
        settings.pop(SETTINGS_KEY, None)
        user.settings = settings
    db.commit()
    log.info("Immich-Verknüpfungen verworfen: %d (user=%s)", n, user_id)
    return n
