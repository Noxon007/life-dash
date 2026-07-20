"""P3.1 — Statistik-Widgets (deklarativ aus den Modul-YAMLs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.stats import compute_widgets

router = APIRouter(prefix="/api/stats", tags=["Statistik"])


@router.get("/widgets")
def widgets(db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> list[dict]:
    """Alle deklarierten Kennzahlen der getrackten Module — Zahl oder Zeitreihe.
    Reine Ableitung, respektiert die Tracking-Auswahl (A15)."""
    return compute_widgets(db, user.id)
