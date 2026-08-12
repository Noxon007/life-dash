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
def is_memory_url(url: str) -> bool:
    """Läuft diese Datenbank im Arbeitsspeicher?

    **Anmerkung 223: es gibt ZWEI Schreibweisen**, und geprüft wurde nur eine.
    `sqlite://` (ohne Pfad) ist die gebräuchlichere von beiden — die Testsuite
    benutzt genau sie — und fiel hier durch: sie bekam die Pool-Argumente,
    landete damit auf `SingletonThreadPool`, und `create_engine` warf einen
    `TypeError` beim IMPORT des Moduls. Kein Startfehler mit Meldung, sondern
    ein Absturz, bevor irgendetwas läuft.
    """
    return url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url


_pool_args: dict = {}
if not is_memory_url(settings.database_url):
    _pool_args = {
        "pool_size": 20,
        "max_overflow": 30,
        "pool_timeout": 5,
        "pool_recycle": 1800,   # gegen Verbindungen, die ein Proxy still kappt
        "pool_pre_ping": True,
    }

engine = create_engine(settings.database_url, connect_args=connect_args, **_pool_args)


# --------------------------------------------------------------------------- #
#  Wie eine SQLite-Verbindung dieser Anwendung eingestellt ist — EINE Stelle
# --------------------------------------------------------------------------- #
# Selbstkontrolle zum größeren Pool: Mehr gleichzeitige Verbindungen sind bei
# SQLite nicht umsonst zu haben — ohne WAL sperrt ein Schreiber alle Leser aus,
# und aus „Pool erschöpft" würde „database is locked". WAL lässt beliebig viele
# Leser neben EINEM Schreiber zu, `busy_timeout` lässt einen kurz wartenden
# Schreiber warten, statt sofort zu scheitern. Für PostgreSQL gilt nichts
# davon; die Weiche steht am Präfix.
#
# **Anmerkung 223 — und der Grund, warum das eine Funktion ist.** Hier stand ein
# `@event.listens_for(engine, …)` direkt an DIESER Engine. Die Testsuite baut
# sich aber ihre eigene (`conftest.db`), und die bekam davon nichts mit. Als ich
# `PRAGMA foreign_keys=ON` zuerst nur hier eintrug, liefen 902 Tests grün und
# bewiesen nichts: die Erzwingung galt im Betrieb und nicht im Lauf, der sie
# prüfen sollte. Genau die Klasse „Prüfungen, die nichts prüfen".
SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA synchronous=NORMAL",
    # **Fremdschlüssel werden erzwungen.** SQLite tut das von sich aus NICHT —
    # die Angaben stehen im Schema und gelten nicht. Das ist der Grund für die
    # eigene Falle in CLAUDE.md: „eine vergessene Kindtabelle ist in JEDEM Test
    # grün", sie fällt erst auf PostgreSQL um, und dann NACHDEM das Log schon
    # einen Erfolg gemeldet hat.
    #
    # Die Zusagen, die daran hängen, sind inzwischen alle gegen `Base.metadata`
    # geprüft (`wipe.WIPE_ORDER`, `admin.ON_DELETE`, `data._user_scoped_refs`)
    # und laufen auf PostgreSQL grün. Die Erzwingung holt diese ganze
    # Fehlerklasse damit aus dem 95-Sekunden-Lauf in den 50-Sekunden-Lauf, den
    # ohnehin jeder fährt.
    "PRAGMA foreign_keys=ON",
)


def attach_sqlite_pragmas(target) -> None:
    """Hängt die Einstellungen an JEDE neue Verbindung dieser Engine.

    Pro VERBINDUNG und nicht pro Datenbank: `foreign_keys` ist keine
    Eigenschaft der Datei, sondern der Sitzung. Wer eine Engine baut, ruft das
    hier — sonst hat er eine Datenbank mit anderen Regeln als die Anwendung.
    """
    if target.dialect.name != "sqlite":
        return
    from sqlalchemy import event

    @event.listens_for(target, "connect")
    def _set(dbapi_connection, _record) -> None:  # pragma: no cover
        cur = dbapi_connection.cursor()
        try:
            for pragma in SQLITE_PRAGMAS:
                cur.execute(pragma)
        finally:
            cur.close()


attach_sqlite_pragmas(engine)
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
