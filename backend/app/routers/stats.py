"""P3.1 — Statistik-Widgets (deklarativ aus den Modul-YAMLs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.stats import compute_widgets
from app.services.stats_overview import compute_overview

router = APIRouter(prefix="/api/stats", tags=["Statistik"])


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    """A37: Alle Zahlen des Statistik-Reiters — als Ableitung im Server.

    Ersetzt den Client-Reduce über die volle Ereignisliste. Ohne diesen
    Endpunkt würde das Zeitfenster die Kacheln still auf das Fenster
    beziehen, statt auf das Leben."""
    return compute_overview(db, user.id)


@router.get("/widgets")
def widgets(db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> list[dict]:
    """Alle deklarierten Kennzahlen der getrackten Module — Zahl oder Zeitreihe.
    Reine Ableitung, respektiert die Tracking-Auswahl (A15)."""
    return compute_widgets(db, user.id)
