"""Demo-Daten: spielt beim ersten Start ein paar Beispiel-Fragmente durch die Pipeline."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Fragment, Source, User
from app.services.ingestion import ingest_fragment

DEMO_FRAGMENTS = [
    "12.07.2026 war in Detmold und habe einen Adler gesehen",
    "Sommer 2002 Urlaub in Frankreich",
    "September 2025 Städtetrip nach Lissabon, Portugal",
    "Gestern 10 km am Elbstrand in Hamburg gelaufen",
    "2019 einen Fuchs im Garten beobachtet",
    "15.05.2024 Konzert am Pariser Platz 1 in Berlin",
    "03.06.2025 in der Reeperbahn 1, Hamburg unterwegs gewesen",
]


def seed_demo(db: Session, user: User) -> None:
    """Legt Demo-Fragmente für den angegebenen Nutzer an, falls die DB leer ist."""
    if db.query(Fragment).count() > 0:
        return
    for text in DEMO_FRAGMENTS:
        fragment = Fragment(user_id=user.id, raw_text=text, source=Source.manual)
        db.add(fragment)
        db.flush()
        ingest_fragment(db, fragment)
    db.commit()
