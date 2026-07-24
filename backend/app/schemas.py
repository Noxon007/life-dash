"""Pydantic-Schemas für Request/Response."""
from __future__ import annotations

from datetime import date as date_type
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
    """Frontend-Info: 'dev' = kein Login nötig, 'oidc' = Login-Redirect,
    'local' = E-Mail/Passwort-Formular."""
    mode: str
    # A27: optionaler Anzeigename des SSO-Providers (kosmetisch)
    provider_name: str = ""
    # A35: gibt es schon Konten? Nein -> das Formular bietet Registrierung
    # (der erste Nutzer wird Admin) statt nur Login an.
    needs_setup: bool = False


class LocalLogin(BaseModel):
    """A35: Anmeldung mit lokalem Konto."""
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=1024)


class LocalRegister(BaseModel):
    """A35: Konto anlegen. Öffentlich nur für den allerersten Nutzer (Admin);
    danach legt ein Admin weitere Konten an."""
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=1024)
    display_name: str | None = Field(None, max_length=255)


class PasswordChange(BaseModel):
    """A35: eigenes Passwort ändern."""
    current_password: str = Field(..., min_length=1, max_length=1024)
    new_password: str = Field(..., min_length=8, max_length=1024)


class AdminCreateUser(BaseModel):
    """A35: ein Admin legt ein weiteres lokales Konto an."""
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=1024)
    display_name: str | None = Field(None, max_length=255)
    role: UserRole = UserRole.user


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
class FragmentCreate(BaseModel):
    raw_text: str = Field(..., min_length=1, examples=["12.07.2026 war in Detmold und habe einen Adler gesehen"])
    source: Source = Source.manual
    # F2: optionaler Gerätestandort (nur per Knopf, nie automatisch);
    # der Text hat Vorrang, wenn er selbst einen Ort nennt
    capture_lat: float | None = Field(None, ge=-90, le=90)
    capture_lng: float | None = Field(None, ge=-180, le=180)
    # P5.1: Kennung des Clients für EINE Erfassung. Nur die Offline-Warteschlange
    # setzt sie — sie ist die einzige Stelle, die dieselbe Erfassung ein zweites
    # Mal senden kann, wenn die Antwort unterwegs verloren ging. Ohne das Feld
    # verhält sich /api/ingest wie bisher: zweimal derselbe Text sind zwei
    # Erfassungen, weil ein Mensch das genau so meinen kann.
    client_id: str | None = Field(None, max_length=64)


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    name: str
    attributes: dict = {}
    confirmed: ConfirmState
    event_count: int = 0  # Anzahl verknüpfter Events (Kompendium-Kacheln)


class CityRead(BaseModel):
    """A41: eine besuchte Stadt fürs Kompendium — aggregiert aus
    `Location.city` (A39), nicht als eigene Zeile gespeichert. `name` ist
    zugleich der Filterwert für `/api/events?city=…`."""
    name: str
    country: str | None = None
    event_count: int = 0
    place_count: int = 0     # wie viele Orte in dieser Stadt
    first_visit: datetime | None = None
    last_visit: datetime | None = None


class CityInfoRead(BaseModel):
    """A42: die zwischengespeicherte Wikipedia-Beschreibung einer Stadt.
    `description = None` heißt „nachgesehen, kein Artikel" — nicht „noch nie
    versucht"; die Unterscheidung verhindert einen Abruf bei jedem Öffnen."""
    model_config = ConfigDict(from_attributes=True)
    name: str
    country: str | None = None
    lang: str = "de"
    description: str | None = None
    wiki_title: str | None = None
    wiki_url: str | None = None
    thumbnail: str | None = None


class CityPlaceRead(BaseModel):
    """Ein Ort innerhalb einer Stadt — trägt die Karte der Stadtseite."""
    id: str
    name: str
    lat: float | None = None
    lng: float | None = None
    event_count: int = 0


class CityDetailRead(CityRead):
    """A42: die Stadt als Sammlungs-Eintrag statt als Kachel mit Sprungziel.

    `events` ist eine VORSCHAU (die jüngsten), `event_count` die Wahrheit —
    eine Stadt kann nach einem Import tausende Besuche tragen, und der
    Zeitstrahl mit Stadtfilter zeigt sie vollständig.
    """
    places: list[CityPlaceRead] = []
    events: list["EventRead"] = []
    events_shown: int = 0
    info: CityInfoRead | None = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    type: str | None = None
    lat: float | None = None
    lng: float | None = None
    # A39: Die Stadt reist mit, damit das Frontend eine Gruppe aufklappen und
    # nach Stadt filtern kann, ohne den Namen zu zerlegen. Leerstring heißt
    # „nachgesehen, gibt es hier keine" (siehe Location.city).
    city: str | None = None


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
    # F7: Herkunftsverweis eines Tages-Unterereignisses auf sein Eltern-Event
    parent_event_id: str | None = None
    entities: list[EntityRead] = []
    metrics: list[MetricRead] = []
    media: list["MediaRead"] = []   # F15: angehängte Bilder
    # A36: kompaktes Wetter in der schlanken Liste (statt der Metrik-Zeilen);
    # in der vollen Liste None, dort liest das Frontend die Metriken.
    weather: dict | None = None
    # A37/F7: Wie viele Tages-Kinder hängen an diesem Eintrag? Der Zeitstrahl
    # zählte sie bisher in der geladenen Liste — mit dem Zeitfenster kann ein
    # Kind auf einer anderen Seite liegen, und der Chip zählte still zu wenig.
    child_count: int | None = None
    # A39: Diese Karte steht stellvertretend für mehrere importierte Besuche
    # desselben Tages in derselben Stadt. None heißt: sie steht für sich.
    group: "EventGroup | None" = None


class EventGroup(BaseModel):
    """A39: Was ein zusammengefasster Eintrag vertritt.

    Bewusst mit Zeitspanne statt nur einer Zahl: „12 Besuche" allein wirft die
    Frage auf, wann eigentlich — „12 Besuche, 08:14–19:30" beantwortet sie und
    macht das Aufklappen zur Wahl statt zur Notwendigkeit.
    """
    city: str
    count: int
    first: datetime | None = None
    last: datetime | None = None
    # A47/Anmerkung 134: auf welcher Ebene verdichtet wurde (country|city|
    # district). Das Feld `city` trägt den Wert DIESER Ebene — bei „district"
    # also den Ortsteil („HafenCity"), nicht die Stadt. Ohne die Ebene fragte das
    # Aufklappen immer nach `Location.city` und fand einen Ortsteil-Wert nie.
    level: str = "city"


# --------------------------------------------------------------------------- #
# A37 — schlanke Ansichten fürs serverseitige Zeitfenster
# --------------------------------------------------------------------------- #
class LocationGeo(BaseModel):
    """Nur, was ein Kartenpunkt braucht."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    lat: float
    lng: float | None = None


class EventGeo(BaseModel):
    """A37: Ereignis als Kartenpunkt — ohne Beschreibung, Notiz, Entities und
    Medien. Rund 380 statt 660 Byte je Eintrag; das Wetter bleibt drin, weil
    Marker-Popup und Stopp-Liste es zeigen."""
    id: str
    title: str
    category: str
    date_start: datetime
    date_precision: DatePrecision
    source: Source
    location: LocationGeo
    weather: dict | None = None


class YearCount(BaseModel):
    year: int
    count: int


class EventsIndex(BaseModel):
    """A37: Wie viele Ereignisse liegen wo — ohne ein einziges davon zu laden.

    Trägt die Jahresüberschriften und die Scroll-Länge des Zeitstrahls sowie
    die Kacheln des Heute-Reiters (Gesamtzahl, Unbestätigte, Zeitspanne)."""
    total: int
    dated: int
    undated: int
    unconfirmed: int
    # Importierte Standort-Besuche — der Zeitstrahl blendet sie aus und nennt
    # ihre Zahl auf dem Schalter
    visits: int = 0
    # Anmerkung 110: unscharf datierte Einträge (Monat/Jahreszeit/Jahr/Jahrzehnt
    # oder ganz ohne Datum). Ein eigener Rückstand neben `unconfirmed`, nicht
    # dieselbe Frage: „stimmt das?" gegen „wann war das?".
    fuzzy: int = 0
    # A47: Orte, für die noch nie Adress-Bausteine geholt wurden. Sie tragen
    # die Stufe „Ortsteil" — ohne sie wäre die Auswahl ein Feld, das man
    # anklickt und bei dem nichts passiert. Die Oberfläche sagt es stattdessen,
    # statt still auf die Stadt zurückzufallen (A40).
    locations_no_address: int = 0
    locations_total: int = 0
    year_min: int | None = None
    year_max: int | None = None
    years: list[YearCount] = []
    # F17: der Meilenstein „Geburt" — Grundlage der Alters-Chips, und praktisch
    # immer außerhalb des geladenen Fensters
    birth: dict | None = None


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
    # P5.1: true, wenn dieselbe `client_id` schon einmal ankam — die
    # Warteschlange darf dann streichen, ohne ein zweites Fragment erzeugt zu haben.
    duplicate: bool = False


class JournalSuggestion(BaseModel):
    """F1: Vorschlag für den Tagebuch-Text eines Tages — nichts davon ist gespeichert.

    `text=None` heißt „für diesen Tag gibt es nichts zusammenzufassen"; das ist
    ein Ergebnis und keine Panne, deshalb 200 und kein Fehler. Damit die
    Oberfläche den Grund nennen kann, kommen beide Zählungen mit:
    `used_events` (eingeflossen) und `skipped_unconfirmed` (übergangen, weil
    unbestätigt).
    """
    day: date_type
    text: str | None = None
    used_events: int = 0
    skipped_unconfirmed: int = 0


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
    # F1: persönliche Notiz/Tagebuchtext (Markdown) — nie von der KI angefasst
    note: str | None = None
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
    # A46: Besuche über Mitternacht, die in Tagesstücke geschnitten wurden —
    # und die, deren Spanne dafür zu groß war (SPLIT_MAX_DAYS). Beides steht
    # hier, weil eine Import-Zusammenfassung, die verschweigt, dass sie die
    # Zeilen umgeformt hat, keine Zusammenfassung ist.
    visits_split: int = 0
    visits_too_long: int = 0
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


class MediaRead(BaseModel):
    """F15: ein Bild an einem Event. `url`/`thumb_url` zeigen auf die
    geschützten Endpunkte — Dateien werden nie direkt statisch ausgeliefert."""
    id: str
    # F18: None heißt „hängt an einem Tag, nicht an einem Ereignis" — dann
    # sagt `captured_at`, an welchem.
    event_id: str | None = None
    provider: str
    mime: str | None = None
    bytes: int | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None
    sort_order: int = 0
    captured_at: datetime | None = None
    url: str
    thumb_url: str


class MediaUploadResult(BaseModel):
    """Ergebnis eines Uploads. Die EXIF-Werte sind **Vorschläge** — angewendet
    werden sie erst, wenn der Nutzer zustimmt (Kap. 3.1)."""
    media: MediaRead
    suggested_captured_at: datetime | None = None
    suggested_lat: float | None = None
    suggested_lng: float | None = None


class OnThisDayGroup(BaseModel):
    """F14: Ein Jahrgang des „An diesem Tag"-Rückblicks.

    Ableitung (Schicht 4) — hält keine eigenen Daten, wird bei jedem Aufruf
    frisch aus der Lebensdatenbank berechnet."""
    years_ago: int
    date: date_type
    events: list[EventRead]
    # F16: wie viele es an dem Tag insgesamt waren — die Liste ist gedeckelt,
    # und „3 von 12" ist ehrlicher als stillschweigend abzuschneiden
    total: int = 0


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


# --------------------------------------------------------------------------- #
# F5 — Welt-Reiter (Länderkarte & Kontinente-Checkliste)
# --------------------------------------------------------------------------- #
class VisitedCountry(BaseModel):
    """Ein besuchtes Land — Schlüssel ist der ISO-Code (passt zum GeoJSON)."""
    iso: str
    name: str
    continent: str
    event_count: int
    first_visit: datetime | None = None
    last_visit: datetime | None = None
    # F11: Durchschnittstemperatur der bestätigten Events dieses Landes —
    # None, solange keines davon Wetter trägt
    avg_temp_c: float | None = None


class ContinentProgress(BaseModel):
    """Fortschritt je Kontinent für die Checkliste."""
    code: str
    label: str
    total: int          # Länder auf diesem Kontinent (Stammdaten)
    visited: int
    countries: list[VisitedCountry] = []
    missing: list[str] = []   # noch nicht besuchte Länder — macht es zur Checkliste


class WorldRead(BaseModel):
    """Alles, was der Welt-Reiter braucht — eine reine Ableitung (Schicht 4)."""
    countries_total: int
    countries_visited: int
    continents_total: int
    continents_visited: int
    continents: list[ContinentProgress]
    recent: list[VisitedCountry] = []   # zuletzt neu besucht
    # Länder-Entities, die zu keinem Eintrag der Stammdaten passen (Tippfehler,
    # historische Namen) — sichtbar machen statt stillschweigend verschlucken.
    unmatched: list[str] = []


# --------------------------------------------------------------------------- #
# F6 — Achievements (Bronze/Silber/Gold/Platin)
# --------------------------------------------------------------------------- #
class AchievementRead(BaseModel):
    """Ein Erfolg samt aktuellem Stand — jederzeit neu berechenbar."""
    id: str
    module: str
    label: str
    description: str | None = None
    emoji: str | None = None
    value: int                      # aktueller Metrik-Wert
    tier: str | None = None         # erreichte Stufe: bronze|silber|gold|platin
    tier_index: int = 0             # 0 = noch keine Stufe, 4 = platin
    next_tier: str | None = None    # nächste Stufe (None = alle Stufen erreicht)
    # F19: Ziel — solange es Stufen gibt deren Schwelle, danach die erzeugte
    # Marke. EIN Feld für beides, damit die Anzeige nicht zwei Fälle rechnen
    # muss; `beyond_top` sagt, wie es zu benennen ist ("Gold" vs. "Marke").
    next_threshold: int | None = None
    beyond_top: bool = False        # über der höchsten Stufe, zählt weiter
    marks_passed: int = 0           # bereits passierte Marken oberhalb
    progress: float = 0.0           # 0..1 bis zum nächsten Ziel
    thresholds: dict[str, int] = {}


class AchievementsRead(BaseModel):
    earned: int                     # Erfolge mit mindestens Bronze
    total: int
    points: int                     # Bronze 1, Silber 2, Gold 3, Platin 4
    achievements: list[AchievementRead]
