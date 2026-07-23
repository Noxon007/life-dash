"""Anmerkung 119 — das Wetter EINES TAGES, für die Oberfläche.

Eigener Router und nicht in `events.py`, weil der Pfad die Sache benennt: was
hier herauskommt, gehört keinem Ereignis. `/api/events/…` hätte genau die
Verwechslung fortgeschrieben, aus der der Defekt entstanden ist — dass die
Auskunft über einen Tag am Wetter eines beliebigen Eintrags hing.

Die Regel selbst steht in `services/weather_day.py`; hier wird nur zugestellt.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services import weather_day

router = APIRouter(prefix="/api", tags=["Wetter"])

# Die Antwort ist von sich aus klein: sie trägt eine Zeile je Tag, an dem es
# Wetter GIBT, und der Zeitstrahl fragt immer nur die Spanne der gerade
# geladenen Seite ab — höchstens 300 Ereignisse, also höchstens 300 Tage.
# Die Grenze ist deshalb kein Größenschutz, sondern nur ein Riegel gegen
# offensichtlich unsinnige Eingaben; sie muss ein ganzes Leben umfassen.
#
# Der erste Anlauf stand bei 4000 Tagen (11 Jahre) — das hätte in einem dünn
# gefüllten Bestand jede Seite getroffen, die von 1994 bis heute reicht, und
# der Zeitstrahl hätte das Tageswetter dort stumm weggelassen. Eine Grenze,
# die aus dem falschen Grund gezogen ist, wird zur stillen Auslassung.
# Gedeckelt wird mit einem FEHLER, nicht mit einem Zuschnitt.
MAX_DAYS = 40000


@router.get("/days/weather", response_model=dict[str, dict])
def day_weather_range(
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, dict]:
    """Wetter je Kalendertag eines Zeitraums.

    `{"2026-07-23": {"values": {"temp_max_c": 24.1, …}, "regions": 1}}`

    `regions` ist die Zahl der berührten Wetterregionen (0,1°-Zellen). Steht
    dort mehr als 1, stammen die Werte aus verschiedenen Gegenden und die
    Oberfläche muss das sagen, statt einen davon als „das Wetter" auszugeben.

    Unbestätigte Ereignisse zählen mit: der Zeitstrahl zeigt sie auch, und ein
    Tageskopf, der eine andere Menge zusammenfasst als die Karten darunter,
    wäre wieder eine zweite Wahrheit.
    """
    if date_to < date_from:
        raise HTTPException(400, "„to“ liegt vor „from“.")
    if (date_to - date_from).days > MAX_DAYS:
        raise HTTPException(400, f"Zeitraum zu groß (höchstens {MAX_DAYS} Tage).")
    return weather_day.day_weather(db, user.id, start=date_from, end=date_to)
