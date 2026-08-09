"""Wie teuer sind die Start-Endpunkte bei realistischer Größe? Messen statt raten.

**Zwei Bestände, zwei Fragen.** Ohne Zutun baut dieser Lauf einen künstlichen
Bestand: 20.000 Ereignisse, 20.000 Fotos, 50.000 Wege auf 240 Orten. Das ist
der LASTFALL — grob, gleichverteilt, und in jeder Dimension größer als das,
was ein Mensch in zwanzig Jahren zusammenträgt.

Mit `DEMO=1` misst derselbe Lauf stattdessen den **Demo-Bestand** (R1a): das
erfundene Leben, das die Anwendung ausliefert. Er ist in den Ereignissen
kleiner und in den ORTEN um ein Vielfaches größer (3.700 statt 240), weil
importierte Besuche je einen anlegen — und genau daran hängen die Fragen, die
Anmerkung 199 offen gelassen hat. **Ein Lastfall, der eine Dimension nicht
kennt, misst sie auch nicht.**

    <python> tools/_measure_api.py          # Lastfall
    DEMO=1 <python> tools/_measure_api.py   # Demo-Bestand

Immer aus dem Wurzelverzeichnis.

Zuletzt gemessen 2026-08-09 (SQLite, Windows) — der nächste Umbau wird daran
gemessen und nicht an einem Gefühl:

                              Demo     Lastfall
    /api/events/index          55 ms      92 ms
    Zeitstrahl-Seite (300)     43 ms      11 ms
    …mit Fotos + verdichtet    66 ms     168 ms
    /api/days/weather (alles) 1708 ms     212 ms
    /api/achievements          811 ms     203 ms
    /api/stats/overview       2326 ms     543 ms
    /api/stats/toplists       1081 ms     479 ms
    /api/events/map            176 ms     138 ms

**Der Demo-Bestand ist auf den teuren Endpunkten VIERMAL so langsam wie der
„Lastfall", obwohl er weniger als die Hälfte der Ereignisse hat.** Der Grund
steht in den Zahlen darunter: der Lastfall schreibt DREI Wetterwerte je
Wohnort-Tag, die Anwendung schreibt SIEBZEHN. Ein Lastfall, der die teuerste
Dimension um den Faktor sechs unterschätzt, beruhigt — er misst nicht.
Deshalb steht der Demo-Bestand jetzt daneben: er ist das, was ausgeliefert
wird.
"""
from __future__ import annotations

import os
import random
import sys
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.abspath("backend"))
DEMO = os.environ.get("DEMO", "").strip() not in ("", "0", "false")
DB = "_measure.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{DB}")
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("AI_PROVIDER", "mock")
# **Der Demo-Bestand darf nicht UNTER den Lastfall geraten.** Seit R1a legt der
# Start im dev-Modus von sich aus ein erfundenes Leben an — dieser Lauf baute
# seine 20.000 Ereignisse dann obendrauf und maß eine Mischung, die es nirgends
# gibt. (Bis das auffiel, brach er an der Eindeutigkeit der Wohnort-Tage ab,
# was der glückliche Fall ist: ein lautloses Messergebnis wäre teurer gewesen.)
os.environ["SEED_DEMO"] = "true" if DEMO else "false"
os.environ.setdefault("MEDIA_DIR", "./_measure_media")

from fastapi.testclient import TestClient   # noqa: E402

from app.auth import get_dev_user            # noqa: E402
from app.database import SessionLocal       # noqa: E402
from app.main import app                    # noqa: E402
from app.models import (BaselineLocation, ConfirmState,  # noqa: E402
                        DatePrecision, DayMetric, Event, Location, Metric,
                        MediaRef, Source, Track, User)

N_EVENTS = int(os.environ.get("N", "20000"))
CITIES = [("Detmold", 51.93, 8.87), ("London", 51.50, -0.12), ("Palma", 39.57, 2.65),
          ("Köln", 50.94, 6.96), ("Kiel", 54.32, 10.14), ("Wien", 48.21, 16.37)]

with TestClient(app):
    db = SessionLocal()
    # Ausdrücklich anlegen statt „den ersten nehmen": ohne Demo-Seed legt der
    # Start gar kein Konto an — der Dev-Nutzer entsteht sonst erst bei der
    # ersten Anfrage, und die kommt hier nach dem Bestand.
    user = get_dev_user(db)
    if DEMO:
        from app.models import Entity, EventEntityLink  # noqa: E402
        print("Demo-Bestand (R1a) — vom Start angelegt:")
        for model in (Event, Location, Entity, EventEntityLink, Metric,
                      DayMetric, MediaRef, Track):
            print(f"  {model.__name__:18} {db.query(model).count():>8,}")
        db.close()
    random.seed(7)
    if not DEMO:
        # Der künstliche Lastfall. Er entsteht nur, wenn nicht ohnehin
        # der Demo-Bestand gemessen wird — zwei Bestände übereinander
        # wären eine Größe, die es nirgends gibt.
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

        # Anmerkung 185: ein Wohnort VOR den Ereignissen, mit Tageswetter — der
        # Fall, für den `weather_day` seit dieser Anmerkung prüft, ob ein Tag
        # überhaupt noch einer ist, den der Wohnort füllt. Ohne diese Zeilen misst
        # der Lauf die Bedingung über einer leeren Tabelle, also nichts.
        home = Location(user_id=user.id, name="Elternhaus", city="Bad Segeberg",
                        lat=53.93, lng=10.31, country="X")
        db.add(home)
        db.flush()
        db.add(BaselineLocation(user_id=user.id, location_id=home.id,
                                date_start=date(1990, 1, 1), date_end=date(2005, 12, 31)))
        day = date(1990, 1, 1)
        n_days = 0
        while day <= date(2005, 12, 31):
            for key, value in (("temp_max_c", 18.0), ("temp_min_c", 7.0),
                               ("sunshine_h", 5.0)):
                db.add(DayMetric(user_id=user.id, day=day, key=key, value=value,
                                 source=Source.weather))
            day += timedelta(days=1)
            n_days += 1
        db.commit()
        print(f"{n_days} Wohnort-Tage mit je 3 Wetterwerten angelegt")

        # Anmerkung 189: Fotos und Wege. Ohne sie messen die beiden neuen
        # Auskünfte über leere Tabellen, also nichts.
        for i in range(20000):
            db.add(MediaRef(user_id=user.id, provider=("local" if i % 50 == 0 else "immich"),
                            external_id=f"m{i}", bytes=(2_000_000 if i % 50 == 0 else None),
                            captured_at=base + timedelta(hours=i * 4)))
            if i % 4000 == 0:
                db.commit()
        for i in range(50000):
            when = base + timedelta(minutes=i * 90)
            db.add(Track(user_id=user.id, date_start=when,
                         date_end=when + timedelta(minutes=30), points=[],
                         activity_type=("drive", "walk", "cycle", None)[i % 4],
                         distance_m=(None if i % 97 == 0 else 1500.0 + i % 40000)))
            if i % 5000 == 0:
                db.commit()
        db.commit()
        print("20.000 Fotos und 50.000 Wege angelegt")
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
    # Anmerkung 174: derselbe Endpunkt mit eingeschaltetem Schalter „Besuche
    # mitzeigen". Das ist der Fall, der gemeldet wurde — und der einzige, in
    # dem die Vorauswahl überhaupt etwas zu tun hat: ohne ihn fällt der ganze
    # importierte Bestand schon an der Quellen-Bedingung weg, und eine Messung
    # über nichts misst nichts.
    timed("…mit importierten Besuchen", "/api/events/on-this-day?include_imported=1")
    timed("/api/moderation/queue", "/api/moderation/queue")
    # Anmerkung 185: die Tagesauskunft prüft seitdem je Zeile, ob der Tag noch
    # einer ist, den der Wohnort füllt. Beide Spannen messen — die eines
    # Zeitstrahl-Fensters und die des ganzen Lebens, weil die Erfolge und die
    # Statistik ohne Fenster fragen.
    timed("/api/days/weather (ein Monat)",
          "/api/days/weather?from=2001-06-01&to=2001-06-30")
    timed("/api/days/weather (alles)",
          "/api/days/weather?from=1990-01-01&to=2026-12-31")
    print("\n=== Auf Klick ===")
    timed("/api/achievements", "/api/achievements")
    timed("/api/stats/overview", "/api/stats/overview")
    timed("/api/stats/toplists", "/api/stats/toplists")
    timed("/api/stats/tracks", "/api/stats/tracks")
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
