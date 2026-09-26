"""Anmerkung 231 — ein Export aus einer ALTEN Version kommt in jeder neuen an.

Seit Anmerkung 231 darf ein teurer Umbau des Datenmodells während der
Testphase auch „neu aufsetzen" heißen, statt die betriebene Datenbank zu
migrieren — aber nur, wenn das KEIN Datenverlust ist. Der Weg dafür ist der
Export: ZIP aus der alten Version, frische Datenbank, Import in der neuen.

**Diese Fixture ist ein echter Export, kein nachgebauter.** Geschrieben hat
ihn v0.39.0, die letzte veröffentlichte Version, aus einem eigenen
Arbeitsbaum gestartet: Einträge mit Ort, Notiz und Entität, ein Mehrtäger,
eine unscharf datierte Reise, Freitext-Erfassungen über die Mock-KI, ein
Google-Timeline-Import mit Besuch und Weg, ein Foto am Ereignis und eins am
Tag. Beim ersten Rundlauf von Hand kamen alle 62 Zeilen an, jedes gemeinsame
Feld identisch, beide Bilder samt Vorschau wiederhergestellt. Dieser Test hält
fest, dass das so bleibt.

Ein nachgebauter Export hätte nur bewiesen, dass der Import das liest, was der
Test glaubt, das eine alte Version schreibt. Was eine alte Version WIRKLICH
schreibt (etwa den Abschnitt `photo_points`, den es heute nicht mehr gibt),
weiß nur die Datei.

Wird das Exportformat einmal bewusst gebrochen, bleibt diese Datei trotzdem
liegen und bekommt eine Nachfolgerin — sie ist dann die Auskunft, AB WANN ein
alter Export nicht mehr ankommt.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.models import (Entity, Event, EventEntityLink, Fragment, Location,
                        MediaRef, Metric, Track)
from app.routers.data import import_archive

FIXTURE = Path(__file__).parent / "fixtures" / "export_v0.39.0.zip"


class _Upload:
    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


@pytest.fixture(autouse=True)
def media_tmp(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    return tmp_path / "media"


def _import(db, user):
    return import_archive(file=_Upload(FIXTURE.read_bytes()), db=db, user=user)


def test_every_row_of_an_old_export_arrives(db, user):
    result = _import(db, user)
    assert result["imported"] == {
        "locations": 8, "fragments": 12, "entities": 5, "events": 12,
        "event_entity_links": 6, "media_refs": 2, "metrics": 16, "tracks": 1,
        "baseline_locations": 0, "day_metrics": 0}
    assert result["skipped_foreign"] == 0
    assert result["media_restored"] == 2
    # und wirklich in der Datenbank, nicht nur in der Antwort gezählt
    for model, n in ((Location, 8), (Fragment, 12), (Entity, 5), (Event, 12),
                     (EventEntityLink, 6), (MediaRef, 2), (Metric, 16), (Track, 1)):
        assert db.query(model).count() == n, model.__tablename__


def test_the_fields_survive_not_only_the_rows(db, user):
    """Stichproben über die Felder, an denen ein Formatwechsel zuerst reißt:
    Datumsgenauigkeit, Zeitspanne, Notiz, Entität, Bildmaße, Besitz."""
    _import(db, user)
    concert = db.query(Event).filter_by(title="Konzert im Stadtpark").one()
    assert concert.note == "mit Anna"
    assert concert.category == "concert"
    assert concert.location is not None and "Stadtpark" in concert.location.name
    assert concert.user_id == user.id
    names = {link.entity.name for link in concert.entity_links}
    assert "Die Ärzte" in names

    trip = db.query(Event).filter_by(title="Urlaub Kreta").one()
    assert trip.date_start.date().isoformat() == "2025-08-01"
    assert trip.date_end.date().isoformat() == "2025-08-14"

    fuzzy = db.query(Event).filter_by(title="Sommer 2002 Frankreich").one()
    assert getattr(fuzzy.date_precision, "value", fuzzy.date_precision) == "season"

    media = db.query(MediaRef).all()
    assert {m.user_id for m in media} == {user.id}
    assert all(m.width == 64 and m.height == 48 for m in media)
    assert sum(1 for m in media if m.event_id is None) == 1   # das Foto am TAG

    assert db.query(Fragment).filter(
        Fragment.raw_text.like("%Adler%")).count() >= 1


def test_the_photos_come_back_as_files(db, user, media_tmp):
    _import(db, user)
    files = [p for p in media_tmp.rglob("*.jpg") if not p.name.endswith(".thumb.jpg")]
    assert len(files) == 2
    assert all(p.stat().st_size > 0 for p in files)


def test_importing_the_old_export_twice_changes_nothing(db, user):
    _import(db, user)
    second = _import(db, user)
    assert second["total"] == 0
    assert db.query(Event).count() == 12
