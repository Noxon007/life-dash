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
    # Provenienz (P2.7): wann/wodurch bestätigt ("manual" | "bulk" | "import")
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
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
# Tracks (Routenverläufe, Stufe 3) — Google-Timeline-Import
# --------------------------------------------------------------------------- #
class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    date_start: datetime
    date_end: datetime
    points: list  # [[lat, lng], ...]
    activity_type: str | None = None
    distance_m: float | None = None
    source: Source


class TimelineImportResult(BaseModel):
    """Zusammenfassung eines Timeline-Imports."""
    visits_created: int
    tracks_created: int
    skipped_duplicates: int
    skipped_invalid: int
    # A12: Besuche unterhalb der Mindest-Ortssicherheit (min_probability)
    skipped_low_probability: int = 0
    date_min: datetime | None = None
    date_max: datetime | None = None
    # Reverse-Geocoding: direkt beim Import aufgelöste neue Orte bzw.
    # verbleibende Koordinaten-Namen (-> Button „Ortsnamen auflösen")
    names_resolved: int = 0
    locations_unnamed: int = 0


class PlaceNameResolveResult(BaseModel):
    """Ergebnis eines „Ortsnamen auflösen"-Batchlaufs."""
    resolved: int
    failed: int
    remaining: int


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
# P2.5 — Bulk-Bestätigen (Vorschau + Ausführung nutzen denselben Filter)
# --------------------------------------------------------------------------- #
class BulkConfirmFilter(BaseModel):
    """Filter, welche unbestätigten Events bestätigt werden sollen.
    Ohne Angaben trifft er ALLE unbestätigten Events des Nutzers."""
    category: str | None = None
    source: Source | None = None
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)
    date_from: datetime | None = None
    date_to: datetime | None = None


class BulkConfirmPreview(BaseModel):
    """Vorschau: Anzahl + Stichprobe der Events, die bestätigt würden."""
    total: int
    events: list[EventRead]


class BulkConfirmResult(BaseModel):
    confirmed: int


# --------------------------------------------------------------------------- #
# Module
# --------------------------------------------------------------------------- #
class ModuleRead(BaseModel):
    key: str
    label: str
    icon: str | None = None
    # A7: Frontend-Bausteine direkt aus dem Modul-YAML
    color: str | None = None
    emoji: str | None = None
    compendium: bool = False
    category_labels: dict = {}
    event_categories: list[str] = []
