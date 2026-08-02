"""Wie teuer sind die Start-Endpunkte bei realistischer Größe? Messen statt raten."""
from __future__ import annotations

import os
import random
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath("backend"))
DB = "_measure.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{DB}")
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("AI_PROVIDER", "mock")

from fastapi.testclient import TestClient   # noqa: E402

from app.database import SessionLocal       # noqa: E402
from app.main import app                    # noqa: E402
from app.models import (ConfirmState, DatePrecision, Event,  # noqa: E402
                        Location, Metric, Source, User)

N_EVENTS = int(os.environ.get("N", "20000"))
CITIES = [("Detmold", 51.93, 8.87), ("London", 51.50, -0.12), ("Palma", 39.57, 2.65),
          ("Köln", 50.94, 6.96), ("Kiel", 54.32, 10.14), ("Wien", 48.21, 16.37)]

with TestClient(app):
    db = SessionLocal()
    user = db.query(User).first()
    random.seed(7)
    locs = []
    for i, (city, lat, lng) in enumerate(CITIES):
        for k in range(40):
            loc = Location(user_id=user.id, name=f"Ort {i}-{k}, {city}", city=city,
                           lat=lat + k / 500, lng=lng + k / 500, country="X",
                           address={"city": city})
            db.add(loc)
            locs.append(loc)
    db.flush()
    base = datetime(2006, 1, 1)
    t = time.monotonic()
    for i in range(N_EVENTS):
        loc = locs[i % len(locs)]
        when = base + timedelta(hours=i * 8)
        src = Source.immich if i % 3 else Source.google_timeline
        ev = Event(user_id=user.id, title=f"Eintrag {i}", category="event",
                   date_start=when, date_end=when, date_precision=DatePrecision.exact,
                   source=src, confirmed=ConfirmState.confirmed, confirmed_by="import",
                   location=loc,
                   external_id=(f"immich:photo:a{i}" if src == Source.immich else None))
        db.add(ev)
        if i % 4 == 0:
            db.flush()
            db.add(Metric(event_id=ev.id, key="temperature_c", value=15.0,
                          source=Source.weather))
        if i % 2000 == 0:
            db.commit()
    db.commit()
    print(f"{N_EVENTS} Ereignisse angelegt in {time.monotonic() - t:.1f}s")
    db.close()

    client = TestClient(app)

    def timed(name, path, runs=3):
        # Einmal warmlaufen, dann messen — der erste Aufruf zahlt Importe mit.
        client.get(path)
        best = min((lambda: (lambda s: (client.get(path), time.monotonic() - s)[1])(
            time.monotonic()))() for _ in range(runs))
        r = client.get(path)
        size = len(r.content)
        print(f"  {name:34} {best * 1000:7.0f} ms   {size / 1024:8.1f} kB")
        return best

    print("\n=== Start-Endpunkte ===")
    timed("/api/events/index", "/api/events/index")
    timed("Zeitstrahl-Seite (300, slim)",
          "/api/events?slim=1&limit=300&offset=0&machine_proposals=0&visits=0&photos=0&group=city")
    timed("…mit Fotos + verdichtet",
          "/api/events?slim=1&limit=300&offset=0&machine_proposals=0&visits=1&photos=1&condense=1&group=city")
    timed("/api/events/on-this-day", "/api/events/on-this-day")
    timed("/api/moderation/queue", "/api/moderation/queue")
    print("\n=== Auf Klick ===")
    timed("/api/stats/overview", "/api/stats/overview")
    timed("/api/events/map (ohne Fotos)", "/api/events/map?machine_proposals=0&photos=0")
    timed("/api/events/map (mit Fotos)", "/api/events/map?machine_proposals=0")
    timed("/api/world", "/api/world")
    timed("/api/cities", "/api/cities")

# Unter Windows hält die noch offene SQLite-Verbindung die Datei; das ist kein
# Fehler des Laufs und darf ihn nicht mit einem Stack-Trace beenden — die
# Messung ist zu diesem Zeitpunkt längst ausgegeben. Beim nächsten Start wird
# sie ohnehin ersetzt (siehe oben).
try:
    os.remove(DB)
except OSError:
    print(f"\n(Hinweis: {DB} liegt noch da und wird beim nächsten Lauf ersetzt.)")
