"""Log-Ring-Puffer (A17): hält die letzten App-Log-Zeilen im Speicher,
damit das Admin-Panel sie anzeigen kann — ohne SSH/`docker logs`.

Bewusst flüchtig (kein Persistieren, kein Datei-Zugriff): `docker logs`
bleibt die vollständige Quelle; hier geht es um den schnellen Blick,
was das System gerade tut.
"""
from __future__ import annotations

import logging
import time
from collections import deque

# Seit die Läufe je Schritt sprechen (Ortsnamen: eine Zeile je Ort), füllt ein
# einziger Lauf die alten 500 Zeilen in gut acht Minuten — und schob damit
# genau das aus dem Puffer, wofür man ihn aufmacht (Fehler von vorhin).
# 2000 Zeilen sind im Speicher ein paar hundert Kilobyte und decken einen
# kompletten Lauf ab. `docker logs` bleibt die vollständige Quelle.
CAPACITY = 2000


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = CAPACITY):
        super().__init__()
        self.buffer: deque[dict] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S",
                                    time.localtime(record.created)),
                "level": record.levelname,
                "levelno": record.levelno,
                "logger": record.name,
                "message": record.getMessage(),
            })
        except Exception:  # noqa: BLE001 — Logging darf nie die App stören
            pass


# Ein Puffer für den Prozess; wird in main.py an den "lifedash"-Logger
# gehängt (fängt via Propagation alle lifedash.*-Kinder mit).
ring = RingBufferHandler()
