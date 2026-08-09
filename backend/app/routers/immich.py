"""Immich als Ereignis-Quelle — was übrig bleibt, wenn der Lauf einer ist.

**Anmerkung 206: die Vorschau und die Jahresauswahl sind weg.** Bis 0.39 lagen
hier zwei lesende Endpunkte (`/years`, `/preview`) vor einem jahresweisen Job.
Die Trennung folgte dem P2.5-Muster „erst sehen, dann anlegen", und sie war
richtig gedacht: dieser Lauf schreibt bestätigte Lebensdatenbank, und die
Moderation gibt es für diese Quelle seit Anmerkung 138 nicht.

Gekippt hat sie der Nutzer, mit einem Grund, der stärker ist als die Regel:
*„im doing schaue ich mir keine 8.000 Vorschläge an, und das monatsweise
Anschauen mache ich auch nicht."* Eine Bremse, die niemand betätigt, bremst
nichts — sie kostet nur den Weg zum Ergebnis. Was an ihre Stelle tritt, ist
nicht nichts: jede angelegte Zeile trägt den Platz `immich:photo:<asset>`, ist
also maschinell wieder auffindbar, und `/api/photos/reset` nimmt sie samt
Grabsteinen zurück. Rückgängig statt vorher-ansehen.

Übrig bleibt der Aufräum-Lauf für die Tagescluster aus Anmerkung 138. Er fasst
BESTÄTIGTES an, und daraus folgen alle seine Grenzen (nur auf Knopfdruck, nie
im Nachtplan, nur `immich:day:`, Vorschau nennt die Zeilen) — dieselbe Strenge
wie beim A46-Besuchsschnitt. **Dass ausgerechnet er seine Vorschau behält, ist
kein Widerspruch:** er LÖSCHT, und Löschen hat keinen Rückweg.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services import photo_points as source

router = APIRouter(prefix="/api/immich", tags=["Immich"])

log = logging.getLogger("lifedash.immich")


# --------------------------------------------------------------------------- #
# Aufräumen: die Tagescluster aus Anmerkung 138
# --------------------------------------------------------------------------- #
@router.get("/day-clusters")
def day_clusters(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Was der Aufräum-Lauf löschen WÜRDE. Löscht nichts.

    Anmerkung 138 hat für einen Tag mit Fotos EIN Ereignis angelegt („34 Fotos
    in Detmold"). Anmerkung 139 ersetzt genau diesen Mechanismus durch ein
    Ereignis je Foto. Beides nebeneinander stehen zu lassen hieße, denselben
    Tag zweimal zu behaupten — einmal als Sammelzeile, einmal als 34 Punkte.

    Die Vorschau NENNT die Zeilen (A46/F7-Zusage), statt nur zu zählen: ein
    Knopf, der „214 bestätigte Einträge löschen" sagt und nicht welche, ist
    keine Entscheidungsgrundlage.
    """
    total = source.count_day_clusters(db, user.id)
    return {"total": total,
            "sample": source.day_cluster_sample(db, user.id) if total else []}


@router.post("/day-clusters/remove")
def remove_day_clusters(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Räumt die Tagescluster aus Anmerkung 138 weg — **nur auf Knopfdruck**.

    Kein Job, kein Nachtplan, kein Automatismus. Das hier fasst Bestätigtes an,
    und daraus folgt jede Grenze: es passiert genau dann, wenn jemand nach
    einer Vorschau darauf drückt. Dieselbe Strenge wie beim A46-Besuchsschnitt.

    Idempotent: ein zweiter Klick findet nichts mehr und sagt das auch.
    """
    removed = source.remove_day_clusters(db, user.id)
    db.commit()
    log.info("Tagescluster (Anm. 138) entfernt für %s: %d", user.id[:8], removed)
    return {"removed": removed}
