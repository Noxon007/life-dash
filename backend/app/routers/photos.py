"""Anmerkung 139 — was von der Foto-Ebene übrig bleibt: der Bild-Proxy.

A45 hatte hier fünf Endpunkte: `/index`, `/days`, `/map`, `/groups` und
`/reset`. Vier davon beantworteten Fragen, die eine EIGENE Tabelle nötig
machten (`PhotoPoint`) — „wie viele Punkte gibt es?", „an welchen Tagen?", „wo
liegen die dieses Zeitraums?", „wie sehen sie verdichtet aus?".

Seit Anmerkung 139 ist ein verortetes Foto ein Ereignis. Damit beantwortet
`/api/events/index`, `/api/events/map` und die A39-Verdichtung dieselben vier
Fragen bereits — für ALLE Ereignisse, nicht nur für Fotos, und mit einer
einzigen Regel statt zweier. Die vier Endpunkte sind deshalb nicht umgezogen,
sondern **weggefallen**; das ist der Unterschied zwischen Auflösen und
Verschieben.

Übrig bleibt genau das, was Immich exklusiv hat und Life-Dash nicht speichert:
das Bild selbst.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, User
from app.routers.media import _SAFE_HEADERS
from app.services import immich as immich_api
from app.services import photo_points as pp

router = APIRouter(prefix="/api/photos", tags=["Fotos"])

log = logging.getLogger("lifedash.photos")


@router.get("/{asset_id}/thumb")
def photo_thumb(asset_id: str, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> Response:
    """Vorschaubild eines Foto-Ereignisses — durchgereicht aus Immich.

    **Erst prüfen, dann die Verbindung loslassen, dann erst ins Netz**
    (Anmerkung 110): Ein Proxy-Endpunkt ist kein Datenbank-Endpunkt. Hielte er
    seine Pool-Verbindung, während er 15 Sekunden auf Immich wartet, wäre der
    Pool nach fünfzehn parallelen Bildabrufen leer — und dann scheitert **jede**
    Anfrage, auch die des Zeitstrahls. Genau so wurde 0.38 gemeldet: „lädt
    endlos".

    Die Prüfung selbst ist der Zugriffsschutz: ohne sie ließe sich über diesen
    Endpunkt jedes Asset des hinterlegten Immich-Servers abrufen, auch fremde.
    Gefragt wird jetzt der PLATZ des Ereignisses (`immich:photo:<asset>`) statt
    einer eigenen Tabelle — dieselbe Zusage, eine Quelle weniger.
    """
    known = (db.query(Event.id)
             .filter(Event.user_id == user.id,
                     Event.external_id == pp.slot_photo(asset_id)).first())
    cfg = immich_api.config_for(user)
    db.close()          # Verbindung zurück in den Pool, VOR dem Netzaufruf
    if not known:
        raise HTTPException(404, "Unbekanntes Foto")
    if cfg is None:
        raise HTTPException(404, "Immich nicht eingerichtet")
    try:
        data = immich_api.thumbnail(*cfg, asset_id)
    except immich_api.ImmichError as exc:
        raise HTTPException(502, str(exc)) from exc
    return Response(content=data, media_type="image/jpeg", headers=_SAFE_HEADERS)


@router.post("/reset")
def photo_reset(
    limit: Annotated[int, Query(ge=0, le=5000,
                                description="0 = alles auf einmal")] = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Verwirft alle Foto-Ereignisse — und die Merkliste der Jahre dazu.

    **Das fasst jetzt Bestätigtes an**, anders als bei A45, wo eine Ableitung
    weggeworfen wurde. Es bleibt trotzdem richtig, dass es den Knopf gibt: was
    dieser Lauf angelegt hat, hat er nach einer nachvollziehbaren Regel
    angelegt, und wer sie insgesamt nicht will, braucht einen Weg zurück, der
    nicht „zwanzigtausend Zeilen von Hand" heißt. Gelöscht wird ausschließlich,
    was den Platz `immich:photo:` trägt.

    Die Merkliste geht mit. Bliebe sie stehen, behauptete die Oberfläche nach
    dem Zurücksetzen „2004: nachgesehen, keine Fotos" — über einem Bestand, der
    gerade geleert wurde.

    **Mit `limit` ein Stapel statt allem** (Anmerkung 215). Der Knopf löschte
    zehntausende bestätigte Zeilen in EINER Anfrage: der Browser konnte
    dazwischen nichts sagen, also stand die Seite ohne Auskunft — der
    wiederkehrende Defekt ist die Stille. `remaining` ist die Zahl, an der der
    Aufrufer seinen Balken misst; sie wird NACH dem Löschen frisch gezählt, statt
    aus der eigenen Buchführung fortgeschrieben zu werden (ein zweiter Tab oder
    ein laufender Immich-Lauf ändern denselben Bestand).
    """
    count = pp.reset(db, user.id, limit=limit or None)
    settings = dict(user.settings or {})
    settings.pop("photo_points", None)
    user.settings = settings
    db.commit()
    remaining = pp.count_photo_events(db, user.id)
    log.info("Foto-Ereignisse verworfen: %d (noch %d)", count, remaining)
    return {"deleted": count, "remaining": remaining}
