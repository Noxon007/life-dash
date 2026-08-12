"""Anmerkung 208: Sicherheits-Kopfzeilen und die Content Security Policy.

Der fünfte und sechste offene Punkt aus Anmerkung 200 („keine Security-Header",
„vier Kartenbibliotheken vom CDN ohne CSP"). Die Bibliotheken sind seit
Anmerkung 207 im eigenen Haus — erst dadurch lässt sich hier `script-src 'self'`
schreiben, statt einen fremden Rechner ausdrücklich zu erlauben.

**Warum Hashes und nicht `'unsafe-inline'`.** Das Frontend ist EIN File mit zwei
Inline-Skriptblöcken; `'unsafe-inline'` wäre die bequeme Antwort und hätte
`script-src` fast vollständig entwertet — genau gegen die Klasse, gegen die
diese Regel existiert (eingeschleustes `<script>` in einem Ortsnamen, einem
Tagebucheintrag, einem Immich-Albumtitel). Stattdessen steht der SHA-256 der
beiden Blöcke in der Kopfzeile. Der wird beim Start aus der AUSGELIEFERTEN
Datei gerechnet, nicht beim Bauen eingetragen:

* Ein eingetragener Hash wäre eine Regel an zwei Orten — Datei hier, Zahl dort
  — und die laufen still auseinander. Beim ersten Mal, das jemand eine Zeile
  im Skriptblock ändert, wäre die Seite tot.
* Zeilenenden. Auf Windows steht `index.html` mit CRLF im Arbeitsverzeichnis,
  im Container mit LF. Ein Hash über die eine Fassung passt nicht auf die
  andere. Aus der Datei gerechnet, die dieser Prozess auch ausliefert, kann
  das nicht auseinandergehen.

**Sobald ein Hash dasteht, verwirft der Browser jeden Inline-Handler** —
`onclick=""` im Markup ist ab hier wirkungslos, und zwar lautlos. Die eine
Stelle, die das getan hat, hängt ihren Handler jetzt am Element
(`showBanner`).

**Was bewusst weich bleibt, mit Grund:**

* `style-src 'unsafe-inline'` — 363 `style="…"`-Attribute stehen im Markup.
  Die zu entfernen wäre ein Umbau ohne Sicherheitsgewinn, der diesem Angriff
  entspräche: mit CSS allein lässt sich hier nichts ausführen.
* `img-src … https:` — die Kachel-URL ist frei wählbar (eigener Kachelserver),
  und die Wikipedia-Vorschaubilder an Objekten kommen von `upload.wikimedia.org`.
  Eine Liste erlaubter Bildhosts wäre eine Liste, die der Betreiber nicht
  ändern kann, ohne den Code zu ändern.
* `/docs` und `/redoc` bleiben AUSGENOMMEN. Swagger UI lädt sich selbst von
  jsDelivr; unter dieser Regel wäre die API-Doku eine weiße Seite. Sie ist ein
  Werkzeug für Entwickler, keine Oberfläche für Daten — das hier steht
  geschrieben, statt dass jemand in einem halben Jahr rätselt, warum `/docs`
  leer ist.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import settings

log = logging.getLogger("lifedash.security")

# Die Doku-Oberflächen laden ihr eigenes Skript von einem CDN — siehe Kopf.
#
# **Anmerkung 223: genau diese Pfade, nicht alles, was so anfängt.** Geprüft
# wurde mit `startswith`, und damit war auch `/docsomething` von der Regel
# ausgenommen. Heute unerreichbar — der Static-Mount kennt den Pfad nicht —,
# aber die Bedingung sagte etwas anderes, als sie meinte, und eine Ausnahme von
# der Sicherheitsregel ist die falsche Stelle für „ungefähr".
#
# `/docs/oauth2-redirect` gibt es als Unterpfad wirklich (Swagger benutzt ihn
# beim OAuth-Fluss), deshalb bleibt der Präfix erlaubt — aber nur mit einem
# Schrägstrich dahinter.
_CSP_EXEMPT = ("/docs", "/redoc")


def _csp_exempt(path: str) -> bool:
    """Ist dieser Pfad eine der Doku-Oberflächen (oder ein Unterpfad davon)?"""
    return any(path == p or path.startswith(p + "/") for p in _CSP_EXEMPT)

_INLINE_SCRIPT = re.compile(rb"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def _as_browser_reads_it(body: bytes) -> bytes:
    """Zeilenenden so normalisieren, wie der HTML-Parser es tut.

    **Das ist die Stelle, an der diese Datei beim ersten Versuch falsch war.**
    Der Hash muss über das gerechnet werden, was der Browser als Skriptinhalt
    SIEHT, nicht über die Bytes auf der Platte. Die HTML-Spezifikation
    verlangt, dass jedes CRLF und jedes einzelne CR im Eingabestrom vor dem
    Zerlegen zu LF wird — der Skriptinhalt hat also nie ein CR, egal wie die
    Datei gespeichert ist.

    Ohne diese Zeile stimmt der Hash auf einer Windows-Arbeitskopie (CRLF)
    nicht, im Linux-Container (LF) schon. Das Ergebnis wäre die schlimmste
    Sorte Fehler, die dieses Projekt kennt: er tritt genau dort auf, wo
    entwickelt wird, verschwindet dort, wo geprüft wird, und äußert sich als
    eine Seite, die einfach nichts tut.
    """
    return body.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def inline_script_hashes() -> list[str]:
    """SHA-256 der Inline-Skriptblöcke der ausgelieferten `index.html`.

    Leere Liste, wenn kein Frontend ausgeliefert wird (reiner API-Betrieb) —
    dann gibt es auch nichts zu erlauben. **Nicht** stillschweigend auf
    `'unsafe-inline'` zurückfallen: eine CSP, die sich selbst aufweicht, wenn
    sie ihre Datei nicht findet, ist eine, die im Fehlerfall nichts tut.
    """
    index = settings.frontend_dir / "index.html"
    if not index.exists():
        return []
    raw = index.read_bytes()
    out: list[str] = []
    for body in _INLINE_SCRIPT.findall(raw):
        digest = hashlib.sha256(_as_browser_reads_it(body)).digest()
        out.append(f"'sha256-{base64.b64encode(digest).decode()}'")
    if not out:
        log.warning("index.html enthält keinen Inline-Skriptblock — die CSP "
                    "erlaubt entsprechend keinen. Ist das die richtige Datei?")
    return out


def build_csp(hashes: list[str]) -> str:
    parts = [
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        # Die moderne Hälfte von X-Frame-Options. Beide stehen da: die alte,
        # weil sie in Umgebungen greift, die die neue nicht kennen.
        "frame-ancestors 'none'",
        "form-action 'self'",
        " ".join(["script-src 'self'", *hashes]),
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https:",
        # Der Browser spricht ausschließlich mit dieser Instanz. Kacheln und
        # Wikipedia-Bilder sind `img`, nicht `connect` — sie fallen hier nicht
        # hinein, und genau das ist der Punkt: was Daten SENDEN könnte, bleibt
        # bei 'self'.
        "connect-src 'self'",
        "worker-src 'self'",
        "manifest-src 'self'",
        "font-src 'self'",
        "media-src 'self' blob:",
    ]
    return "; ".join(parts)


# --------------------------------------------------------------------------- #
#  „Keine Geheimnisse im Log" (R1d)
# --------------------------------------------------------------------------- #
# Ein Filter statt einer Durchsicht, und der Unterschied ist der ganze Punkt.
# Eine Durchsicht beantwortet „loggt der Code von heute ein Geheimnis?"; die
# Frage von morgen — jemand schreibt beim Debuggen `log.info("%s", url)` und
# lässt es stehen — beantwortet sie nicht. Und diese Instanz zeigt ihr Log in
# der Verwaltung an (A17): ein Schlüssel im Ringpuffer steht damit auf einer
# Webseite.
#
# Zwei Wege, weil es zwei Sorten Geheimnis gibt:
#  * die aus der Konfiguration (Geocoder-, KI-Schlüssel, Session-Secret) —
#    bekannte Werte, die sich als ganze Zeichenkette ersetzen lassen;
#  * die aus der DATENBANK, allen voran der Immich-Schlüssel je Nutzer. Den
#    kennt dieses Modul nicht und kann ihn nicht kennen. Deshalb zusätzlich
#    das Muster über die üblichen Parameternamen — es greift auch bei einem
#    Wert, von dem hier niemand weiß.
_SECRET_PARAM = re.compile(
    r"((?:[?&]|\b)(?:key|api_key|apikey|token|access_token|client_secret)=)[^&\s\"']+",
    re.IGNORECASE)
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE)
MASK = "***"


def _configured_secrets() -> list[str]:
    """Nur, was tatsächlich ein Geheimnis IST.

    Kurze Werte bleiben draußen: `openai_api_key` steht ohne Anbieter auf
    `not-needed`, und ein Filter, der jedes Vorkommen von „not-needed" durch
    Sternchen ersetzt, macht Logzeilen unlesbar, ohne etwas zu schützen. Das
    Standard-Session-Secret ist ebenfalls kein Geheimnis — es steht in
    `.env.example`, und der Start bricht deswegen ohnehin ab.
    """
    candidates = [settings.geocoder_api_key, settings.openai_api_key,
                  settings.openai_embed_api_key, settings.oidc_client_secret,
                  settings.session_secret]
    return sorted({v for v in candidates
                   if v and len(v) >= 12 and v != "dev-secret-change-me"},
                  key=len, reverse=True)


def redact(text: str) -> str:
    for value in _configured_secrets():
        text = text.replace(value, MASK)
    text = _SECRET_PARAM.sub(r"\1" + MASK, text)
    return _BEARER.sub(r"\1" + MASK, text)


class RedactSecretsFilter(logging.Filter):
    """Hängt am `lifedash`-Logger — und damit auch am Ringpuffer der Log-Ansicht.

    Der Filter formatiert die Meldung aus und ersetzt sie durch die
    geschwärzte Fassung; `args` fällt dabei weg, weil sie schon eingesetzt
    sind. Das kostet eine Formatierung je Zeile und ist der Grund, warum hier
    nichts Schlaueres steht: ein Filter, der nur manchmal greift, ist ein
    Filter, dessen Lücke niemand kennt.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:      # eine kaputte Formatvorlage ist nicht unser Problem
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Setzt die Kopfzeilen auf JEDE Antwort — auch auf Fehlerseiten.

    Die Hashes werden EINMAL beim Bauen der Middleware gerechnet, nicht je
    Anfrage: die Datei ändert sich im laufenden Prozess nicht, und ein Hash je
    Antwort wäre ein Dateizugriff pro Bild.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.csp = build_csp(inline_script_hashes())
        # HSTS nur, wenn diese Instanz laut Konfiguration über TLS erreichbar
        # ist. Ohne die Bedingung sperrt sich eine Instanz auf `http://` selbst
        # aus, sobald ein Browser die Kopfzeile einmal gesehen hat. Ohne
        # `includeSubDomains` und ohne `preload`: beides trifft Nachbarn auf
        # derselben Domain, die dieses Projekt nicht kennt.
        self.hsts = (settings.public_base_url.lower().startswith("https://")
                     and "max-age=31536000" or "")

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not _csp_exempt(path):
            response.headers.setdefault("Content-Security-Policy", self.csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # `strict-origin-when-cross-origin` ist der Browser-Standard und würde
        # beim Klick auf einen Wikipedia-Link die Herkunft mitschicken. Diese
        # Instanz hat einen Namen, den niemand fremdes braucht.
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # Was die Seite tatsächlich benutzt: Standort (Karte „wo bin ich?") und
        # Mikrofon (Spracheingabe). Alles andere ausdrücklich zu.
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(self), microphone=(self), camera=(), payment=(), usb=()")
        if self.hsts:
            response.headers.setdefault("Strict-Transport-Security", self.hsts)
        return response
