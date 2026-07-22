"""Lebenszeichen für lange Läufe — ein Fortschrittsprotokoll mit Drossel.

Der wiederkehrende Defekt in diesem Projekt ist nicht Kaputtheit, sondern
Stille (Anmerkung 92): Ein Lauf über 12 000 Ereignisse schreibt eine Zeile beim
Start und eine beim Ende, und dazwischen ist ein langsamer Lauf von einem
hängenden nicht zu unterscheiden. Der Immich-Lauf hatte das als erster gelöst
(alle 10 Ereignisse eine Zeile); dieses Modul macht daraus etwas, das jeder
Lauf benutzen kann, statt das Muster fünfmal nachzubauen.

Gedrosselt wird über die ZEIT, nicht über die Anzahl: „alle 25 Einträge" ist
bei Wetter (fünf pro Sekunde) eine Flut und beim Geocoder (einer pro Sekunde)
kaum ein Lebenszeichen. Alle `every` Sekunden eine Zeile ist bei beiden
dasselbe Versprechen — solange etwas kommt, läuft es noch.

Tempo und Restzeit stehen dabei, weil sie die eigentliche Frage beantworten:
nicht „läuft es?", sondern „lohnt sich das Warten?".
"""
from __future__ import annotations

import logging
import time


def format_duration(seconds: float) -> str:
    """Grobe, lesbare Dauer — Sekunden, Minuten oder Stunden, nie alles."""
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 90 * 60:
        return f"{seconds / 60:.0f} min"
    return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d} h"


class Progress:
    """Ein sprechender Lauf: Startzeile, Lebenszeichen, Schlusszeile.

    Benutzung:
        p = Progress(log, "Wetter ergänzen", unit="Ereignisse")
        p.start(total)
        ...  p.beat(done, remaining)   # so oft wie bequem — drosselt selbst
        p.finish("1 200 angereichert")
    """

    def __init__(self, log: logging.Logger, label: str, *,
                 unit: str = "Einträge", every: float = 10.0) -> None:
        self.log = log
        self.label = label
        self.unit = unit
        self.every = every
        self.t0 = time.monotonic()
        # Der erste Fortschritt soll SOFORT sichtbar sein: er beantwortet
        # „ist überhaupt etwas losgegangen?", und darauf zehn Sekunden zu
        # warten ist genau die Stille, gegen die dieses Modul gebaut ist.
        self._last = self.t0 - every
        self._beats = 0

    # -- Ausgabe ----------------------------------------------------------- #
    def start(self, total: int | None = None, note: str = "") -> None:
        what = f"{total} {self.unit}" if total is not None else "Umfang noch offen"
        self.log.info("%s beginnt: %s%s", self.label, what,
                      f" — {note}" if note else "")

    def beat(self, done: int, remaining: int | None = None, note: str = "",
             force: bool = False) -> bool:
        """Eine Fortschrittszeile, höchstens alle `every` Sekunden.

        Gibt zurück, ob geschrieben wurde — nützlich für Aufrufer, die eine
        teure Zusatzangabe nur dann ermitteln wollen.
        """
        now = time.monotonic()
        if not force and now - self._last < self.every:
            return False
        self._last = now
        self._beats += 1
        elapsed = now - self.t0
        rate = done / elapsed if elapsed > 0 else 0.0      # je Sekunde
        head = (f"{done}/{done + remaining}" if remaining is not None else f"{done}")
        tail = []
        # Unter einer Sekunde ist jedes Tempo geraten („1000/s", weil zwei
        # Zeilen in zwei Millisekunden liefen) — dann lieber nichts behaupten.
        if elapsed >= 1.0 and rate > 0:
            tail.append(f"{rate * 60:.0f}/min" if rate < 10 else f"{rate:.0f}/s")
            if remaining:
                tail.append(f"noch ~{format_duration(remaining / rate)}")
        if note:
            tail.append(note)
        self.log.info("%s: %s %s%s", self.label, head, self.unit,
                      f" ({', '.join(tail)})" if tail else "")
        return True

    def finish(self, summary: str = "") -> None:
        elapsed = time.monotonic() - self.t0
        self.log.info("%s fertig nach %s%s", self.label,
                      format_duration(elapsed), f": {summary}" if summary else "")
