"""SQLAlchemy-Modelle — die Drei-Stufen-Architektur.

Stufe 1: Fragment (Roh-Input, unveränderlich)
Stufe 2: Event, Entity, EventEntityLink, Location (strukturiert, moderiert)
Stufe 3: MediaRef, Metric (berechnete Anreicherungen) — hier als Tabellen vorbereitet
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class FragmentStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    needs_review = "needs_review"
    discarded = "discarded"


class DatePrecision(str, enum.Enum):
    exact = "exact"
    day = "day"
    month = "month"
    season = "season"
    year = "year"
    decade = "decade"


class ConfirmState(str, enum.Enum):
    unconfirmed = "unconfirmed"
    confirmed = "confirmed"


class Source(str, enum.Enum):
    manual = "manual"
    ai = "ai"
    immich = "immich"
    google_timeline = "google_timeline"
    fitness = "fitness"
    health_connect = "health_connect"
    psn = "psn"
    weather = "weather"
    api = "api"


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


# --------------------------------------------------------------------------- #
# Identität — Multi-User via OIDC (Pocket ID)
# --------------------------------------------------------------------------- #
class User(Base):
    """Ein angemeldeter Nutzer. Alle Stufe-1/2/3-Daten sind nutzergebunden."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    oidc_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user)
    # Pro-Nutzer-Einstellungen (später: Immich-API-Key, PSN-Token, ...)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# --------------------------------------------------------------------------- #
# Stufe 1 — Roh-Input
# --------------------------------------------------------------------------- #
class Fragment(Base):
    """Unveränderlicher Roh-Input. Die Quelle der Wahrheit."""

    __tablename__ = "fragments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    audio_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[Source] = mapped_column(Enum(Source), default=Source.manual)
    status: Mapped[FragmentStatus] = mapped_column(
        Enum(FragmentStatus), default=FragmentStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    events: Mapped[list["Event"]] = relationship(back_populates="origin_fragment")


# --------------------------------------------------------------------------- #
# Stufe 2 — Strukturierte, moderierte Daten
# --------------------------------------------------------------------------- #
class Location(Base):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # city|country|poi|home
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    events: Mapped[list["Event"]] = relationship(back_populates="location")


class Event(Base):
    """Zentrale Entität (Stufe 2). Etwas, das zu einer Zeit an einem Ort passiert ist."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    date_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_precision: Mapped[DatePrecision] = mapped_column(
        Enum(DatePrecision), default=DatePrecision.day
    )

    category: Mapped[str] = mapped_column(String(64), default="event")  # trackable key
    # Persönliche Notiz/Kommentar des Nutzers — nie von der KI angefasst
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    confirmed: Mapped[ConfirmState] = mapped_column(
        Enum(ConfirmState), default=ConfirmState.unconfirmed
    )
    # Welche Felder wurden manuell bestätigt/korrigiert -> vor Re-Processing geschützt
    field_overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[Source] = mapped_column(Enum(Source), default=Source.ai)

    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    origin_fragment_id: Mapped[str | None] = mapped_column(
        ForeignKey("fragments.id"), nullable=True
    )
    # Vektor für semantische Suche (JSON-Liste; pgvector erst mit Postgres).
    # none_as_null: Python-None als SQL NULL speichern (nicht als JSON 'null'),
    # damit "fehlt noch"-Filter (IS NULL) funktionieren.
    embedding: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    location: Mapped[Location | None] = relationship(back_populates="events")
    origin_fragment: Mapped[Fragment | None] = relationship(back_populates="events")
    entity_links: Mapped[list["EventEntityLink"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    media: Mapped[list["MediaRef"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["Metric"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Entity(Base):
    """Kompendium-Objekt (Stufe 2): Tier, Film, Land, Spiel, Ort, Buch ..."""

    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(64))  # animal|country|movie|...
    name: Mapped[str] = mapped_column(String(255))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)  # modul-spezifisch
    confirmed: Mapped[ConfirmState] = mapped_column(
        Enum(ConfirmState), default=ConfirmState.unconfirmed
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    event_links: Mapped[list["EventEntityLink"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )


class EventEntityLink(Base):
    """n:m-Verknüpfung zwischen Event und Entity."""

    __tablename__ = "event_entity_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    role: Mapped[str] = mapped_column(String(32), default="subject")  # subject|location|mentioned

    event: Mapped[Event] = relationship(back_populates="entity_links")
    entity: Mapped[Entity] = relationship(back_populates="event_links")


# --------------------------------------------------------------------------- #
# Stufe 3 — Anreicherungen (Enrichment)
# --------------------------------------------------------------------------- #
class MediaRef(Base):
    """Verweis auf externe Medien (z. B. Immich). Keine Kopie."""

    __tablename__ = "media_refs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    provider: Mapped[str] = mapped_column(String(32), default="immich")
    external_id: Mapped[str] = mapped_column(String(255))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    event: Mapped[Event] = relationship(back_populates="media")


class Metric(Base):
    """Generische Kennzahl (Fitness, Wetter ...), an ein Event gehängt."""

    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    key: Mapped[str] = mapped_column(String(64))  # steps|distance_km|temperature_c|...
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[Source] = mapped_column(Enum(Source), default=Source.fitness)
    enriched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    event: Mapped[Event] = relationship(back_populates="metrics")
