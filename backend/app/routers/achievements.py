"""F6 — Achievements-Endpoint (reine Ableitung, siehe services/achievements.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import AchievementsRead
from app.services.achievements import compute

router = APIRouter(prefix="/api", tags=["Achievements"])


@router.get("/achievements", response_model=AchievementsRead)
def achievements(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AchievementsRead:
    """Alle Erfolge samt Stufe und Fortschritt zur nächsten."""
    return compute(db, user.id)
