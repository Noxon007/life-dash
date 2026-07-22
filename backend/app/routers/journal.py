"""F1 (zweite Hälfte): der KI-Vorschlag für den Tagebuch-Text eines Tages.

Genau ein Endpunkt, und er ist absichtlich ein GET: er liest, rechnet und gibt
Text zurück — geschrieben wird nichts. Der Vorschlag landet im Editor, der
Mensch entscheidet. Ein `POST /api/journal` gibt es nicht und soll es nicht
geben: das Tagebuch wird über den normalen Ereignis-Weg gespeichert (Kategorie
`journal`, Text in `note`), und zwei Schreibwege für dieselbe Sache widersprechen
sich früher oder später still (Anmerkung 106).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.ai.base import ProviderUnavailable
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import JournalSuggestion
from app.services import journal as journal_svc

router = APIRouter(prefix="/api/journal", tags=["Journal"])


@router.get("/suggest", response_model=JournalSuggestion)
def suggest_day(
    day: date = Query(..., description="Der Tag, YYYY-MM-DD"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JournalSuggestion:
    """Formuliert aus den bestätigten Ereignissen eines Tages einen Textvorschlag."""
    try:
        text, used, unconfirmed = journal_svc.suggest(db, user.id, day)
    except ProviderUnavailable as err:
        # 503 statt leerem Text: „das Modell antwortet nicht" ist eine Auskunft,
        # ein leerer Vorschlag wäre Stille (vgl. A40).
        raise HTTPException(503, f"KI-Provider nicht erreichbar: {err}") from err
    return JournalSuggestion(day=day, text=text, used_events=used,
                             skipped_unconfirmed=unconfirmed)
