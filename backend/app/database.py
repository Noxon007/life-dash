"""Datenbank-Engine und Session-Verwaltung."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

# Jede Anfrage braucht eine Verbindung, und sei es nur, um den angemeldeten
# Nutzer zu laden (`get_current_user`). Die Vorgabe von SQLAlchemy — fünf
# Verbindungen plus zehn Überlauf — reicht dafür genau so lange, wie keine
# Anfrage lange dauert. Beobachtet: schnelles Scrollen füllt die Warteschlange
# mit Bildanfragen, und dann scheitert JEDE andere Anfrage mit
# `QueuePool limit ... reached`; der Zeitstrahl sah aus, als lade er endlos.
#
# Die eigentliche Reparatur sitzt am Bild-Endpunkt (er gibt die Verbindung vor
# dem Netzaufruf zurück, siehe `routers/media.py`). Das hier ist die zweite
# Sicherung: ein größerer Pool und vor allem eine **kurze** Wartezeit. Dreißig
# Sekunden zu warten und dann zu scheitern ist das schlechteste beider Welten —
# der Nutzer sieht eine halbe Minute nichts und danach einen Fehler. Fünf
# Sekunden sagen dasselbe früher.
_pool_args: dict = {}
if not settings.database_url.startswith("sqlite:///:memory:"):
    _pool_args = {
        "pool_size": 20,
        "max_overflow": 30,
        "pool_timeout": 5,
        "pool_recycle": 1800,   # gegen Verbindungen, die ein Proxy still kappt
        "pool_pre_ping": True,
    }

engine = create_engine(settings.database_url, connect_args=connect_args, **_pool_args)

# Selbstkontrolle zum größeren Pool: Mehr gleichzeitige Verbindungen sind bei
# SQLite nicht umsonst zu haben — ohne WAL sperrt ein Schreiber alle Leser aus,
# und aus „Pool erschöpft" würde „database is locked". WAL lässt beliebig viele
# Leser neben EINEM Schreiber zu, `busy_timeout` lässt einen kurz wartenden
# Schreiber warten, statt sofort zu scheitern. Für PostgreSQL gilt nichts
# davon; die Weiche steht am Präfix.
if settings.database_url.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA synchronous=NORMAL")
        finally:
            cur.close()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI-Dependency: liefert eine DB-Session pro Request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
