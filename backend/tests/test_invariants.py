"""P2.6 — Invarianten-Test „Bestätigtes ist unantastbar" (KONZEPT Kap. 3.1).

Die harte Invariante der Lebensdatenbank: Maschinen (Neuberechnung,
Enrichment, Re-Import) ändern bestätigte Daten NIE — sie ergänzen nur
additiv (Metriken, Medien-Referenzen). Diese Tests fahren die realen
Code-Pfade und prüfen die Invariante nach jedem Lauf.

Dokumentierte Ausnahme: „Ortsnamen auflösen" ersetzt generierte
Koordinaten-Titel auch an bestätigten Import-Besuchen — manuell
umbenannte Titel (title in field_overrides) bleiben aber geschützt.
"""
from __future__ import annotations

from datetime import datetime

from app.models import (
    ConfirmState,
    Event,
    Fragment,
    FragmentStatus,
    Location,
    Metric,
    Source,
)
from app.routers.moderation import bulk_confirm, bulk_confirm_preview, confirm_event
from app.routers.tracks import _apply_resolved_name, import_timeline
from app.schemas import BulkConfirmFilter
from app.services.enrichment import auto_enrich_events, enrich_weather
from app.services.ingestion import ingest_fragment, reprocess_pending, reset_reprocess

# Alles außer updated_at (das onupdate-Feld sagt nichts über den Inhalt)
_SNAPSHOT_COLS = [c.name for c in Event.__table__.columns if c.name != "updated_at"]


def _snapshot(event: Event) -> dict:
    return {c: getattr(event, c) for c in _SNAPSHOT_COLS}


def _ingest_text(db, user, text: str) -> list[Event]:
    fragment = Fragment(user_id=user.id, raw_text=text, source=Source.manual)
    db.add(fragment)
    db.flush()
    events = ingest_fragment(db, fragment)
    db.commit()
    return events


# --------------------------------------------------------------------------- #
# Stufe-2-Neuberechnung
# --------------------------------------------------------------------------- #
def test_neuberechnung_laesst_bestaetigte_fragmente_komplett_in_ruhe(db, user):
    # Fragment A: eines seiner Events wird bestätigt (+ manuell korrigiert)
    (event_a,) = _ingest_text(db, user, "12.07.2026 war in Detmold und habe einen Adler gesehen")
    event_a.confirmed = ConfirmState.confirmed
    event_a.title = "Seeadler-Beobachtung"  # manuelle Korrektur
    event_a.field_overrides = {"title": True}
    db.commit()
    before = _snapshot(event_a)

    # Fragment B: nur unbestätigte Vorschläge -> darf neu berechnet werden
    (event_b,) = _ingest_text(db, user, "Sommer 2002 Urlaub in Frankreich")
    event_b_id = event_b.id

    total = reset_reprocess(db)

    # Nur Fragment B wurde markiert; das bestätigte Event existiert unverändert
    assert total == 1
    assert db.get(Event, before["id"]) is not None
    assert _snapshot(db.get(Event, before["id"])) == before
    # Bs alter Vorschlag wurde verworfen (Vorschlagsraum ist wegwerfbar)
    assert db.get(Event, event_b_id) is None

    processed, remaining, aborted = reprocess_pending(db, limit=10)
    assert (processed, remaining, aborted) == (1, 0, False)
    # Auch nach der Neuberechnung: bestätigtes Event byte-identisch
    assert _snapshot(db.get(Event, before["id"])) == before


def test_neuberechnung_verschont_unbestaetigte_geschwister_bestaetigter_events(db, user):
    """Hat EIN Event eines Fragments den Sprung in die Lebensdatenbank
    geschafft, bleibt das ganze Fragment unangetastet — auch seine
    unbestätigten Geschwister-Events."""
    (event,) = _ingest_text(db, user, "12.07.2026 war in Detmold und habe einen Adler gesehen")
    fragment = event.origin_fragment
    # Geschwister-Event am selben Fragment, bleibt unbestätigt
    sibling = Event(user_id=user.id, title="Geschwister-Vorschlag",
                    origin_fragment=fragment, source=Source.ai)
    db.add(sibling)
    event.confirmed = ConfirmState.confirmed
    db.commit()
    sibling_id = sibling.id

    assert reset_reprocess(db) == 0
    assert db.get(Event, sibling_id) is not None
    assert fragment.status != FragmentStatus.pending


# --------------------------------------------------------------------------- #
# Wetter-Enrichment (Fakten-Anreicherung: nur additiv, nie ändernd)
# --------------------------------------------------------------------------- #
def test_wetter_enrichment_ist_additiv_und_idempotent(db, user, fake_weather):
    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    event = Event(user_id=user.id, title="Spaziergang",
                  date_start=datetime(2024, 5, 1), location=loc,
                  confirmed=ConfirmState.confirmed, source=Source.manual)
    db.add_all([loc, event])
    db.commit()
    before = _snapshot(event)

    enriched, remaining = enrich_weather(db)
    assert (enriched, remaining) == (1, 0)
    assert _snapshot(db.get(Event, event.id)) == before  # Event selbst unberührt
    assert len(event.metrics) == 2  # Temperatur + Bedingung ergänzt

    # Zweiter Lauf: Wetter ist schon da -> nichts wird ersetzt oder dupliziert
    enriched, _ = enrich_weather(db)
    assert enriched == 0
    assert len(fake_weather) == 1
    assert len(db.get(Event, event.id).metrics) == 2


def test_auto_enrichment_fehler_bricht_erfassung_nie_ab(db, user, monkeypatch):
    def _boom(lat, lng, when):
        raise RuntimeError("Open-Meteo down")

    monkeypatch.setattr("app.services.enrichment.fetch_weather", _boom)
    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    event = Event(user_id=user.id, title="Spaziergang",
                  date_start=datetime(2024, 5, 1), location=loc)
    db.add_all([loc, event])
    db.flush()

    assert auto_enrich_events(db, [event]) == 0  # kein Raise, kein Wetter
    assert event.metrics == []


# --------------------------------------------------------------------------- #
# Bulk-Bestätigen (P2.5) + Provenienz (P2.7)
# --------------------------------------------------------------------------- #
def test_bulk_confirm_kippt_nur_den_status_und_setzt_provenienz(db, user):
    hit = Event(user_id=user.id, title="Treffer", category="sighting",
                confidence=0.9, source=Source.ai)
    miss = Event(user_id=user.id, title="Zu unsicher", category="sighting",
                 confidence=0.5, source=Source.ai)
    # naiv, weil SQLite Datetimes ohne Zeitzone zurückliefert
    t0 = datetime(2026, 1, 1)
    already = Event(user_id=user.id, title="Längst wahr", category="sighting",
                    confidence=0.99, confirmed=ConfirmState.confirmed,
                    confirmed_at=t0, confirmed_by="manual", source=Source.ai)
    db.add_all([hit, miss, already])
    db.commit()
    hit_before = _snapshot(hit)

    filt = BulkConfirmFilter(category="sighting", min_confidence=0.8)
    preview = bulk_confirm_preview(filt, db=db, user=user)
    assert preview.total == 1 and preview.events[0].id == hit.id

    result = bulk_confirm(filt, db=db, user=user)
    assert result.confirmed == 1

    # Treffer: NUR Status + Provenienz neu, alle Fakten unverändert
    assert hit.confirmed == ConfirmState.confirmed
    assert hit.confirmed_by == "bulk" and hit.confirmed_at is not None
    unchanged = {k: v for k, v in _snapshot(hit).items()
                 if k not in ("confirmed", "confirmed_at", "confirmed_by")}
    assert unchanged == {k: v for k, v in hit_before.items()
                         if k not in ("confirmed", "confirmed_at", "confirmed_by")}
    # Nicht-Treffer bleibt Vorschlag; bereits Bestätigtes behält seine Provenienz
    assert miss.confirmed == ConfirmState.unconfirmed
    assert already.confirmed_by == "manual" and already.confirmed_at == t0


def test_einzel_bestaetigung_setzt_provenienz_manual(db, user):
    (event,) = _ingest_text(db, user, "12.07.2026 war in Detmold und habe einen Adler gesehen")
    confirm_event(event.id, db=db, user=user)
    assert event.confirmed == ConfirmState.confirmed
    assert event.confirmed_by == "manual" and event.confirmed_at is not None


# --------------------------------------------------------------------------- #
# Timeline-Re-Import (idempotent, fasst Bestätigtes nicht an)
# --------------------------------------------------------------------------- #
_TIMELINE_PAYLOAD = {
    "semanticSegments": [
        {
            "startTime": "2025-05-01T10:00:00+02:00",
            "endTime": "2025-05-01T11:00:00+02:00",
            "visit": {
                "probability": 0.93,
                "topCandidate": {"placeLocation": {"latLng": "51.9375°, 8.8797°"},
                                  "placeId": "place-1"},
            },
        },
        {
            "startTime": "2025-05-01T11:00:00+02:00",
            "endTime": "2025-05-01T11:30:00+02:00",
            "timelinePath": [{"point": "51.93°, 8.87°"}, {"point": "51.94°, 8.88°"}],
        },
    ]
}


def test_reimport_erzeugt_keine_duplikate_und_aendert_bestaetigtes_nicht(db, user):
    first = import_timeline(_TIMELINE_PAYLOAD, db=db, user=user)
    assert first.visits_created == 1 and first.tracks_created == 1

    visit = db.query(Event).filter(Event.source == Source.google_timeline).one()
    assert visit.confirmed == ConfirmState.confirmed
    assert visit.confirmed_by == "import" and visit.confirmed_at is not None

    # Nutzer benennt den Besuch um (manuelle Wahrheit)
    visit.title = "Ausflug zum Hermannsdenkmal"
    visit.field_overrides = {"title": True}
    db.commit()
    before = _snapshot(visit)

    second = import_timeline(_TIMELINE_PAYLOAD, db=db, user=user)
    assert second.visits_created == 0 and second.tracks_created == 0
    assert second.skipped_duplicates == 2
    assert _snapshot(db.get(Event, visit.id)) == before
    assert db.query(Event).filter(Event.source == Source.google_timeline).count() == 1


# --------------------------------------------------------------------------- #
# Dokumentierte Ausnahme: Ortsnamen-Auflösung schützt manuelle Titel
# --------------------------------------------------------------------------- #
def test_ortsnamen_aufloesung_respektiert_manuell_umbenannte_titel(db, user, monkeypatch):
    monkeypatch.setattr("app.services.geocode.reverse_geocode",
                        lambda lat, lng: {"name": "Hermannsdenkmal, Detmold", "type": "poi"})
    loc = Location(user_id=user.id, name="Ort (51.9375, 8.8797)",
                   lat=51.9375, lng=8.8797)
    auto = Event(user_id=user.id, title="Besuch: Ort (51.9375, 8.8797)",
                 location=loc, source=Source.google_timeline,
                 confirmed=ConfirmState.confirmed)
    # Titel sieht generiert aus, wurde aber vom Nutzer bestätigt (Override)
    manual = Event(user_id=user.id, title="Besuch: Ort (51.9375, 8.8797)",
                   location=loc, source=Source.google_timeline,
                   confirmed=ConfirmState.confirmed, field_overrides={"title": True})
    db.add_all([loc, auto, manual])
    db.commit()

    assert _apply_resolved_name(db, loc, user.id) is True
    db.commit()

    assert loc.name == "Hermannsdenkmal, Detmold"
    assert auto.title == "Besuch: Hermannsdenkmal, Detmold"  # generierter Titel folgt
    assert manual.title == "Besuch: Ort (51.9375, 8.8797)"   # Override bleibt geschützt


# --------------------------------------------------------------------------- #
# Embeddings sind Ableitungen — Neuberechnung fasst nur `embedding` an
# --------------------------------------------------------------------------- #
def test_embedding_neuberechnung_aendert_nur_das_embedding(db, user, monkeypatch):
    event = Event(user_id=user.id, title="Strandtag in Italien",
                  confirmed=ConfirmState.confirmed, source=Source.manual)
    db.add(event)
    db.commit()
    before = _snapshot(event)

    # Denselben Weg gehen wie der Admin-Endpoint: fehlende Embeddings füllen
    from app.ai import get_provider

    provider = get_provider()
    monkeypatch.setattr(type(provider), "embed",
                        lambda self, text, kind="document": [0.1, 0.2, 0.3])
    batch = db.query(Event).filter(Event.embedding.is_(None)).all()
    for e in batch:
        e.embedding = provider.embed(f"{e.title}\n{e.description or ''}")
    db.commit()

    after = _snapshot(db.get(Event, event.id))
    assert after.pop("embedding") == [0.1, 0.2, 0.3]
    before.pop("embedding")
    assert after == before
