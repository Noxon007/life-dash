"""Beide Löschwege müssen JEDE Tabelle mit Lebensdaten kennen — und in der
richtigen Reihenfolge.

**Warum es diesen Test gibt.** `baseline_locations` fehlte in beiden Löschwegen,
seit es die Tabelle gibt. Auffallen konnte das nirgends: SQLite erzwingt keine
Fremdschlüssel, also lief die Testsuite grün durch; auf PostgreSQL scheiterte
das `DELETE FROM locations`, die Sitzung rollte zurück — und weil jede Tabelle
ihre Zeile ins Log schreibt, BEVOR committet wird, meldete das Protokoll ein
Löschen, das nicht stattgefunden hat.

Ein Test, der nur „nach dem Wipe ist die Tabelle leer" prüft, hätte das nicht
gefunden: er hätte die vergessene Tabelle gar nicht erst abgefragt. Deshalb
prüft dieser hier gegen `Base.metadata` — also gegen ALLE Tabellen, auch die,
die es beim Schreiben des Tests noch nicht gab. Eine neue Tabelle mit
Nutzerdaten lässt ihn rot werden, bis jemand entschieden hat, ob sie gelöscht
oder behalten wird.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.database import Base
from app.models import (BaselineLocation, DayMetric, Location, Source, User,
                        UserRole)
from app.routers.data import export_data, import_data, wipe_my_data
from app.wipe import WIPE_KEEPS, WIPE_ORDER, is_delete_word

WIPE_TABLES = [table for _m, table, _s in WIPE_ORDER]


@pytest.fixture
def other(db) -> User:
    """Ein zweites Konto — Löschen ist nur richtig, wenn es genau eines trifft."""
    u = User(oidc_subject="other-wipe", email="ow@example.org", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


# --------------------------------------------------------------------------- #
# Vollständigkeit und Reihenfolge — strukturell, nicht nach Beispiel
# --------------------------------------------------------------------------- #
def test_every_table_is_either_wiped_or_deliberately_kept():
    """Keine Tabelle darf durchs Raster fallen. Wer eine neue anlegt, trifft
    hier die Entscheidung — statt sie später auf PostgreSQL zu erfahren."""
    known = set(WIPE_TABLES) | set(WIPE_KEEPS)
    forgotten = sorted(set(Base.metadata.tables) - known)

    assert not forgotten, (
        f"Diese Tabellen kennt kein Löschweg: {forgotten}. Entweder in "
        "app.wipe.WIPE_ORDER eintragen (mit Reihenfolge!) oder in WIPE_KEEPS "
        "mit Begründung, warum sie stehen bleibt.")


def test_no_table_is_in_both_lists():
    assert not (set(WIPE_TABLES) & set(WIPE_KEEPS))


def test_the_order_respects_every_foreign_key():
    """Kinder vor Eltern — sonst schlägt genau ein `DELETE` fehl, und zwar
    erst auf PostgreSQL."""
    rank = {table: i for i, table in enumerate(WIPE_TABLES)}
    for table in WIPE_TABLES:
        for fk in Base.metadata.tables[table].foreign_keys:
            parent = fk.column.table.name
            if parent == table or parent not in rank:
                continue        # Selbstbezug / Tabelle bleibt stehen (users)
            assert rank[table] < rank[parent], (
                f"{table} zeigt auf {parent}, wird aber später gelöscht — "
                "auf PostgreSQL bricht das den ganzen Lauf ab.")


def test_wipe_keeps_carry_a_reason():
    """Eine Tabelle stehen zu lassen ist eine Entscheidung, kein Versehen."""
    for table, reason in WIPE_KEEPS.items():
        assert table in Base.metadata.tables, f"{table} gibt es gar nicht mehr"
        assert len(reason) > 20, f"{table}: Begründung fehlt"


# --------------------------------------------------------------------------- #
# Und derselbe Satz einmal ausgeführt
# --------------------------------------------------------------------------- #
def _baseline(db, user) -> BaselineLocation:
    loc = Location(user_id=user.id, name="Elternhaus", lat=51.9, lng=8.9)
    db.add(loc)
    db.flush()
    b = BaselineLocation(user_id=user.id, location_id=loc.id, label="Kindheit",
                         date_start=date(1995, 3, 1), date_end=date(2007, 8, 31))
    db.add(b)
    db.add(DayMetric(user_id=user.id, day=date(2000, 5, 1),
                     key="temperature_c", value=17.5, source=Source.weather))
    db.commit()
    return b


def test_wipe_removes_the_baseline_and_its_day_values(db, user):
    """Der Fall, der auf PostgreSQL 500 warf: der Grundort zeigt auf einen Ort,
    und der Ort sollte gelöscht werden."""
    _baseline(db, user)

    result = wipe_my_data(confirm="LÖSCHEN", db=db, user=user)

    assert db.query(BaselineLocation).count() == 0
    assert db.query(DayMetric).count() == 0
    assert db.query(Location).count() == 0
    assert result["deleted"]["baseline_locations"] == 1
    assert result["deleted"]["day_metrics"] == 1


def test_wipe_leaves_the_other_accounts_baseline(db, user, other):
    _baseline(db, user)
    _baseline(db, other)

    wipe_my_data(confirm="LÖSCHEN", db=db, user=user)

    assert db.query(BaselineLocation).count() == 1
    assert db.query(BaselineLocation).one().user_id == other.id
    assert db.query(DayMetric).one().user_id == other.id


def test_media_without_an_event_goes_too(db, user):
    """F18: ein Bild kann dem Konto gehören, ohne an einem Ereignis zu hängen.
    Nur über `event_id` gefiltert bliebe die Zeile stehen — während ihre Datei
    gelöscht wird."""
    from app.models import MediaRef

    db.add(MediaRef(user_id=user.id, provider="local", external_id="foo.jpg",
                    event_id=None))
    db.commit()

    wipe_my_data(confirm="LÖSCHEN", db=db, user=user)

    assert db.query(MediaRef).count() == 0


# --------------------------------------------------------------------------- #
# Das Losungswort — eine Regel, beide Wege
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("typed", ["LÖSCHEN", "LOESCHEN", "DELETE",
                                   " löschen ", "delete"])
def test_every_spelling_of_the_word_counts(typed):
    """Deutsch, englisch, umlautfrei — die Bestätigung ist kein Passwort,
    sondern eine Bremse gegen den Fehlklick. Wer sie auf einer englischen
    Tastatur nicht tippen kann, steht vor einer Wand statt vor einer Bremse."""
    assert is_delete_word(typed)


@pytest.mark.parametrize("typed", ["", "ja", "ok", "löschen bitte", "LÖSCH"])
def test_anything_else_does_not(typed):
    assert not is_delete_word(typed)


def test_deleting_a_user_takes_the_baseline_with_it(db, user, other):
    """Die dritte Kopie derselben Regel. Hier wog die Lücke am schwersten:
    `baseline_locations` zeigt auch auf `users`, und diese Zeile wird gleich
    danach gelöscht — auf PostgreSQL scheiterte damit der ganze Vorgang."""
    from app.routers.admin import delete_user

    _baseline(db, other)

    delete_user(other.id, db=db, admin=user)

    assert db.query(BaselineLocation).count() == 0
    assert db.query(DayMetric).count() == 0
    assert db.get(User, other.id) is None


def test_the_admin_route_asks_for_it_too(db, user):
    """Bis 0.39 leerte ein `POST` ohne Rumpf die ganze Instanz — die einzige
    Nachfrage stand im Frontend."""
    from app.routers.admin import wipe_data

    with pytest.raises(HTTPException) as exc:
        wipe_data(confirm="")
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Was gelöscht wird, muss vorher zu sichern sein
# --------------------------------------------------------------------------- #
def test_the_export_carries_the_baseline_back_and_forth(db, user):
    """Der Wipe-Dialog sagt „mach vorher ein Backup". Bis 0.39 enthielt dieses
    Backup die Grundort-Zeiträume nicht — die einzige von Hand gepflegte
    Tabelle, aus nichts wiederherstellbar."""
    _baseline(db, user)

    payload = export_data(db=db, user=user)
    assert len(payload["baseline_locations"]) == 1
    assert payload["baseline_locations"][0]["date_start"] == "1995-03-01"

    wipe_my_data(confirm="LÖSCHEN", db=db, user=user)
    import_data(payload=payload, db=db, user=user)

    back = db.query(BaselineLocation).one()
    assert back.label == "Kindheit"
    # Ein Tag muss ein Tag bleiben und darf nicht als Zeitpunkt zurückkommen —
    # die Grundort-Rechnung vergleicht `date`, nicht `datetime`.
    assert back.date_start == date(1995, 3, 1)
    assert back.date_end == date(2007, 8, 31)
    assert db.get(Location, back.location_id) is not None
