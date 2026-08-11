"""Die laufende App-Version — die eine Quelle der Wahrheit (A3).

Wird bei jedem Release zusammen mit CHANGELOG.md und dem Git-Tag gepflegt
(SemVer, siehe CHANGELOG-Kopf). Angezeigt im UI (Sidebar) und in /health.
"""
import os

APP_VERSION = "0.39.0"

# Womit sich diese Software bei FREMDEN Diensten meldet (Anmerkung 219).
#
# Hier und nicht bei den Aufrufern, weil es zwei gibt und sie auseinanderliefen:
# `auth.HTTP_HEADERS` baute die Zeichenkette aus `APP_VERSION`, `geocode`
# verdrahtete „life-dash/0.1" — eine Version, die es nie gab. Ausgerechnet dort
# wiegt es am schwersten: Nominatims Nutzungsbedingungen verlangen eine
# identifizierende Angabe, und wer sie nicht liefert, wird gesperrt.
#
# Genannt wird die SOFTWARE, nicht die Instanz — die Projekt-URL ist die
# Identität von Life-Dash selbst und steht deshalb fest, während die Adresse
# einer Anlage niemanden etwas angeht.
USER_AGENT = f"Life-Dash/{APP_VERSION} (+https://github.com/Noxon007/life-dash)"


def release_channel() -> str:
    """„release" nur für ein CI-Image vom passenden SemVer-Tag, sonst „dev".

    Anmerkung 86: Seit es das :main-Gleis gibt, sagt „0.32.0" allein nicht
    mehr, ob der veröffentlichte Stand läuft oder der von heute Nachmittag.
    Die CI setzt BUILD_REF auf `github.ref_name` — beim Release-Lauf also den
    Tag (`v0.32.0`), beim Testlauf den Branch (`main`). Verlangt wird
    Gleichheit mit APP_VERSION, nicht nur „sieht aus wie ein Tag": ein Image
    von `v0.31.0`, in dem versehentlich eine andere Version steht, ist kein
    Release dieser Version. Alles ohne BUILD_REF — lokal gestartet, selbst
    gebaut — ist ebenfalls „dev": das ist der ehrliche Default, denn ein
    Release ist genau das, was aus dem Tag gebaut wurde.
    """
    return "release" if os.getenv("BUILD_REF", "").lstrip("v") == APP_VERSION else "dev"


def display_version() -> str:
    """Für Menschen: „0.32.0" im Release, „0.32.0-dev" auf dem Testgleis."""
    return APP_VERSION if release_channel() == "release" else f"{APP_VERSION}-dev"
