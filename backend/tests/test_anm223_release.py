"""Anmerkung 223 — Teil 4 der Durchsicht: Betrieb, Start und Auslieferung.

Das Auffälligste an dieser Runde steht nicht in einem einzelnen Test:
**seit SQLite Fremdschlüssel erzwingt, prüft die schnelle Suite eine
Fehlerklasse mit, die vorher nur PostgreSQL sah.** Der erste Versuch war dabei
selbst die Falle — das Pragma hing an der Engine der ANWENDUNG, die Testsuite
baut sich ihre eigene, und 902 Tests liefen grün, ohne dass die Erzwingung im
Lauf galt.

Was Docker angeht, kann hier nichts gefahren werden (kein Docker auf dieser
Maschine, siehe Anmerkung 210). Geprüft wird deshalb, was sich ohne Bau prüfen
lässt: dass die Konfigurationsdateien einander nicht widersprechen. Das ist
genau der Defekt gewesen — nicht ein kaputtes Image, sondern ein `MEDIA_DIR`,
das an drei Stellen stand und an der vierten fehlte.
"""
from __future__ import annotations

import pathlib
import re

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.database import Base, attach_sqlite_pragmas, is_memory_url
from app.migrate import _adoptable_tables, adopt_orphan_rows, ensure_schema
from app.models import Event, Location, MediaRef, Track, User, UserRole

ROOT = pathlib.Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
#  (a) Fremdschlüssel gelten jetzt auch auf SQLite
# --------------------------------------------------------------------------- #
def test_foreign_keys_are_enforced_in_the_test_database(db):
    """**Der Test, der den ersten Entwurf entlarvt hätte.**

    Das Pragma stand zuerst nur an der Engine der Anwendung. Die Suite baut
    ihre eigene (`conftest.db`) und bekam davon nichts mit — 902 Tests grün,
    Erzwingung im Betrieb, nicht im Lauf. Genau die Klasse „Prüfungen, die
    nichts prüfen": grün, weil es die Einstellung GIBT, nicht weil sie hier
    gilt.
    """
    if db.bind.dialect.name != "sqlite":
        return                      # PostgreSQL erzwingt sie ohnehin
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_an_orphan_cannot_be_written(db, user):
    """Eine Metrik ohne ihr Ereignis wird abgewiesen statt still angelegt."""
    from sqlalchemy.exc import IntegrityError
    from app.models import Metric, Source

    db.add(Metric(event_id="gibt-es-nicht", key="temperature_c", value=1.0,
                  source=Source.weather))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_pragmas_are_one_list(db):
    """Anwendung und Test lesen dieselbe Aufzählung.

    Zwei Fassungen wären zwei Datenbanken mit verschiedenen Regeln — und die
    eine, die geprüft wird, wäre die, die niemand betreibt.
    """
    from app.database import SQLITE_PRAGMAS

    assert "PRAGMA foreign_keys=ON" in SQLITE_PRAGMAS


# --------------------------------------------------------------------------- #
#  (b) Der Import muss Eltern vor Kinder setzen
# --------------------------------------------------------------------------- #
def test_a_backup_with_the_child_first_still_restores(db, user):
    """Der Fall, den die Erzwingung sofort gefunden hat.

    Der Export liest in der Reihenfolge der Datenbank und sagt zu Eltern und
    Kindern nichts zu. Dass das funktionierte, lag an zwei verschiedenen
    Zufällen: SQLite erzwang nichts, und PostgreSQL prüft am Ende der
    ANWEISUNG — SQLAlchemy schreibt einen Block als ein einziges `INSERT …
    VALUES (…), (…)`, also stand am Ende beides da.

    Auf SQLite mit erzwungenen Fremdschlüsseln zerreißt es: dort ist
    `executemany` eine Anweisung je Zeile.
    """
    from app.routers.data import import_data

    payload = {
        "format": "lifedash-export",
        "locations": [{"id": "loc-1", "name": "Zuhause", "lat": 52.0, "lng": 13.0}],
        "events": [
            {"id": "kind-1", "title": "Reise — Tag 2", "category": "trip",
             "date_start": "2026-05-06T10:00:00", "date_precision": "day",
             "source": "manual", "confirmed": "confirmed",
             "parent_event_id": "eltern-1", "location_id": "loc-1"},
            {"id": "eltern-1", "title": "Reise", "category": "trip",
             "date_start": "2026-05-05T10:00:00", "date_precision": "day",
             "source": "manual", "confirmed": "confirmed", "location_id": "loc-1"},
        ],
    }
    result = import_data(payload=payload, db=db, user=user)
    assert result["imported"]["events"] == 2
    kid = db.get(Event, "kind-1")
    assert kid is not None and kid.parent_event_id == "eltern-1"


def test_only_self_references_are_reordered():
    """Wer nicht auf die eigene Tabelle zeigt, behält seinen Platz.

    Sonst wäre aus einer Sortierung gegen einen Fremdschlüssel eine
    Umsortierung des ganzen Backups geworden — und die Reihenfolge im Export
    ist die einzige Spur der Herkunft, die eine Datei noch hat.
    """
    from app.routers.data import _parents_first, _self_ref

    assert _self_ref(Event) == "parent_event_id"
    assert _self_ref(Location) is None
    rows = [{"id": "b"}, {"id": "a"}, {"id": "c"}]
    assert _parents_first(Location, rows) == rows        # keine Selbstbeziehung
    assert _parents_first(Event, rows) == rows           # keine Verweise


def test_a_cycle_does_not_hang_the_import():
    """Eine von Hand geschriebene Datei darf den Lauf nicht aufhängen."""
    from app.routers.data import _parents_first

    rows = [{"id": "a", "parent_event_id": "b"}, {"id": "b", "parent_event_id": "a"}]
    assert len(_parents_first(Event, rows)) == 2


# --------------------------------------------------------------------------- #
#  (c) Altdaten ohne Besitzer
# --------------------------------------------------------------------------- #
def test_orphans_of_every_owned_table_are_adopted(tmp_path):
    """`tracks` und `media_refs` fehlten in der Aufzählung.

    Beide werden überall über `user_id` gefiltert — eine Zeile ohne Besitzer
    ist damit für immer unsichtbar, **auch im Export**, und beim Löschen des
    Kontos wäre sie stehen geblieben.
    """
    assert {"tracks", "media_refs"} <= set(_adoptable_tables())


def test_the_job_log_is_not_adopted():
    """**Die Gegenprobe.** `jobs` hat eine nullbare `user_id` und ist trotzdem
    kein Nutzerbesitz.

    Der erste Entwurf fragte das Schema („jede Tabelle mit nullbarer
    `user_id`") und griff damit das Lauf-Protokoll mit. Ein systemweiter Lauf
    hat ausdrücklich keinen Besitzer; ihn dem ersten Konto zuzuschlagen wäre
    eine erfundene Aussage. Gefragt wird deshalb `wipe.WIPE_ORDER`, das diese
    Frage schon beantwortet.
    """
    assert "jobs" not in _adoptable_tables()
    assert "users" not in _adoptable_tables()


def test_adoption_reaches_tracks_and_media(tmp_path):
    """Und zwar wirklich, nicht nur in der Liste."""
    engine = create_engine(f"sqlite:///{tmp_path/'adopt.db'}")
    attach_sqlite_pragmas(engine)
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, oidc_subject, role, settings, created_at) "
            "VALUES ('u1', 'sub', 'admin', '{}', '2020-01-01')"))
        conn.execute(text(
            "INSERT INTO tracks (id, date_start, date_end, points, source, created_at) "
            "VALUES ('t1', '2020-01-01', '2020-01-02', '[]', 'google_timeline', "
            "'2020-01-01')"))
        conn.execute(text(
            "INSERT INTO media_refs (id, provider, external_id, sort_order, created_at) "
            "VALUES ('m1', 'local', 'a.jpg', 0, '2020-01-01')"))

    assert adopt_orphan_rows(engine, "u1") >= 2
    with engine.connect() as conn:
        assert conn.execute(text("SELECT user_id FROM tracks")).scalar() == "u1"
        assert conn.execute(text("SELECT user_id FROM media_refs")).scalar() == "u1"
    engine.dispose()


# --------------------------------------------------------------------------- #
#  (d) Start und Migration
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url, memory", [
    ("sqlite://", True),
    ("sqlite:///:memory:", True),
    ("sqlite:///./lifedash.db", False),
    ("postgresql+psycopg2://x@y/z", False),
])
def test_both_spellings_of_in_memory_are_known(url, memory):
    """`sqlite://` ist die gebräuchlichere von beiden und fiel durch.

    Sie bekam die Pool-Argumente, landete auf `SingletonThreadPool`, und
    `create_engine` warf einen `TypeError` beim IMPORT des Moduls — kein
    Startfehler mit Meldung, sondern ein Absturz, bevor irgendetwas lief.
    """
    assert is_memory_url(url) is memory


def test_the_weather_cleanup_runs_only_without_its_index(tmp_path):
    """Eine einmalige Nacharbeit läuft nicht bei jedem Start.

    Der `DELETE` mit `GROUP BY` ging über die ganze Metrik-Tabelle — am
    Demo-Bestand 143.000 Zeilen — und konnte seit dem ersten Lauf nichts mehr
    finden: **der Index IST die Zusage.**
    """
    engine = create_engine(f"sqlite:///{tmp_path/'wx.db'}")
    attach_sqlite_pragmas(engine)
    ensure_schema(engine)
    have = {ix["name"] for ix in inspect(engine).get_indexes("metrics")}
    assert "ux_metrics_weather" in have

    seen: list[str] = []

    from sqlalchemy import event as sa_event

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _watch(conn, cursor, statement, params, context, many):
        seen.append(statement)

    ensure_schema(engine)           # zweiter Start
    assert not any("DELETE FROM metrics" in s for s in seen), (
        "Die Dubletten-Aufräumung läuft bei jedem Start erneut")
    engine.dispose()


def test_a_legacy_rebuild_survives_a_dangling_owner(tmp_path):
    """Der Neubau darf an einer Altdaten-Waise nicht abbrechen.

    Der Tabellen-Neubau (F18) kopiert in ein Schema, das STRENGER ist als das
    alte: `media_refs.user_id` hat seit dieser Runde einen Fremdschlüssel,
    vorher war es ein `VARCHAR(36)`, das zufällig wie eine Kennung aussah. Eine
    Altdatenbank mit einem Zeiger auf ein Konto, das es nicht gibt, hätte den
    Start damit unmöglich gemacht — aus einer alten Unsauberkeit wäre eine
    Instanz geworden, die nicht mehr hochkommt.

    **Ein Zeiger auf ein Konto, das es nicht gibt, ist keine Angabe, sondern
    ein Schaden.** NULL sagt dasselbe, nur ehrlich.
    """
    engine = create_engine(f"sqlite:///{tmp_path/'legacy.db'}")
    attach_sqlite_pragmas(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE media_refs (id VARCHAR(36) PRIMARY KEY, "
            "user_id VARCHAR(36), event_id VARCHAR(36) NOT NULL, "
            "provider VARCHAR(32), external_id VARCHAR(255), "
            "captured_at DATETIME, sort_order INTEGER, created_at DATETIME)"))
        conn.execute(text(
            "INSERT INTO media_refs VALUES ('m1', 'weg', 'e1', 'local', 'a.jpg', "
            "'2020-01-01', 0, '2020-01-01')"))

    ensure_schema(engine)           # darf nicht werfen

    with engine.connect() as conn:
        assert conn.execute(text("SELECT user_id FROM media_refs")).scalar() is None
        assert not list(conn.exec_driver_sql("PRAGMA foreign_key_check"))
    engine.dispose()


def test_the_label_cleanup_asks_before_it_writes(tmp_path):
    """Dasselbe für die Alt-Label-Umbenennung (A19)."""
    engine = create_engine(f"sqlite:///{tmp_path/'lbl.db'}")
    attach_sqlite_pragmas(engine)
    ensure_schema(engine)
    seen: list[str] = []

    from sqlalchemy import event as sa_event

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _watch(conn, cursor, statement, params, context, many):
        seen.append(statement)

    ensure_schema(engine)
    assert not any(s.startswith("UPDATE locations") for s in seen)
    assert not any(s.startswith("UPDATE events") for s in seen)
    engine.dispose()


# --------------------------------------------------------------------------- #
#  (e) Was ohne Docker prüfbar ist: die Dateien widersprechen sich nicht
# --------------------------------------------------------------------------- #
def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_the_image_sets_every_path_it_needs():
    """`MEDIA_DIR` stand in Compose und Einstiegspunkt und fehlte im Image.

    Über `docker compose` fiel das nie auf. Wer das Image direkt startet, bekam
    `/app/media`: außerhalb des `/data`-Volumes (Fotos weg beim nächsten
    `docker run`) und in einem Verzeichnis, das root gehört, während der Prozess
    als 10001 läuft.
    """
    dockerfile = _read("Dockerfile")
    for var in ("MODULES_DIR", "FRONTEND_DIR", "DATABASE_URL", "MEDIA_DIR"):
        # `ENV MODULES_DIR=…` steht mit dem Schlüsselwort davor, die übrigen
        # eingerückt in derselben Gruppe — beides trifft „Wortgrenze, dann =".
        assert re.search(rf"(?:^|\s){var}=", dockerfile, re.M), \
            f"Das Dockerfile setzt {var} nicht"


def test_image_and_entrypoint_agree_on_the_media_path():
    """Ein Image, das seine eigene Vorgabe anders beantwortet als sein
    Einstiegspunkt, ist die Doppelregel in ihrer teuersten Form."""
    image = re.search(r"MEDIA_DIR=(\S+)", _read("Dockerfile")).group(1)
    entry = re.search(r'MEDIA_DIR:-([^}]+)\}', _read("docker-entrypoint.sh")).group(1)
    compose = re.search(r"MEDIA_DIR: \$\{MEDIA_DIR:-([^}]+)\}",
                        _read("docker-compose.yml")).group(1)
    assert image == entry == compose, (image, entry, compose)


def test_nothing_is_installed_unpinned():
    """Der Datenbanktreiber war das einzige ungepinnte Paket des Images.

    Das Basis-Image hängt am Digest, weil ein Tag „unbrauchbar als Aussage
    darüber ist, was gebaut wurde" — ein Treiber, der bei jedem Bau ein anderer
    sein darf, hebt genau diese Aussage wieder auf.
    """
    assert "psycopg2-binary\n" not in _read("Dockerfile"), \
        "Das Dockerfile installiert noch ein Paket an requirements.txt vorbei"
    for line in _read("backend/requirements.txt").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            assert "==" in line, f"ungepinnt: {line}"


def test_the_image_ships_no_test_tooling():
    """`pytest` lag im Image, ohne dass die Tests darin liegen."""
    prod = _read("backend/requirements.txt")
    assert "pytest" not in prod
    assert "pytest==" in _read("backend/requirements-dev.txt")


def test_the_entrypoint_asks_before_it_chowns():
    """`chown -R` lief bei jedem Start über die ganze Fotobibliothek."""
    entry = _read("docker-entrypoint.sh")
    assert "stat -c" in entry and "continue" in entry


def test_the_world_map_is_in_the_offline_shell():
    """Der Welt-Reiter war die einzige Hauptansicht ohne Netz-Ersatz."""
    sw = _read("frontend/sw.js")
    shell = sw[sw.index("const SHELL"):sw.index("];", sw.index("const SHELL"))]
    assert "/world-countries.geojson" in shell


def test_both_doc_uis_are_excluded_from_the_cache():
    """Von den beiden Doku-Oberflächen stand nur eine da."""
    sw = _read("frontend/sw.js")
    assert '"/docs"' in sw and '"/redoc"' in sw


def test_the_csp_exemption_means_those_paths_and_not_a_prefix():
    """`startswith` nahm auch `/docsomething` von der Regel aus."""
    from app.security import _csp_exempt

    assert _csp_exempt("/docs") and _csp_exempt("/docs/oauth2-redirect")
    assert _csp_exempt("/redoc")
    assert not _csp_exempt("/docsomething")
    assert not _csp_exempt("/redocument")
    assert not _csp_exempt("/")


# --------------------------------------------------------------------------- #
#  (f) Der Changelog-Schnitt
# --------------------------------------------------------------------------- #
def test_unreleased_has_each_heading_once():
    """181 Punkte unter dreizehn Überschriften waren keine Release-Notes.

    `### Changed` kam viermal vor, `### Fixed` dreimal — ein Leser konnte die
    Fehlerbehebungen nicht an einer Stelle finden, und aus diesem Block
    entstehen beim Schnitt die Notizen zur Version.
    """
    text_ = _read("CHANGELOG.md")
    start = text_.index("## [Unreleased]")
    end = text_.index("\n## [", start + 5)
    heads = re.findall(r"^### (.+)$", text_[start:end], re.M)
    assert len(heads) == len(set(heads)), f"doppelte Überschriften: {heads}"
    order = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
    assert heads == [h for h in order if h in heads], (
        f"Reihenfolge nicht nach Keep a Changelog: {heads}")
