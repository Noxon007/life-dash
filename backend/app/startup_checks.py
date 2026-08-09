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


def check_session_secret(s: Settings) -> None:
    """Das Standard-Secret signiert keine echten Sitzungen.

    Wer es kennt — und es steht in `.env.example` — fälscht eine fremde Sitzung.
    Anders als beim dev-Modus ist hier ein Abbruch die einzig richtige Antwort
    und war es immer: es gibt keinen Anwendungsfall, in dem ein echter Login mit
    einem öffentlich bekannten Signaturschlüssel gewollt ist.
    """
    if s.auth_mode in ("local", "oidc") and s.session_secret == "dev-secret-change-me":
        raise InsecureStartup(
            "SESSION_SECRET ist noch der Standardwert aus .env.example, und der "
            f"steht öffentlich im Repository. Bei AUTH_MODE={s.auth_mode} signiert "
            "er die Sitzungs-Cookies — wer ihn kennt, meldet sich als beliebiger "
            "Nutzer an. Einen eigenen erzeugen:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(48))\"")


def run_startup_checks(s: Settings) -> None:
    check_auth_mode(s)
    check_session_secret(s)
