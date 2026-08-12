"""Anmerkung 208: Was beim Start NICHT gestartet werden darf.

R1(d) nennt den dev-Modus „die schärfste Kante, die dieses Projekt ausliefert".
`AUTH_MODE=dev` heißt: kein Login. Nicht „ein einfacher Login", sondern keiner —
`get_dev_user()` liefert für jede Anfrage denselben Nutzer, und dem gehört alles.
Lokal ist das genau richtig. In einer Instanz, die jemand erreichen kann, ist es
die gesamte Lebensdatenbank ohne Tür.

**Der Riegel prüft nicht, ob die Instanz erreichbar IST — das kann ein Prozess
nicht wissen.** Er prüft, ob sie danach AUSSIEHT, und zwar an den beiden
Stellen, an denen der Unfall tatsächlich passiert:

1. `PUBLIC_BASE_URL` zeigt nicht auf den eigenen Rechner. Wer das setzt, hat
   einen Reverse-Proxy davor — die Adresse existiert nur, damit jemand von
   außen sie aufruft.
2. Ein OIDC-Provider ist konfiguriert, `AUTH_MODE` steht trotzdem auf `dev`.
   Das ist die halb fertige Umstellung: Issuer und Client-ID eingetragen, den
   Modus vergessen. Hier hat der Betreiber seine Absicht bereits aufgeschrieben,
   und sie widerspricht der Einstellung.

**Warum ein Abbruch und keine Warnung.** Eine Warnung im Log ist in diesem
Projekt die dokumentierte Art, einen Fehler zu verstecken (`CLAUDE.md`: der
wiederkehrende Defekt ist nicht Kaputtheit, sondern Stille). Die alte Fassung
hat genau das getan, und die Anmerkung daneben sagte „die Härtung folgt mit R1".
Sie ist hier.

Die Ausnahme heißt `DEV_AUTH_ALLOW_PUBLIC=true` und ist ausdrücklich vorgesehen
— eine öffentliche Demo-Instanz mit `SEED_DEMO=true` ist genau das. Sie meldet
sich bei jedem Start, weil eine Ausnahme, die man einmal setzt und nie wieder
sieht, keine Ausnahme mehr ist, sondern die Einstellung.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.config import Settings

log = logging.getLogger("lifedash.startup")

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0", "host.docker.internal"}


class InsecureStartup(RuntimeError):
    """Der Start wird abgebrochen, statt eine offene Instanz hochzufahren."""


def _is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    # Ein leerer Host heißt „keine brauchbare Adresse konfiguriert" — das ist
    # kein Produktions-Anzeichen, sondern eine Lücke, und Lücken sind lokal.
    return not host or host in _LOCAL_HOSTS


def production_signals(s: Settings) -> list[str]:
    """Die Anzeichen dafür, dass diese Instanz erreichbar sein soll."""
    out: list[str] = []
    if not _is_local(s.public_base_url):
        out.append(f"PUBLIC_BASE_URL={s.public_base_url} zeigt nicht auf diesen Rechner")
    if s.oidc_issuer.strip() or s.oidc_client_id.strip():
        out.append("ein OIDC-Provider ist konfiguriert (OIDC_ISSUER/OIDC_CLIENT_ID), "
                   "AUTH_MODE steht aber auf dev")
    return out


def check_auth_mode(s: Settings) -> None:
    """Bricht ab, wenn der dev-Modus in einer produktionsförmigen Umgebung steht."""
    if s.auth_mode != "dev":
        return
    signals = production_signals(s)
    if not signals:
        return
    if s.dev_auth_allow_public:
        log.warning(
            "AUTH_MODE=dev in einer erreichbaren Umgebung — ausdrücklich erlaubt "
            "durch DEV_AUTH_ALLOW_PUBLIC=true. DIESE INSTANZ HAT KEINEN LOGIN: "
            "%s. Wer die Adresse kennt, sieht und ändert alle Daten.",
            "; ".join(signals))
        return
    raise InsecureStartup(
        "AUTH_MODE=dev bedeutet KEIN LOGIN — jede Anfrage gilt als der Nutzer, dem "
        "alle Daten gehören. Diese Instanz sieht aber danach aus, als solle sie "
        "erreichbar sein:\n  - " + "\n  - ".join(signals) + "\n\n"
        "Zu tun ist eins von dreien:\n"
        "  * AUTH_MODE=local setzen (E-Mail + Passwort, kein Identitätsanbieter nötig)\n"
        "  * AUTH_MODE=oidc setzen, wenn ein Provider konfiguriert ist\n"
        "  * DEV_AUTH_ALLOW_PUBLIC=true setzen, WENN das Absicht ist — etwa eine "
        "öffentliche Demo-Instanz mit erfundenen Daten (SEED_DEMO=true).\n"
        "Siehe docs/DEPLOY.md.")


# HS256 signiert mit SHA-256, und RFC 7518 §3.2 verlangt einen Schlüssel, der
# mindestens so lang ist wie die Ausgabe des Hashs. PyJWT 2.13 warnt seit dem
# Abhängigkeits-Sprung bei jedem kürzeren (`InsecureKeyLengthWarning`) — die
# Warnung hat diese Lücke überhaupt erst sichtbar gemacht.
_MIN_SECRET_BYTES = 32


def check_session_secret(s: Settings) -> None:
    """Der Signaturschlüssel muss geheim UND lang genug sein.

    **Diese Prüfung zählte Literale auf, und das war ihr Fehler.** Sie kannte
    genau eine verbotene Zeichenkette — `dev-secret-change-me`, den Vorgabewert
    aus `config.py`. In `.env.example` stand aber `change-me`, und **das ist
    der Wert, den ein Fremder tatsächlich bekommt**: die erste Zeile der
    README lautet `cp .env.example .env`. Neun Byte, öffentlich im
    Repository, `AUTH_MODE` steht per Vorgabe auf `local` — die App startete
    und signierte damit Sitzungs-Cookies. Genau der Angriff, gegen den
    Anmerkung 208 diese Funktion gebaut hat, nur durch die Tür daneben.

    Eine zweite verbotene Zeichenkette einzutragen hätte die Falle
    verlängert, nicht geschlossen: **eine Liste bekannter schlechter Werte ist
    immer unvollständig**, und sie steht an einem anderen Ort als der Wert, den
    sie meint. Die Länge ist die Regel, die keine Liste braucht — jeder
    öffentlich bekannte Platzhalter ist kurz, und ein echter Zufallswert ist es
    nie. Sie ist überdies die Regel, die ohnehin gilt (RFC 7518 §3.2).

    Der Vorgabewert wird weiterhin eigens genannt, aber nur für die
    BEGRÜNDUNG: „zu kurz" ist bei einem bekannten Platzhalter die schlechtere
    Auskunft als „der steht im Repository".
    """
    if s.auth_mode not in ("local", "oidc"):
        return
    secret = s.session_secret or ""
    known = secret in ("dev-secret-change-me", "change-me", "")
    if known or len(secret.encode()) < _MIN_SECRET_BYTES:
        why = ("ist ein Platzhalter aus dem Repository und damit öffentlich "
               "bekannt" if known else
               f"ist mit {len(secret.encode())} Byte zu kurz — HS256 verlangt "
               f"mindestens {_MIN_SECRET_BYTES} (RFC 7518 §3.2)")
        raise InsecureStartup(
            f"SESSION_SECRET {why}. Bei AUTH_MODE={s.auth_mode} signiert er die "
            "Sitzungs-Cookies — wer ihn erraten oder nachschlagen kann, meldet "
            "sich als beliebiger Nutzer an. Einen eigenen erzeugen:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(48))\"")


def run_startup_checks(s: Settings) -> None:
    check_auth_mode(s)
    check_session_secret(s)
