"""P3.1 — Statistik-Widgets (deklarativ aus den Modul-YAMLs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services import gaps
from app.services.stats import compute_widgets
from app.services.stats_overview import compute_overview
from app.services.stats_toplists import compute_toplists

router = APIRouter(prefix="/api/stats", tags=["Statistik"])


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    """A37: Alle Zahlen des Statistik-Reiters — als Ableitung im Server.

    Ersetzt den Client-Reduce über die volle Ereignisliste. Ohne diesen
    Endpunkt würde das Zeitfenster die Kacheln still auf das Fenster
    beziehen, statt auf das Leben."""
    return compute_overview(db, user.id)


@router.get("/toplists")
def toplists(db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    """Anmerkung 156: die Ranglisten der dritten Statistik-Ansicht.

    Eigener Endpunkt statt weiterer Felder in `/overview`: der Überblick wird
    bei jedem Öffnen des Reiters geholt, diese Listen erst, wenn jemand sie
    ansieht — dieselbe Regel, mit der A37 die Karte von der Startseite getrennt
    hat. Eine Ansicht bezahlt, was sie zeigt.
    """
    return compute_toplists(db, user.id)


@router.get("/gaps")
def gaps_report(db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    """F21/Anmerkung 145: wo weiß ich gar nichts?

    Eigener Endpunkt aus demselben Grund wie `/toplists`: eine Ansicht bezahlt,
    was sie zeigt. Der Kalenderdurchlauf über ein ganzes Leben ist billig, aber
    er soll nicht bei jedem Öffnen des Statistik-Reiters anfallen.

    **Es wird nichts gespeichert.** Eine Lücke ist eine Ansicht, kein Zustand —
    stünde sie als Zeile in der Datenbank, müsste sie bei jedem Import, jeder
    Löschung und jeder Grundort-Änderung nachgeführt werden, und eine veraltete
    Lückenliste schickt jemanden auf die Suche nach Daten, die längst da sind.
    """
    return gaps.report(db, user.id)


@router.get("/widgets")
def widgets(db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> list[dict]:
    """Alle deklarierten Kennzahlen der getrackten Module — Zahl oder Zeitreihe.
    Reine Ableitung, respektiert die Tracking-Auswahl (A15)."""
    return compute_widgets(db, user.id)
