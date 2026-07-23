#!/usr/bin/env bash
# Aufrüstung 0.38.0 -> 0.39.0 an einer BESTEHENDEN Datenbank.
#
# `create_all` legt fehlende Tabellen an, `ensure_schema` fehlende Spalten —
# beides greift aber nur, wenn es auch wirklich läuft. Eine frische Datenbank
# beweist das nicht: dort entsteht ohnehin alles auf einmal. Geprüft wird
# deshalb der Weg, den jeder Bestandsnutzer geht.
set -u
PY="C:/Users/phili/miniforge3/envs/py313/python.exe"
SP="$(cd "$(dirname "$0")" && pwd)"
REPO="d:/Python/life-dash"
OLD="$SP/old38"
DB="$REPO/backend/_upgrade.db"

rm -rf "$OLD" "$DB"
cd "$REPO" || exit 1

# 1. Den Stand von 0.38.0 auschecken (Tag existiert lokal? sonst der Commit
#    vor dieser Runde) und damit eine Datenbank füllen.
# Der Stand, von dem aufgeruestet wird — als Argument, mit dem letzten
# Release-Tag als Vorgabe.
BASE="${1:-v0.38.0}"
git rev-parse "$BASE" >/dev/null 2>&1 || BASE=$(git rev-parse cf1da26^)
git worktree add -q --detach "$OLD" "$BASE" || exit 1

cd "$OLD/backend" || exit 1
DATABASE_URL="sqlite:///./_upgrade.db" AUTH_MODE=dev AI_PROVIDER=mock "$PY" - <<'PYEOF'
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import ConfirmState, Event, Location, MediaRef, Source, User

with TestClient(app):
    db = SessionLocal()
    user = db.query(User).first()
    loc = Location(user_id=user.id, name="Kaiserstr., Detmold", lat=51.93, lng=8.87,
                   city="Detmold", country="Deutschland")
    db.add(loc); db.flush()
    # Ein Besuch ueber Mitternacht, wie ihn 0.38 angelegt hat: nackter Hash.
    db.add(Event(user_id=user.id, title="Besuch: Kaiserstr., Detmold",
                 date_start=datetime(2024, 7, 1, 22, 0),
                 date_end=datetime(2024, 7, 2, 7, 0),
                 category="event", confirmed=ConfirmState.confirmed,
                 source=Source.google_timeline, location=loc,
                 external_id="alt-hash-0001"))
    db.add(MediaRef(user_id=user.id, provider="local", external_id="foto.jpg",
                    captured_at=datetime(2024, 7, 1, 12, 0)))
    db.commit()
    print("0.38er Datenbank angelegt:",
          db.query(Event).count(), "Ereignis,",
          db.query(Location).count(), "Ort,",
          db.query(MediaRef).count(), "Bild")
    db.close()
PYEOF
[ $? -ne 0 ] && { echo "XX  Die 0.38er Datenbank liess sich nicht anlegen"; exit 1; }
# Die Datei entstand im alten Arbeitsbaum — jetzt dorthin, wo der neue Stand sie oeffnet.
for f in "$OLD"/backend/_upgrade.db*; do cp "$f" "$REPO/backend/"; done

# 2. Dieselbe Datei mit dem NEUEN Stand oeffnen.
cd "$REPO/backend" || exit 1
DATABASE_URL="sqlite:///./_upgrade.db" AUTH_MODE=dev AI_PROVIDER=mock "$PY" - <<'PYEOF'
import sys
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from app.main import app
from app.database import SessionLocal, engine
from app.models import Event, Location, MediaRef, PhotoPoint

fail = 0
def ok(name, cond, detail=""):
    global fail
    print(("  ok  " if cond else "  XX  ") + name + ("" if cond else f" — {detail}"))
    if not cond: fail += 1

with TestClient(app) as client:
    insp = inspect(engine)
    ok("Die neue Tabelle ist da", "photo_points" in insp.get_table_names(),
       str(insp.get_table_names()))
    cols = {c["name"] for c in insp.get_columns("photo_points")}
    ok("…mit allen Spalten",
       cols >= {"user_id", "provider", "asset_id", "taken_at", "lat", "lng",
                "district", "city", "state", "country"}, str(cols))

    db = SessionLocal()
    mine = db.query(Event).filter(Event.external_id.like("alt-hash-0001%")).all()
    ok("Der Bestandseintrag hat die Aufruestung ueberlebt", len(mine) == 1,
       str([e.external_id for e in mine]))
    ok("Das hochgeladene Bild lebt",
       db.query(MediaRef).filter(MediaRef.external_id == "foto.jpg").count() == 1)
    loc = db.query(Location).filter(Location.name == "Kaiserstr., Detmold").first()
    ok("Ein Ort ohne Bausteine gilt als „nie nachgesehen“",
       loc is not None and loc.address is None, repr(loc.address if loc else None))
    db.close()

    idx = client.get("/api/events/index").json()
    ok("Der Index zaehlt ihn als offen", idx["locations_no_address"] >= 1, str(idx))

    prev = client.get("/api/events/visits/multiday").json()
    ok("Der Aufraeum-Lauf findet den Alt-Besuch", prev["events"] == 1, str(prev))
    ok("…und nennt die Zeilen danach", prev["rows_after"] == 2, str(prev))
    run = client.post("/api/events/visits/split").json()
    ok("Er schneidet ihn", run["created"] == 1, str(run))

    db = SessionLocal()
    rows = (db.query(Event).filter(Event.external_id.like("alt-hash-0001%"))
            .order_by(Event.date_start).all())
    ok("Danach zwei Tages-Eintraege", len(rows) == 2, str(len(rows)))
    ok("…keiner mehr ueber eine Tagesgrenze",
       all(e.date_start.date() == e.date_end.date() for e in rows))
    ok("…und der Schluessel traegt jetzt das Suffix",
       {e.external_id for e in rows} == {"alt-hash-0001#1", "alt-hash-0001#2"},
       str({e.external_id for e in rows}))
    db.close()

    for path in ("/api/photos/index", "/api/photos/map", "/api/photos/days",
                 "/api/photos/groups?level=district",
                 "/api/events?slim=1&condense=1&group=district"):
        r = client.get(path)
        ok(f"{path} antwortet", r.status_code == 200, f"{r.status_code} {r.text[:80]}")

print("\nAufruestung 0.38 -> 0.39: " + ("alles gruen" if not fail
                                        else f"{fail} Pruefung(en) fehlgeschlagen"))
sys.exit(1 if fail else 0)
PYEOF
RC=$?

cd "$REPO" && git worktree remove --force "$OLD" >/dev/null 2>&1
rm -f "$DB" "$DB"-wal "$DB"-shm
exit $RC
