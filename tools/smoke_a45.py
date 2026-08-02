"""Smoke-Lauf: der Foto-Lauf gegen ein echtes HTTP-Doppel (Anm. 109/139).

**Warum es diesen Lauf zusätzlich zu 550 Unit-Tests gibt.** Die Unit-Tests
ersetzen `search_assets_paged` komplett — sie prüfen, was Life-Dash mit
Assets MACHT, nie, ob es sie überhaupt bekommt. Drei Befunde von 0.37/0.39
waren für sie prinzipiell unerreichbar: das Blättern über die Seitengrenze,
`astimezone()` unter Windows vor 1970, und der Mitternachts-Fall aus
Anmerkung 111 in den echten DTOs.

Aus dem Repo-Wurzelverzeichnis starten:
    <python> tools/immich_double.py &
    <python> tools/smoke_a45.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath("backend"))
# **Immer eine frische Datenbank.** Der Lauf prüft unter anderem „ein zweiter
# Lauf findet nichts Neues" — auf einer Datei vom Vortag ist schon der ERSTE
# der zweite, und der Wächter meldet einen Fehler, den es nicht gibt. Genau so
# ist er beim Schreiben zweimal rot geworden.
_DB = "_smoke_a45.db"
if os.path.exists(_DB):
    os.remove(_DB)
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{_DB}")
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("AI_PROVIDER", "mock")

from fastapi.testclient import TestClient   # noqa: E402

from app.database import SessionLocal       # noqa: E402
from app.main import app                    # noqa: E402
from app.models import (ConfirmState, Event, Location,  # noqa: E402
                        Source as SourceEnum, User)
from app.services import photo_points as pp        # noqa: E402

URL, KEY = "http://127.0.0.1:8199", "smoke-key"
fail = 0


def ok(name, cond, detail=""):
    global fail
    print(("  ok  " if cond else "  XX  ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fail += 1


with TestClient(app):
    db = SessionLocal()
    user = db.query(User).first()
    user.settings = {"immich": {"url": URL, "api_key": KEY}}
    # Ein eigener Ort mit Adress-Bausteinen — daraus soll A47 den Ortsteil
    # der Fotos in seiner Nähe ableiten.
    db.add(Location(user_id=user.id, name="Kaiserstr.", lat=51.9355, lng=8.8791,
                    city="Detmold", country="Deutschland",
                    address={"road": "Kaiserstr.", "suburb": "Innenstadt",
                             "city": "Detmold", "country": "Deutschland"}))
    db.commit()

    # --- Anmerkung 139: ein Foto, ein bestätigtes Ereignis ------------------ #
    report: dict = {}
    props = pp.scan_year(db, user, 2024, URL, KEY, report=report)
    seen = report.get("seen", 0)
    created = pp.create_photo_events(db, user, props)
    db.commit()
    print(f"\n2024: {seen} Assets gelesen, {created} Ereignisse angelegt")
    ok("Es wurde über die Seitengrenze hinaus geblättert", seen > 250, str(seen))
    ok("Nicht alles wurde übernommen", 0 < created < seen,
       "Fremde, Archivierte und Bildlose müssen wegfallen")

    events = (db.query(Event).filter(Event.user_id == user.id,
                                     Event.source == SourceEnum.immich).all())
    ok("Jedes angelegte Foto ist ein Ereignis", len(events) == created,
       f"{len(events)} Zeilen, {created} gemeldet")
    ok("…und jedes ist direkt bestätigt, wie ein Google-Besuch",
       all(e.confirmed == ConfirmState.confirmed and e.confirmed_by == "import"
           for e in events))
    ok("…und trägt seinen Platz", all(pp.asset_of(e.external_id) for e in events))

    assets = {pp.asset_of(e.external_id) for e in events}
    owners_ok = all(not (a.replace("asset-", "").isdigit()
                         and int(a.replace("asset-", "")) % 37 == 0) for a in assets)
    ok("Kein Foto eines anderen Kontos", owners_ok)
    arch_ok = all(not (a.replace("asset-", "").isdigit()
                       and int(a.replace("asset-", "")) % 53 == 0) for a in assets)
    ok("Nichts Archiviertes", arch_ok)
    ok("Alle haben Koordinaten",
       all(e.location and e.location.lat and e.location.lng for e in events))

    mid = next((e for e in events
                if pp.asset_of(e.external_id) == "asset-midnight"), None)
    ok("Der Mitternachts-Fall liegt am RICHTIGEN Tag",
       mid is not None and mid.date_start.day == 13 and mid.date_start.month == 5,
       f"{mid.date_start if mid else 'fehlt'} — localDateTime muss gewinnen")

    cities = {e.location.city for e in events if e.location}
    ok("Städte kommen aus exifInfo", cities >= {"Detmold", "London", "Palma"},
       str(cities))
    ok("Ein Ort ohne Stadt bleibt ohne Stadt",
       any(e.location.city is None and e.location.country == "Norwegen"
           for e in events if e.location))
    ok("Der Ortsteil kommt aus dem eigenen Ortsbestand",
       any("Innenstadt" in (e.title or "") for e in events),
       "A47: aus Location.address, ohne einen einzigen Abruf")

    # **Die Ortszeilen sind entdoppelt** (Anmerkung 139): je Koordinate eine,
    # nicht je Foto und nicht je Stadt. Beide Fehler wären hier sichtbar —
    # gleich viele Orte wie Fotos, oder eine Handvoll für die ganze Bibliothek.
    photo_locs = db.query(Location).filter(Location.user_id == user.id,
                                           Location.type == "photo").count()
    ok("Ein Ort je Koordinate, nicht je Foto", photo_locs < len(events),
       f"{photo_locs} Orte für {len(events)} Fotos")
    ok("…und auch nicht je Stadt", photo_locs > len(cities),
       f"{photo_locs} Orte für {len(cities)} Städte — sonst wären 1200 Bilder "
       "aus London wieder EIN Punkt (der Bericht, der A45 ausgelöst hat)")

    # **Die Endlos-Abruf-Falle**: diese Orte dürfen NIE bei Nominatim landen.
    unmarked = db.query(Location).filter(Location.user_id == user.id,
                                         Location.type == "photo",
                                         Location.address.is_(None)).count()
    ok("Kein Foto-Ort ohne Marke", unmarked == 0,
       f"{unmarked} Orte ohne `address` — der Rückfüll-Lauf schickte für jeden "
       "einen gedrosselten Nominatim-Abruf, immer wieder")

    # Zweiter Lauf: nichts Neues.
    props2 = pp.scan_year(db, user, 2024, URL, KEY)
    ok("Ein zweiter Lauf findet nichts Neues", len(props2) == 0, str(len(props2)))

    pp.mark_scanned(db, user, 2024)
    db.commit()
    ok("Das Jahr gilt als durchsucht", 2024 in pp.scanned_years(user))

    some_asset = pp.asset_of(events[0].external_id)
    total_events = len(events)
    db.close()

    # --- Über HTTP: die Endpunkte ------------------------------------------- #
    client = TestClient(app)
    idx = client.get("/api/events/index").json()
    ok("Der Index nennt die Foto-Ereignisse", idx["photo_events"] == total_events,
       str(idx["photo_events"]))

    mp = client.get("/api/events/map").json()
    ok("Die Karte nennt total UND shown",
       mp["total"] >= total_events and mp["shown"] <= mp["total"], str(mp)[:120])
    ok("…und jedes Foto bringt seine Asset-Kennung mit",
       any(e.get("photo") for e in mp["events"]),
       "ohne sie hat die Karte kein Bild fürs Popup")

    off = client.get("/api/events/map?photos=0").json()
    ok("photos=0 lässt sie weg", off["total"] < mp["total"],
       f"{off['total']} gegen {mp['total']} — ein ausgeschalteter Schalter darf "
       "zehntausende Punkte gar nicht erst über die Leitung schicken")

    for level in ("country", "city", "district", "point"):
        r = client.get(f"/api/events?slim=1&visits=1&photos=1&condense=1&group={level}")
        ok(f"Ereignisliste auf Stufe {level}", r.status_code == 200, r.text[:120])

    thumb = client.get(f"/api/photos/{some_asset}/thumb")
    ok("Vorschaubild kommt durch",
       thumb.status_code == 200 and thumb.content[:2] == b"\xff\xd8",
       f"{thumb.status_code}")
    ok("Ein fremdes Asset wird abgewiesen",
       client.get("/api/photos/nicht-meins/thumb").status_code == 404)

    dc = client.get("/api/immich/day-clusters").json()
    ok("Der Aufräum-Lauf findet nichts anzufassen", dc["total"] == 0, str(dc))

print("\nSmoke Foto-Ereignisse (Anm. 139): " + ("alles grün" if not fail
                                                else f"{fail} Prüfung(en) fehlgeschlagen"))
sys.exit(1 if fail else 0)
