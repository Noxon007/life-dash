"""P2.1 Stufe 2 — Endpunkte für „Immich als Ereignis-Quelle".

Zwei lesende Endpunkte (Jahre, Vorschau) und ein Lauf, der als **Job** läuft
(`immich_source`, jahresweise über `params`). Die Trennung ist Absicht und
folgt dem P2.5-Muster: **erst sehen, dann anlegen.** Ohne die Vorschau füllt
eine zwanzig Jahre alte Bibliothek eine Warteschlange, die für Dutzende gebaut
ist — und niemand hätte vorher gewusst, dass es passiert.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services import immich as api
from app.services import immich_source as source

router = APIRouter(prefix="/api/immich", tags=["Immich"])


def _config_or_400(user: User) -> tuple[str, str]:
    cfg = api.config_for(user)
    if cfg is None:
        raise HTTPException(400, "Immich ist für dieses Konto nicht eingerichtet "
                                 "(Verwaltung → Meine Daten → Immich).")
    return cfg


@router.get("/years")
def source_years(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Jahre zur Auswahl — mit der Anzahl Fotos, die sie hergäben.

    Gefragt wird **Immich**, nicht der eigene Bestand: Anmerkung 107 nennt
    genau die Jahre **ohne** eigene Daten als die wertvollsten (die Zeit vor
    dem Smartphone, für die es keine Timeline-Besuche gibt). Eine Liste aus
    den eigenen Ereignissen böte die nie an.

    Billig ist das trotzdem — `/timeline/buckets` zählt Monate, statt Assets
    zu liefern. Kennt der Server den Endpunkt nicht (ältere Immich-Version),
    bleiben die eigenen Jahre als Notnagel: lieber eine magere Auswahl als
    ein leeres Feld.
    """
    fallback = {"years": [{"year": y, "photos": None}
                          for y in source.years_with_photos(db, user.id)],
                "current": date.today().year, "source": "own"}
    cfg = api.config_for(user)
    if cfg is None:
        return fallback
    url, key = cfg
    try:
        counts = api.photo_years(url, key, api.own_user_id(url, key))
    except api.ImmichError:
        return fallback
    if not counts:
        return fallback
    return {
        "years": [{"year": y, "photos": counts[y]} for y in sorted(counts, reverse=True)],
        "current": date.today().year,
        "source": "immich",
    }


@router.post("/preview")
def source_preview(
    year: int = Query(..., ge=1900, le=2200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Was ein Lauf für dieses Jahr vorschlagen WÜRDE. Legt nichts an.

    Dieselbe Funktion, die der Lauf benutzt (`scan_year`) — zwei getrennte
    Wege wären zwei Regeln, und die widersprechen sich still (Anmerkung 106).
    """
    url, key = _config_or_400(user)
    try:
        proposals = source.scan_year(db, user, year, url, key)
    except api.ImmichError as exc:
        raise HTTPException(502, str(exc)) from exc
    days = sum(1 for p in proposals if p.kind == "day")
    return {
        "year": year,
        "total": len(proposals),
        "days": days,
        "albums": len(proposals) - days,
        "photos": sum(p.photos for p in proposals),
        "shared": sum(1 for p in proposals if p.shared),
        # Die Liste selbst, damit die Vorschau die Vorschläge NENNT statt nur
        # zu zählen. „38 Vorschläge" ist eine Zahl; „Dänemark 2024, 12. Juli
        # in Detmold, …" ist eine Entscheidungsgrundlage.
        "proposals": [p.as_dict() for p in proposals],
    }
