"""Wächter: jeder Abfrageparameter, den die Oberfläche schickt, muss es geben.

Anmerkung 113. „An diesem Tag" bekam in 0.38.0 einen Schalter für importierte
Besuche. Der Endpunkt kennt den Parameter seit F16 und heißt `include_imported`;
die Oberfläche schickte `include_visits`. FastAPI wirft unbekannte
Abfrageparameter **still** weg — der Haken ließ sich setzen, merkte sich seinen
Zustand über Neustarts hinweg und bewirkte nichts. Kein Fehler, kein Log, keine
Rückmeldung: der teuerste Defekt dieses Projekts ist wieder einmal Stille.

Der vorhandene Test rief `on_this_day(..., include_imported=True)` als Funktion
auf und war grün — er prüfte die Regel, aber nicht die **Naht**. Zwischen
`index.html` und `routers/` steht kein Compiler; hier steht er.

Bewusst grob: geprüft wird, ob ein Name irgendwo in der API als
Abfrageparameter vorkommt — nicht, ob er zu genau diesem Pfad gehört. Ein
Tippfehler und eine Umbenennung fallen damit auf, ohne dass der Wächter jede
dynamisch zusammengebaute Adresse verstehen muss (`/api/events?${q}`).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.main import app

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

# Namen, die in der Nähe eines `/api/`-Aufrufs stehen, aber keine sind:
# fremde Adressen (Kartenkacheln) und Immichs eigene Bildgrößen.
_NOT_OURS = {"size", "z", "x", "y", "s", "lang", "utm_source"}


def _api_query_names() -> set[str]:
    """Alle Abfrageparameter, die das Backend laut OpenAPI kennt."""
    names: set[str] = set()
    for path in app.openapi()["paths"].values():
        for op in path.values():
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters") or []:
                if param.get("in") == "query":
                    names.add(param["name"])
    return names


def _frontend_query_names() -> set[dict]:
    """Was die Oberfläche in der Nähe eines `/api/`-Pfades als `?name=` schickt.

    Das Fenster ist Absicht: die Adresse wird nicht immer am Stück geschrieben.
    `'/api/events/on-this-day' + (otdVisits ? '?include_imported=1' : '')` ist
    genau der Fall, an dem sich dieser Wächter beweist.
    """
    text = FRONTEND.read_text(encoding="utf-8")
    found: set[str] = set()
    for hit in re.finditer(r"/api/", text):
        window = text[hit.start():hit.start() + 300]
        # Beim nächsten `/api/` ist das Fenster zu Ende — sonst erbt ein
        # Aufruf die Parameter seines Nachbarn.
        nxt = window.find("/api/", 1)
        if nxt > 0:
            window = window[:nxt]
        for name in re.findall(r"[?&]([a-z_][a-z0-9_]*)=", window):
            found.add(name)
    return found - _NOT_OURS


def test_frontend_sends_only_known_query_params():
    known = _api_query_names()
    unknown = sorted(n for n in _frontend_query_names() if n not in known)
    assert not unknown, (
        "Die Oberfläche schickt Abfrageparameter, die das Backend nicht kennt "
        f"— sie werden still verworfen: {unknown}"
    )


def test_guard_would_have_caught_include_visits(monkeypatch):
    """Gegen den kaputten Stand laufen lassen (Selbstkontrolle 0.36.0).

    Ein Wächter, der den Fehler nicht mehr sieht, den er festnageln soll, ist
    keiner. Also wird der alte Name hier künstlich hergestellt.
    """
    broken = FRONTEND.read_text(encoding="utf-8").replace(
        "'?include_imported=1'", "'?include_visits=1'")
    assert "include_visits" in broken, "Der Aufruf steht nicht mehr so da"
    monkeypatch.setattr(Path, "read_text", lambda self, **kw: broken)
    assert "include_visits" in _frontend_query_names()
    assert "include_visits" not in _api_query_names()
