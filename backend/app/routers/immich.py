"""P2.1 Stufe 2 — Endpunkte für „Immich als Ereignis-Quelle".

Zwei lesende Endpunkte (Jahre, Vorschau) und ein Lauf, der als **Job** läuft
(`immich_source`, jahresweise über `params`). Die Trennung ist Absicht und
folgt dem P2.5-Muster: **erst sehen, dann anlegen.** Ohne die Vorschau
schreibt eine zwanzig Jahre alte Bibliothek in einem Rutsch potenziell
hunderte Ereignisse in die Lebensdatenbank — seit Anmerkung 138 direkt
bestätigt, also ohne die Moderation als zweite Bremse danach.
"""
from __future__ import annotations

import logging
import time
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services import immich as api
from app.services import immich_source as source

router = APIRouter(prefix="/api/immich", tags=["Immich"])

log = logging.getLogger("lifedash.immich")

# Wie lange die VORSCHAU höchstens rechnen darf. Der Wert ist nicht aus der
# Bibliothek abgeleitet, sondern aus dem, was zwischen Browser und App steht:
# umgekehrte Vertreter warten üblicherweise 30 bis 60 Sekunden auf die erste
# Kopfzeile (nginx `proxy_read_timeout` 60 s, Cloudflare 100 s). Ein Budget
# darunter macht aus „gar keiner Antwort" eine Teilantwort — und die ist immer
# noch eine Entscheidungsgrundlage. Der Job kennt kein Budget.
PREVIEW_BUDGET_S = 25.0


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

    **Der Notnagel sagt jetzt, dass er einer ist** (Anmerkung 113). Vorher
    verschwand der Grund im `except` — und wer daraufhin nur die Jahre sah,
    die Life-Dash ohnehin schon kennt, hatte genau die Auswahl vor sich, die
    dieses Paket abschaffen sollte, ohne eine Chance zu merken warum. Der
    Rückfall ist richtig; das Schweigen darüber war der Fehler.
    """
    def _fallback(reason: str | None) -> dict:
        if reason:
            log.warning("Immich-Jahresliste nicht verfügbar: %s", reason)
        return {"years": [{"year": y, "photos": None}
                          for y in source.years_with_photos(db, user.id)],
                "current": date.today().year, "source": "own", "reason": reason}

    cfg = api.config_for(user)
    if cfg is None:
        return _fallback("Immich ist für dieses Konto nicht eingerichtet "
                         "(Verwaltung → Meine Daten → Immich).")
    url, key = cfg
    try:
        counts = api.photo_years(url, key, api.own_user_id(url, key))
    except api.ImmichError as exc:
        return _fallback(str(exc))
    if not counts:
        return _fallback("Immich meldet keine Fotos mit Koordinaten in seinem "
                         "Zeitstrahl.")
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
    """Was ein Lauf für dieses Jahr anlegen WÜRDE. Legt nichts an.

    Dieselbe Funktion, die der Lauf benutzt (`scan_year`) — zwei getrennte
    Wege wären zwei Regeln, und die widersprechen sich still (Anmerkung 106).

    **Der Lauf steht im Log, bevor er fertig ist** (Anmerkung 113). Eine
    Zugriffszeile schreibt der Server erst, wenn die Antwort steht — eine
    Vorschau, die zwei Minuten über eine große Bibliothek läuft, sieht im Log
    deshalb aus wie eine Anfrage, die es nie gab. Genau so wurde sie gemeldet:
    „geht nicht, kein Log, keine Rückmeldung".

    **Ein fremder Dienst, der ausfällt, ist KEIN 5xx dieser App** (Anmerkung
    113): Cloudflare ersetzt den Rumpf einer 502-Antwort durch seine eigene
    HTML-Seite, also **200 mit `error` im Rumpf**, genau wie `/api/immich/years`
    es mit `reason` hält.
    """
    url, key = _config_or_400(user)
    log.info("Immich-Vorschau für %s: Jahr %d — beginnt", user.id[:8], year)
    began = time.monotonic()
    report: dict = {}
    try:
        proposals = source.scan_year(db, user, year, url, key,
                                     budget_s=PREVIEW_BUDGET_S, report=report)
    except api.ImmichError as exc:
        log.warning("Immich-Vorschau %d abgebrochen nach %.1fs: %s",
                    year, time.monotonic() - began, exc)
        return {"year": year, "error": str(exc), "total": 0, "photos": 0,
                "seconds": round(time.monotonic() - began, 1), "proposals": []}
    log.info("Immich-Vorschau %d fertig in %.1fs: %d Tagescluster",
             year, time.monotonic() - began, len(proposals))
    return {
        "year": year,
        "total": len(proposals),
        "photos": sum(p.photos for p in proposals),
        "seconds": report.get("seconds"),
        # Die Liste selbst, damit die Vorschau die Ereignisse NENNT statt nur
        # zu zählen. „12 Tagescluster" ist eine Zahl; „12. Juli in Detmold, …"
        # ist eine Entscheidungsgrundlage.
        "proposals": [p.as_dict() for p in proposals],
    }
