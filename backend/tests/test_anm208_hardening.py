"""Anmerkung 208 — die Härtung aus R1(d), und was daran wirklich prüfbar ist.

Drei Gruppen, und nur die mittlere ist interessant.

**Die Kopfzeilen** lassen sich stumpf ablesen; der einzige Fall mit Substanz
ist die Ausnahme für `/docs` — eine Regel MIT Ausnahme ist eine, die man
prüfen muss, sonst wandert die Ausnahme beim nächsten Umbau still auf alles.

**Die CSP-Hashes** sind die Gruppe, die es gibt, weil dieser Code beim ersten
Versuch falsch war. Der Hash wurde über die Bytes der Datei gerechnet statt
über das, was der Browser als Skriptinhalt sieht — und die HTML-Spezifikation
verlangt, dass CRLF vor dem Zerlegen zu LF wird. Auf der Windows-Arbeitskopie
(CRLF) also falsch, im Container (LF) richtig: ein Defekt, der genau dort
auftritt, wo entwickelt wird, und dort verschwindet, wo geprüft wird. Deshalb
steht hier keine Prüfung „der Hash ist der, den die Funktion rechnet" — das
prüft nichts —, sondern zwei, die es nicht sind:

* **Zeilenenden-Invarianz**: dieselbe Datei, einmal mit CRLF und einmal mit
  LF gespeichert, muss denselben Hash ergeben. Diese Prüfung wurde einmal
  gegen den kaputten Stand gefahren und war rot.
* **Ein Vergleichswert von außen**: der erwartete Hash unten stammt aus einem
  echten HTML-Parser (jsdom, `document.querySelector('script').textContent`),
  nicht aus dieser Sprache. Ein selbst gerechneter Erwartungswert wäre die
  Behauptung, die er beweisen soll.

**Die Startprüfungen** sind Entscheidungen, die aus einer Warnung ein Nein
gemacht haben. Geprüft wird deshalb in BEIDE Richtungen: dass der Riegel
zuschnappt, und dass er die drei erlaubten Fälle durchlässt (lokal, echter
Login, ausdrückliche Ausnahme). Ein Riegel, der auch den Normalfall greift,
wird beim ersten Fehlalarm entfernt.
"""
from __future__ import annotations

import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app
from app.security import _as_browser_reads_it, build_csp, inline_script_hashes
from app.startup_checks import (InsecureStartup, check_auth_mode,
                                check_session_secret, production_signals)

# `with TestClient(app)` führe den Lifespan aus — siehe CLAUDE.md. Hier ist der
# Client nur eine Hülle um die Middleware-Kette.
client = TestClient(app)


# --------------------------------------------------------------------------- #
#  Kopfzeilen
# --------------------------------------------------------------------------- #
def test_security_headers_on_api_response():
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "same-origin"
    assert "geolocation=(self)" in r.headers["permissions-policy"]
    assert "camera=()" in r.headers["permissions-policy"]


def test_csp_locks_down_the_dangerous_directives():
    csp = client.get("/health").headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp
    # Der ganze Zweck der Hash-Fassung: kein 'unsafe-inline' bei script-src.
    script_src = [p for p in csp.split(";") if p.strip().startswith("script-src")][0]
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    # Was Daten SENDEN könnte, bleibt zu Hause.
    assert "connect-src 'self'" in csp


def test_docs_are_exempt_and_say_so():
    """Swagger lädt sich selbst von einem CDN — unter der CSP wäre /docs weiß.

    Die Ausnahme ist eine Entscheidung, kein Versehen; ohne diesen Test wandert
    sie beim nächsten Umbau entweder weg (weiße Seite) oder auf alles.
    """
    assert "content-security-policy" not in client.get("/docs").headers
    # …und die Ausnahme gilt NUR dort: die übrigen Kopfzeilen stehen weiterhin.
    assert client.get("/docs").headers["x-content-type-options"] == "nosniff"


def test_hsts_only_over_tls(monkeypatch):
    from app.security import SecurityHeadersMiddleware

    monkeypatch.setattr(settings, "public_base_url", "http://127.0.0.1:8000")
    assert not SecurityHeadersMiddleware(app).hsts
    monkeypatch.setattr(settings, "public_base_url", "https://life.example.org")
    hsts = SecurityHeadersMiddleware(app).hsts
    assert "max-age=31536000" in hsts
    # Nachbarn auf derselben Domain gehen dieses Projekt nichts an.
    assert "includeSubDomains" not in hsts
    assert "preload" not in hsts


# --------------------------------------------------------------------------- #
#  Die CSP-Hashes — die Gruppe, die es gibt, weil hier ein Fehler stand
# --------------------------------------------------------------------------- #
FIXTURE = b"<!doctype html><html><head><script>\r\nvar a = 1;\r\n</script></head></html>"
# Unabhängig gerechnet: jsdom, textContent des <script>, SHA-256, base64.
JSDOM_REFERENCE = "'sha256-UXNer4npOCf/F4eCtHkKG99a5wMJMyYh4BeQWH3QeYQ='"


def _hashes_of(raw: bytes, tmp_path, monkeypatch) -> list[str]:
    (tmp_path / "index.html").write_bytes(raw)
    monkeypatch.setattr(settings, "frontend_dir", tmp_path)
    return inline_script_hashes()


def test_hash_matches_a_real_html_parser(tmp_path, monkeypatch):
    assert _hashes_of(FIXTURE, tmp_path, monkeypatch) == [JSDOM_REFERENCE]


def test_hash_is_the_same_for_crlf_and_lf(tmp_path, monkeypatch):
    """Die Prüfung, die gegen den kaputten Stand rot war."""
    crlf = _hashes_of(FIXTURE, tmp_path, monkeypatch)
    lf = _hashes_of(FIXTURE.replace(b"\r\n", b"\n"), tmp_path, monkeypatch)
    assert crlf == lf


def test_normalisation_covers_a_lone_cr():
    assert _as_browser_reads_it(b"a\rb\r\nc") == b"a\nb\nc"


def test_scripts_with_src_get_no_hash(tmp_path, monkeypatch):
    """Eine Datei mit `src` hat keinen Inhalt zu erlauben — `'self'` deckt sie.

    Die Gegenrichtung zählt: wer hier versehentlich mitzählt, schreibt einen
    Hash über einen leeren String in die Kopfzeile und merkt nichts davon.
    """
    raw = b"<script src='vendor/leaflet.js'></script><script>var b = 2;</script>"
    assert len(_hashes_of(raw, tmp_path, monkeypatch)) == 1


def test_no_frontend_means_no_hashes_not_unsafe_inline(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frontend_dir", tmp_path / "gibtsnicht")
    assert inline_script_hashes() == []
    assert "'unsafe-inline'" not in [p for p in build_csp([]).split(";")
                                     if p.strip().startswith("script-src")][0]


def test_shipped_index_has_a_hash_for_every_inline_block():
    """Und die echte Datei: so viele Hashes wie Inline-Blöcke, keiner leer."""
    raw = (settings.frontend_dir / "index.html").read_bytes()
    blocks = raw.count(b"<script>")
    hashes = inline_script_hashes()
    assert blocks > 0 and len(hashes) == blocks
    empty = base64.b64encode(hashlib.sha256(b"").digest()).decode()
    assert all(empty not in h for h in hashes)


# --------------------------------------------------------------------------- #
#  Die Startprüfungen
# --------------------------------------------------------------------------- #
def _cfg(**kw) -> Settings:
    base = dict(auth_mode="dev", public_base_url="http://127.0.0.1:8000",
                oidc_issuer="", oidc_client_id="", dev_auth_allow_public=False,
                session_secret="dev-secret-change-me")
    base.update(kw)
    return Settings(**base)


def test_dev_mode_stays_allowed_on_localhost():
    """Der Normalfall. Ein Riegel, der ihn greift, wird zu Recht entfernt."""
    check_auth_mode(_cfg())
    check_auth_mode(_cfg(public_base_url="http://localhost:8000"))
    assert production_signals(_cfg()) == []


@pytest.mark.parametrize("kw", [
    {"public_base_url": "https://life.example.org"},
    {"oidc_issuer": "https://id.example.org"},
    {"oidc_client_id": "life-dash"},
])
def test_dev_mode_refuses_to_start_when_it_looks_public(kw):
    with pytest.raises(InsecureStartup) as err:
        check_auth_mode(_cfg(**kw))
    # Die Meldung muss den Ausweg nennen, nicht nur das Nein.
    assert "AUTH_MODE=local" in str(err.value)
    assert "DEV_AUTH_ALLOW_PUBLIC" in str(err.value)


def test_the_exception_is_honoured_and_stays_loud(caplog):
    with caplog.at_level("WARNING"):
        check_auth_mode(_cfg(public_base_url="https://demo.example.org",
                             dev_auth_allow_public=True))
    assert "KEINEN LOGIN" in caplog.text


def test_real_login_refuses_the_published_default_secret():
    for mode in ("local", "oidc"):
        with pytest.raises(InsecureStartup):
            check_session_secret(_cfg(auth_mode=mode))
    # Ein eigenes Secret geht durch — und der dev-Modus braucht gar keins.
    check_session_secret(_cfg(auth_mode="local", session_secret="x" * 40))
    check_session_secret(_cfg())


# --------------------------------------------------------------------------- #
#  Keine Geheimnisse im Log
# --------------------------------------------------------------------------- #
def test_redaction_covers_keys_this_process_does_not_know(monkeypatch):
    """Der Immich-Schlüssel steht je Nutzer in der Datenbank.

    Ein Filter, der nur die Werte aus der Konfiguration kennt, hätte genau den
    verfehlt — und der ist der einzige, der pro Nutzer verschieden ist.
    """
    from app.security import redact

    line = "Abruf: https://geo.example.org/search?key=pk.abcdef123456&q=Detmold"
    assert "pk.abcdef123456" not in redact(line)
    assert "q=Detmold" in redact(line)          # nur das Geheimnis, nicht die Zeile
    assert "sk-supergeheim" not in redact("Authorization: Bearer sk-supergeheim12345")


def test_redaction_covers_configured_values(monkeypatch):
    from app.security import redact

    monkeypatch.setattr(settings, "geocoder_api_key", "pk.ein-langer-schluessel")
    assert "pk.ein-langer-schluessel" not in redact("Geocoder pk.ein-langer-schluessel läuft")


def test_short_placeholder_keys_are_left_alone(monkeypatch):
    """`OPENAI_API_KEY=not-needed` ist kein Geheimnis.

    Die Gegenrichtung: ein Filter, der alles schwärzt, macht das Log unlesbar
    und wird beim ersten Ärger abgeschaltet.
    """
    from app.security import redact

    monkeypatch.setattr(settings, "openai_api_key", "not-needed")
    assert redact("Anbieter antwortet: not-needed") == "Anbieter antwortet: not-needed"


def test_the_filter_hangs_on_the_handlers_not_the_logger():
    """Die Falle, an der die erste Fassung vorbeigelaufen wäre.

    Python wendet bei der Weitergabe nach oben nur die Filter des
    URSPRÜNGLICHEN Loggers an. Ein Filter am Logger `lifedash` hätte für jedes
    Kind — also für praktisch jede Meldung dieser Anwendung — nichts getan.
    Geprüft wird deshalb am Kind-Logger und am Ringpuffer, der die Zeilen in
    die Verwaltung stellt.
    """
    import logging

    from app.logbuffer import ring

    logging.getLogger("lifedash.geocode").warning(
        "Abruf https://geo.example.org/s?api_key=abcdef1234567890 fehlgeschlagen")
    last = ring.buffer[-1]["message"]
    assert "abcdef1234567890" not in last
    assert "***" in last


# --------------------------------------------------------------------------- #
#  Die Rohansicht gibt keine Geheimnisse heraus — und nimmt keine an
# --------------------------------------------------------------------------- #
def test_raw_view_redacts_hash_and_immich_key():
    from app.routers.admin import redact_row

    row = {"id": "u1", "email": "a@b.c", "password_hash": "$2b$12$echterhash",
           "settings": {"lang": "de", "immich": {"url": "http://i", "api_key": "geheim"}}}
    out = redact_row("users", row)
    assert out["password_hash"] == "***"
    assert "geheim" not in out["settings"]
    # Was KEIN Geheimnis ist, bleibt lesbar — sonst ist die Ansicht wertlos.
    assert out["email"] == "a@b.c"
    assert '"lang": "de"' in out["settings"]
    assert "http://i" in out["settings"]
    # Und das Original wurde nicht angefasst: es hängt an einem ORM-Objekt.
    assert row["settings"]["immich"]["api_key"] == "geheim"


def test_raw_view_refuses_to_write_them_too():
    """Nur zu schwärzen wäre die halbe Antwort.

    Wer einen Passwort-Hash nicht LESEN, ihn aber SETZEN darf, übernimmt jedes
    Konto der Instanz mit einem Hash, den er selbst kennt.
    """
    from fastapi import HTTPException

    from app.routers.admin import reject_secret_writes

    for cols in ({"password_hash"}, {"settings"}, {"email", "password_hash"}):
        with pytest.raises(HTTPException):
            reject_secret_writes("users", cols)
    reject_secret_writes("users", {"email", "role"})      # der Normalfall bleibt
    reject_secret_writes("events", {"title", "settings"})  # nur für `users` gesperrt


def test_raw_text_has_an_upper_bound():
    from pydantic import ValidationError

    from app.schemas import FragmentCreate

    FragmentCreate(raw_text="x" * 20_000)
    with pytest.raises(ValidationError):
        FragmentCreate(raw_text="x" * 20_001)
