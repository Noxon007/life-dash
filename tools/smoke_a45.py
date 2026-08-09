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
from collections import Counter

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
# **Ohne den Demo-Bestand** (Anmerkung 206). Seit R1a legt der dev-Modus beim
# Start ein erfundenes Leben an — 8.500 Ereignisse, die dieser Lauf nicht
# gebeten hat. Zwei seiner Prüfungen wurden davon still falsch: „die Bilder
# hängen am Tag" zählte die Tagesfotos des Demo-Bestands mit, und „jedes Foto
# bringt seine Asset-Kennung mit" fiel um, weil die gedeckelte Kartenauswahl
# zwischen achttausend Demo-Zeilen keinen einzigen Fotopunkt mehr erwischte.
# Dieselbe Falle wie bei `_measure_api.py` (Anmerkung 204): das Messgerät maß
# einen Bestand, den es nicht gibt.
os.environ.setdefault("SEED_DEMO", "false")

from fastapi.testclient import TestClient   # noqa: E402

from app.database import SessionLocal       # noqa: E402
from app.main import app                    # noqa: E402
from app.models import (ConfirmState, Event, Location, MediaRef,  # noqa: E402
                        Source as SourceEnum, User, UserRole)
from app.services import immich as api             # noqa: E402
from app.services import immich_link as link       # noqa: E402
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
    if user is None:
        # Ohne Demo-Bestand legt niemand ein Konto an, bevor die erste Anfrage
        # kommt — dieser Lauf arbeitet aber zuerst direkt an der Datenbank.
        #
        # **Genau das Konto des dev-Modus** (`auth.py`: `sub="dev-user"`), und
        # das ist kein Detail: die zweite Hälfte dieses Laufs geht über HTTP,
        # und die meldet sich als dev-Nutzer an. Ein eigenes Konto hier hieße,
        # dass die Endpunkte in einen leeren Bestand schauen — fünf Prüfungen
        # wären rot, und zwar mit „0" statt mit einem Hinweis auf die Ursache.
        user = User(oidc_subject="dev-user", email="dev@localhost",
                    display_name="Dev-User", role=UserRole.admin)
        db.add(user)
        db.commit()
    user.settings = {"immich": {"url": URL, "api_key": KEY}}
    # Ein eigener Ort mit Adress-Bausteinen — daraus soll A47 den Ortsteil
    # der Fotos in seiner Nähe ableiten.
    db.add(Location(user_id=user.id, name="Kaiserstr.", lat=51.9355, lng=8.8791,
                    city="Detmold", country="Deutschland",
                    address={"road": "Kaiserstr.", "suburb": "Innenstadt",
                             "city": "Detmold", "country": "Deutschland"}))
    db.commit()

    # --- Anmerkung 139/206: ein Foto, ein bestätigtes Ereignis -------------- #
    # Seit Anmerkung 206 ist der MONAT die Einheit, und EIN Griff liefert
    # beides: Ereignisse aus verorteten Fotos UND die Tagesleisten. Genau das
    # gehört gegen das HTTP-Doppel geprüft und nicht nur in den Unit-Test —
    # Blättern über die Seitengrenze erreicht der prinzipiell nicht.
    my_id = api.own_user_id(URL, KEY)
    known = pp.known_slots(db, user.id)
    districts = pp.district_index(db, user.id)
    link_seen = link.linked_asset_ids(db, user.id)
    taken = link.days_with_media(db, user.id)
    seen = created = strips = 0
    for _m in range(1, 13):
        report: dict = {}
        _c, _n = pp.scan_month(db, user, f"2024-{_m:02d}", URL, KEY, my_id,
                               known=known, districts=districts,
                               seen=link_seen, taken=taken, report=report)
        db.commit()
        seen += report.get("seen", 0)
        created += _c
        strips += _n
    print(f"\n2024: {seen} Assets gelesen, {created} Ereignisse angelegt, "
          f"{strips} Bilder an ihren Tagen")
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

    # **Die Tagesleisten aus demselben Griff** (Anmerkung 206). Bis dahin
    # hingen sie an einem ZWEITEN Lauf, der jeden Tag einzeln nachfragte — und
    # ein Tag mit vierzehn Foto-Ereignissen stand ohne ein Bild daneben, wenn
    # der nie dort ankam.
    ok("Es sind Tagesleisten entstanden", strips > 0, str(strips))
    strip_rows = (db.query(MediaRef)
                  .filter(MediaRef.user_id == user.id,
                          MediaRef.provider == "immich",
                          MediaRef.event_id.is_(None)).all())
    ok("…und sie hängen am TAG, nicht am Ereignis",
       len(strip_rows) == strips, f"{len(strip_rows)} Zeilen, {strips} gemeldet")
    ok("…höchstens zwölf je Tag",
       max(Counter(m.captured_at.date() for m in strip_rows).values()) <= 12,
       "die Deckelung gehört in die Datenbank, nicht erst in die Anzeige")
    # Ein Foto OHNE Koordinaten kann nie ein Ereignis werden — an seinen Tag
    # gehört es trotzdem. Sonst wäre die Leiste nur eine zweite Ansicht der
    # Ereignisse statt einer Aussage über den Tag, und genau das war die
    # Zusage aus der Rückmeldung („auch wenn dort noch kein Ereignis ist").
    ok("Auch Fotos ohne Koordinaten hängen an ihrem Tag",
       len({m.external_id for m in strip_rows} - assets) > 0,
       "in der Leiste stehen nur Bilder, die ohnehin Ereignisse sind")

    # Zweiter Lauf: nichts Neues — weder Ereignisse noch doppelte Leisten.
    c2 = n2 = 0
    for m in range(1, 13):
        c, n = pp.scan_month(db, user, f"2024-{m:02d}", URL, KEY, my_id,
                             known=known, districts=districts,
                             seen=link_seen, taken=taken)
        db.commit()
        c2 += c
        n2 += n
    ok("Ein zweiter Lauf legt keine Ereignisse an", c2 == 0, str(c2))
    ok("…und keine zweite Leiste", n2 == 0, str(n2))

    # Die Marke ist die FOTOZAHL je Monat, nicht ein Häkchen — nur so sind
    # „nachgesehen, nichts da" und „nie nachgesehen" unterscheidbar.
    link.mark_month(user, "2024-05", 61)
    db.commit()
    ok("Der Monat gilt als durchsucht", link.scanned_months(user).get("2024-05") == 61)
    ok("…und eine geänderte Fotozahl macht ihn wieder auf",
       link.open_months(user, {"2024-05": 62}) == ["2024-05"])

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
    # **Die Fotopunkte stehen NICHT in `events`**, sondern kompakt daneben
    # (`_photo_block`: [lat, lng, Zeit, Asset, Ortsindex, Kategorieindex]) —
    # die Ereignis-Kennung geht bewusst nicht mit, sie wäre der größte
    # Einzelposten für etwas, das die Karte nicht benutzt. Bis Anmerkung 206
    # fragte dieser Wächter hier `e.get("photo")` in `events` ab: eine Prüfung
    # gegen eine Antwortform, die es nicht mehr gibt, und die nur deshalb nie
    # rot wurde, weil daneben `any(...)` über eine leere Liste stand.
    pts = mp["photos"]["points"]
    ok("Die Fotopunkte kommen kompakt mit", len(pts) > 0, str(mp["photos"])[:120])
    ok("…und jeder bringt seine Asset-Kennung mit",
       all(p[3] for p in pts),
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
