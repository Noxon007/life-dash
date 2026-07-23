"""A45 — Fotopunkte: wo fotografiert wurde, als eigene Karten- und Zeitstrahl-Ebene.

Drei lesende Endpunkte und ein Bild-Proxy. Der Lauf, der die Punkte anlegt,
ist ein Job (`photo_points`, jahresweise) — wie bei P2.1, und aus demselben
Grund: er hängt an einem fremden Dienst und darf an keiner HTTP-Anfrage
kleben.

**Was diese Ebene NICHT ist.** Sie legt keine Ereignisse an. Ein Foto ist kein
Ereignis, sondern ein Beleg dafür, dass jemand irgendwo war; daraus Zeilen in
der Lebensdatenbank zu machen hieße, Tausende Container zu erzeugen, die jede
Aggregation wieder ausfiltern muss — genau das hat Anmerkung 87 für den Tag
schon einmal verworfen. Die Punkte sind eine **Ableitung**: sichtbar, wenn man
sie einschaltet, jederzeit verwerf- und neu berechenbar.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import PhotoPoint, User
from app.routers.media import _SAFE_HEADERS
from app.services import immich as immich_api
from app.services import photo_points as pp

router = APIRouter(prefix="/api/photos", tags=["Fotopunkte"])

log = logging.getLogger("lifedash.photos")

# Wie viele Vorschaubilder eine Gruppe im Zeitstrahl mitliefert. Dieselbe
# Überlegung wie bei der Fotoleiste (Anmerkung 110): ein Urlaubstag mit 300
# Bildern soll den Zeitstrahl nicht sprengen, und die Zahl daneben SAGT, wie
# viele es wirklich sind.
GROUP_THUMBS = 6

# Die Stufen der Verdichtung (A47). „point" heißt: gar nicht verdichten.
GROUP_LEVELS = ("country", "state", "city", "district", "point")


def _level_value(point: PhotoPoint, level: str) -> str | None:
    """Der Gruppenschlüssel eines Punktes auf dieser Stufe.

    **Kein Rückfall auf die gröbere Stufe.** Ein Foto ohne Stadt in eine
    Stadt-Gruppe zu stecken, die eigentlich das Land ist, wäre eine Zahl mit
    Anspruch — und sie stünde neben echten Städten, ohne sich zu unterscheiden.
    Was auf der gewählten Stufe keinen Namen hat, kommt in eine eigene,
    benannte Gruppe (`None` -> die Oberfläche sagt „ohne Angabe").
    """
    if level == "point":
        return None
    return getattr(point, level, None)


def _place_label(point: PhotoPoint, level: str) -> str | None:
    """Was auf der Karte oder im Zeitstrahl an der Gruppe steht."""
    if level == "point":
        return point.city or point.state or point.country
    return _level_value(point, level)


@router.get("/index")
def photo_index(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Was es überhaupt gibt — und welche Jahre noch nie durchsucht wurden.

    Der zweite Teil ist der wichtigere. Ohne ihn zeigt die Karte für 2004
    dasselbe wie für ein Jahr ohne Kamera: nichts, wortlos. „Keine Fotos" und
    „nie nachgesehen" sind zwei verschiedene Auskünfte, und dieses Projekt
    hat sie inzwischen an sechs Stellen verwechselt (F12 `weather_rev`,
    A39-Leerstring, A42 „kein Artikel", P2.1-Grabstein, Anmerkung 114).
    """
    from sqlalchemy import func

    total = db.query(func.count(PhotoPoint.id)).filter(
        PhotoPoint.user_id == user.id).scalar() or 0
    span = (db.query(func.min(PhotoPoint.taken_at), func.max(PhotoPoint.taken_at))
            .filter(PhotoPoint.user_id == user.id).first())
    return {
        "total": total,
        "first": span[0].isoformat() if span and span[0] else None,
        "last": span[1].isoformat() if span and span[1] else None,
        "years_scanned": sorted(pp.scanned_years(user)),
        "max_points": pp.MAX_POINTS,
    }


@router.get("/days")
def photo_days(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Kalendertage mit Fotos, samt Anzahl — `{"2004-07-12": 34, …}`.

    Die Karte gliedert nach Zeiträumen, und die baut sie bisher aus den
    EREIGNISSEN. Genau die Jahre, für die dieses Paket gemacht ist, haben aber
    Fotos und keine Besuche (vor dem Smartphone gibt es keine Timeline) — ohne
    diese Liste ließe sich 2004 gar nicht ansteuern, und der Nutzer sähe eine
    leere Karte statt seiner Bilder.

    Tage statt Fotos: bei zwanzig Jahren sind das einige tausend Zeilen à
    zwanzig Byte. Die Punkte selbst holt `/map` erst für den Zeitraum, den
    jemand wirklich ansieht (A37).
    """
    return {"days": {d.isoformat(): n
                     for d, n in sorted(pp.day_index(db, user.id).items())}}


@router.get("/map")
def photo_map(
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Die Punkte eines Zeitraums — schlank, nach dem Vorbild `/api/events/map`.

    Je Punkt gehen fünf Werte raus, mehr braucht ein Marker nicht. Bei 20.000
    Fotos ist der Unterschied zwischen „alles" und „das Nötige" der zwischen
    einer Karte und einem Ladebalken (A36/A37).

    **Die Deckelung wird GENANNT.** `total` ist die wahre Zahl, `shown` die
    gelieferte. Eine Liste, die stillschweigend bei 5.000 aufhört, sieht auf
    der Karte aus wie die ganze Wahrheit — genau der Defekt, den Anmerkung 110
    an der Ereignis-Karte gefunden hat (`all.slice(0, 300)`, chronologisch,
    ohne ein Wort darüber).
    """
    rows, total = pp.points_for(db, user.id, date_from, date_to)
    return {
        "total": total,
        "shown": len(rows),
        "points": [{"id": p.asset_id, "lat": p.lat, "lng": p.lng,
                    "at": p.taken_at.isoformat(),
                    "place": p.city or p.state or p.country}
                   for p in rows],
    }


@router.get("/groups")
def photo_groups(
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    level: Annotated[str, Query(description="A47: country|state|city|district|point")] = "city",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Fotopunkte, verdichtet zu (Tag, Ort) — für den Zeitstrahl.

    Verdichtet wird **hier**, nicht im Browser: der Zeitstrahl lädt Seiten
    (A37), und eine Gruppierung nach dem Blättern zerschneidet die Gruppe an
    der Seitengrenze — beide Hälften zeigten dann eine zu kleine Zahl (A39).

    Die Stufe kommt von außen, weil sie eine Frage ist und keine Eigenschaft:
    „welche Länder?" und „welche Straße?" sind beide legitim, und welche gerade
    gilt, weiß nur der, der hinsieht.
    """
    if level not in GROUP_LEVELS:
        raise HTTPException(400, f"Unbekannte Stufe: {level}")
    rows, total = pp.points_for(db, user.id, date_from, date_to)

    buckets: dict[tuple[date, str | None], list[PhotoPoint]] = defaultdict(list)
    for point in rows:
        buckets[(point.taken_at.date(), _level_value(point, level))].append(point)

    groups = []
    for (day, _key), items in sorted(buckets.items(), key=lambda kv: kv[0][0]):
        items.sort(key=lambda p: p.taken_at)
        # Gleichmäßig über die Gruppe greifen statt vorne abschneiden — sonst
        # zeigt ein Urlaubstag sechsmal den Morgen (Anmerkung 111).
        step = max(1, len(items) // GROUP_THUMBS)
        thumbs = items[::step][:GROUP_THUMBS]
        groups.append({
            "day": day.isoformat(),
            "place": _place_label(items[0], level),
            "count": len(items),
            "first": items[0].taken_at.isoformat(),
            "last": items[-1].taken_at.isoformat(),
            "lat": round(sum(p.lat for p in items) / len(items), 6),
            "lng": round(sum(p.lng for p in items) / len(items), 6),
            "assets": [p.asset_id for p in thumbs],
        })
    return {"level": level, "total": total, "shown": len(rows),
            "groups": groups}


@router.get("/{asset_id}/thumb")
def photo_thumb(asset_id: str, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> Response:
    """Vorschaubild eines Fotopunktes — durchgereicht aus Immich.

    **Erst prüfen, dann die Verbindung loslassen, dann erst ins Netz**
    (Anmerkung 110): Ein Proxy-Endpunkt ist kein Datenbank-Endpunkt. Hielte er
    seine Pool-Verbindung, während er 15 Sekunden auf Immich wartet, wäre der
    Pool nach fünfzehn parallelen Bildabrufen leer — und dann scheitert
    **jede** Anfrage, auch die des Zeitstrahls. Genau so wurde 0.38 gemeldet:
    „lädt endlos".

    Die Prüfung selbst ist der Zugriffsschutz: ohne sie ließe sich über diesen
    Endpunkt jedes Asset des hinterlegten Immich-Servers abrufen, auch fremde.
    """
    known = (db.query(PhotoPoint.id)
             .filter(PhotoPoint.user_id == user.id,
                     PhotoPoint.asset_id == asset_id).first())
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
def photo_reset(db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    """Verwirft alle Fotopunkte — Ableitung, jederzeit erlaubt (Anmerkung 57).

    Auch die Merkliste der durchsuchten Jahre geht mit. Bliebe sie stehen,
    behauptete die Oberfläche nach dem Zurücksetzen „2004: nachgesehen, keine
    Fotos" — über einer Tabelle, die gerade geleert wurde.
    """
    count = pp.reset(db, user.id)
    settings = dict(user.settings or {})
    settings.pop("photo_points", None)
    user.settings = settings
    db.commit()
    log.info("Fotopunkte verworfen: %d", count)
    return {"deleted": count}
