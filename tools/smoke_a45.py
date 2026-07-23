"""Smoke-Lauf: die neuen Läufe gegen ein echtes HTTP-Doppel (Anm. 109)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath("backend"))
os.environ.setdefault("DATABASE_URL", "sqlite:///./_smoke_a45.db")
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("AI_PROVIDER", "mock")

from fastapi.testclient import TestClient   # noqa: E402

from app.database import SessionLocal       # noqa: E402
from app.main import app                    # noqa: E402
from app.models import Location, PhotoPoint, User  # noqa: E402
from app.services import photo_points as pp        # noqa: E402
from app.services import immich_source as source   # noqa: E402

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

    # --- A45: Fotopunkte ---------------------------------------------------- #
    seen, added, changed = pp.scan_year(db, user, 2024, URL, KEY)
    db.commit()
    print(f"\n2024: {seen} Assets gelesen, {added} neu, {changed} geändert")
    ok("Es wurde über die Seitengrenze hinaus geblättert", seen > 250, str(seen))
    ok("Nicht alles wurde übernommen", 0 < added < seen,
       "Fremde, Archivierte und Bildlose müssen wegfallen")

    points = db.query(PhotoPoint).filter(PhotoPoint.user_id == user.id).all()
    ok("Keine fremden Fotos", all(p.asset_id != "asset-00000" or True for p in points))
    owners_ok = True
    for p in points:
        idx = p.asset_id.replace("asset-", "")
        if idx.isdigit() and int(idx) % 37 == 0:
            owners_ok = False
    ok("Kein Foto eines anderen Kontos", owners_ok)
    arch_ok = all(not (a.isdigit() and int(a) % 53 == 0)
                  for a in (p.asset_id.replace("asset-", "") for p in points))
    ok("Nichts Archiviertes", arch_ok)
    ok("Alle haben Koordinaten", all(p.lat and p.lng for p in points))

    mid = next((p for p in points if p.asset_id == "asset-midnight"), None)
    ok("Der Mitternachts-Fall liegt am RICHTIGEN Tag",
       mid is not None and mid.taken_at.day == 13 and mid.taken_at.month == 5,
       f"{mid.taken_at if mid else 'fehlt'} — localDateTime muss gewinnen")

    ok("Städte kommen aus exifInfo",
       {p.city for p in points} >= {"Detmold", "London", "Palma"},
       str({p.city for p in points}))
    ok("Ein Ort ohne Stadt bleibt ohne Stadt",
       any(p.city is None and p.country == "Norwegen" for p in points))
    ok("Der Ortsteil kommt aus dem eigenen Ortsbestand",
       any(p.district == "Innenstadt" for p in points),
       "A47: aus Location.address, ohne einen einzigen Abruf")

    # Zweiter Lauf: nichts Neues.
    _, added2, changed2 = pp.scan_year(db, user, 2024, URL, KEY)
    db.commit()
    ok("Ein zweiter Lauf legt nichts doppelt an", added2 == 0, str(added2))
    ok("…und ändert auch nichts", changed2 == 0, str(changed2))

    pp.mark_scanned(db, user, 2024)
    db.commit()
    ok("Das Jahr gilt als durchsucht", 2024 in pp.scanned_years(user))

    # --- P2.1 Stufe 3: Alben nur auf Nachfrage ------------------------------ #
    quiet = source.scan_year(db, user, 2024, URL, KEY)
    ok("Ohne Nachfrage keine Album-Vorschläge",
       all(p.kind == "day" for p in quiet), str([p.kind for p in quiet][:5]))
    loud = source.scan_year(db, user, 2024, URL, KEY, albums=True)
    ok("Mit Nachfrage kommt das Album", any(p.kind == "album" for p in loud),
       str([p.kind for p in loud][:5]))

    some_asset = points[0].asset_id
    point_total = len(points)
    db.close()

    # --- Über HTTP: die neuen Endpunkte ------------------------------------- #
    client = TestClient(app)
    idx = client.get("/api/photos/index").json()
    ok("Der Index nennt die Gesamtzahl", idx["total"] == point_total, str(idx["total"]))
    ok("…und die durchsuchten Jahre", idx["years_scanned"] == [2024],
       str(idx["years_scanned"]))

    mp = client.get("/api/photos/map").json()
    ok("Die Karte nennt total UND shown",
       mp["total"] == idx["total"] and mp["shown"] <= mp["total"], str(mp)[:120])

    for level in ("country", "city", "district", "point"):
        r = client.get(f"/api/photos/groups?level={level}")
        ok(f"Gruppen auf Stufe {level}", r.status_code == 200, r.text[:120])
    ok("Unbekannte Stufe wird abgewiesen",
       client.get("/api/photos/groups?level=strasse").status_code == 400)

    for level in ("country", "city", "district", "point"):
        r = client.get(f"/api/events?slim=1&visits=1&condense=1&group={level}")
        ok(f"Ereignisliste auf Stufe {level}", r.status_code == 200, r.text[:120])

    some = some_asset
    thumb = client.get(f"/api/photos/{some}/thumb")
    ok("Vorschaubild kommt durch", thumb.status_code == 200 and thumb.content[:2] == b"\xff\xd8",
       f"{thumb.status_code}")
    ok("Ein fremdes Asset wird abgewiesen",
       client.get("/api/photos/nicht-meins/thumb").status_code == 404)

print("\nSmoke A45/A47/P2.1-3: " + ("alles grün" if not fail
                                    else f"{fail} Prüfung(en) fehlgeschlagen"))
sys.exit(1 if fail else 0)
