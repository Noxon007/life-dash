"""Pydantic-Schemas für Request/Response."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ConfirmState, DatePrecision, FragmentStatus, Source, UserRole


# --------------------------------------------------------------------------- #
# Auth / Nutzer
# --------------------------------------------------------------------------- #
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str | None = None
    display_name: str | None = None
    role: UserRole


class AuthConfig(BaseModel):
    """Frontend-Info: 'dev' = kein Login nötig, 'oidc' = Login-Redirect."""
    mode: str


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
class FragmentCreate(BaseModel):
    raw_text: str = Field(..., min_length=1, examples=["12.07.2026 war in Detmold und habe einen Adler gesehen"])
    source: Source = Source.manual


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    name: str
    attributes: dict = {}
    confirmed: ConfirmState
    event_count: int = 0  # Anzahl verknüpfter Events (Kompendium-Kacheln)


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    type: str | None = None
    lat: float | None = None
    lng: float | None = None


class MetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    value: float | None = None
    value_text: str | None = None
    unit: str | None = None
    source: Source


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    date_precision: DatePrecision
    category: str
    note: str | None = None
    confidence: float
    confirmed: ConfirmState
    source: Source
    location: LocationRead | None = None
    origin_fragment_id: str | None = None
    entities: list[EntityRead] = []
    metrics: list[MetricRead] = []


class FragmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    raw_text: str
    source: Source
    status: FragmentStatus
    created_at: datetime


class IngestResult(BaseModel):
    """Ergebnis der Ingestion: das Roh-Fragment + die erzeugten Events (Stufe-2-Vorschau)."""
    fragment: FragmentRead
    events: list[EventRead]


# --------------------------------------------------------------------------- #
# Manuelle Eingabe (ohne KI): Nutzer trägt alle Felder selbst ein
# --------------------------------------------------------------------------- #
class ManualEntity(BaseModel):
    type: str = Field(..., examples=["animal"])
    name: str = Field(..., min_length=1, examples=["Hai"])
    attributes: dict = {}


class EventManualCreate(BaseModel):
    """Manuell erfasstes Event. Wird sofort als `confirmed` gespeichert —
    der Nutzer ist hier selbst die Quelle der Struktur."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    date_precision: DatePrecision = DatePrecision.day
    category: str = "event"
    location_name: str | None = None
    entities: list[ManualEntity] = []


# --------------------------------------------------------------------------- #
# Moderation
# --------------------------------------------------------------------------- #
class EventUpdate(BaseModel):
    """Manuelle Korrektur eines Events. Gesetzte Felder werden als override markiert."""
    title: str | None = None
    description: str | None = None
    category: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    date_precision: DatePrecision | None = None
    note: str | None = None  # persönlicher Kommentar
    # Neuer Ortsname/Adresse -> wird geocodiert (bis Straße/Hausnummer).
    # Leerer String = Ort entfernen.
    location_name: str | None = None
    # Ersetzt die verknüpften Objekte vollständig (z. B. "Seeadler" -> "Adler").
    # Leere Liste = alle Verknüpfungen entfernen. None = unverändert.
    entities: list[ManualEntity] | None = None


# --------------------------------------------------------------------------- #
# Module
# --------------------------------------------------------------------------- #
class ModuleRead(BaseModel):
    key: str
    label: str
    icon: str | None = None
    event_categories: list[str] = []
