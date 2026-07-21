"""P2.1 — Fotos aus Immich an Ereignisse hängen (Schicht-4-Ableitung).

Getrennt vom reinen API-Client (`immich.py`), damit der Client ohne Datenbank
testbar bleibt und die Zuordnungsregeln an einer Stelle stehen.
"""
from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Event, MediaRef
from app.services import immich as api

log = logging.getLogger("lifedash.immich")

PROVIDER = "immich"
# Höchstens so viele Fotos je Ereignis verknüpfen. Ein Urlaubstag kann 300
# Bilder haben — die gehören in Immich, nicht als Kachelwand in den Zeitstrahl.
MAX_PER_EVENT = 12


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
    """
    from sqlalchemy.orm import selectinload

    # Kinder und Medien mitladen (selectinload), sonst löst der Filter unten
    # pro Ereignis zwei Lazy-Queries aus — bei zehntausenden Ereignissen wird
    # der Kandidaten-Aufbau sonst zur eigentlichen Bremse (N+1).
    rows = (db.query(Event)
            .options(selectinload(Event.children), selectinload(Event.media))
            .filter(Event.user_id == user_id, Event.date_start.isnot(None))
            .all())
    return [e for e in rows
            if api.window_for(e) is not None
            and not e.children
            and not any(m.provider == PROVIDER for m in e.media)]


def link_event(db: Session, user, event: Event, url: str, key: str) -> int:
    """Sucht Fotos für EIN Ereignis und verknüpft sie. Ohne Commit.

    Idempotent über `external_id` (die Immich-Asset-ID): ein zweiter Lauf
    erzeugt keine Dubletten, auch wenn dasselbe Foto zu zwei Ereignissen
    desselben Tages passt.
    """
    window = api.window_for(event)
    if window is None:
        return 0
    assets = api.search_assets(url, key, *window)
    known = {m.external_id for m in event.media}
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
        known.add(asset["id"])
        added += 1
    return added


def link_batch(db: Session, user, limit: int = 25) -> tuple[int, int, int]:
    """Verknüpft einen Stapel Ereignisse.

    Gibt (Ereignisse bearbeitet, Fotos verknüpft, noch offen) zurück.
    **Wichtig:** Ein Ereignis gilt auch dann als bearbeitet, wenn Immich nichts
    liefert — sonst liefe der Batch-Lauf ewig über dieselben fotolosen Tage.
    Dafür merkt sich ein leerer Treffer nichts; erkannt wird er daran, dass
    der Aufrufer nach `limit` Ereignissen weiterrückt.
    """
    cfg = api.config_for(user)
    if cfg is None:
        raise api.ImmichError("Immich ist für dieses Konto nicht eingerichtet "
                              "(Verwaltung → Meine Daten → Immich)")
    url, key = cfg
    pending = candidates(db, user.id)
    batch = pending[:limit]
    linked = 0
    for event in batch:
        try:
            n = link_event(db, user, event, url, key)
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
