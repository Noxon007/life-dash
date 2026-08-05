"""F20 — Wohnorte pflegen, und die Tage, die daraus werden.

Eigener Router und nicht in `events.py`, aus demselben Grund, aus dem
`weather.py` einer ist (Anmerkung 119): der Pfad benennt die Sache. Was hier
verwaltet wird, ist **kein Ereignis** — es ist eine stehende Tatsache mit
Gültigkeitszeitraum, die vierte Sorte Aussage aus Anmerkung 144. Unter
`/api/events/…` wäre sie ein Ereignis mit anderem Namen, und genau diese
Verwechslung sollte das Paket vermeiden.

**Zwei Endpunkt-Sorten, und der Unterschied ist die Schicht:** `/api/baselines`
verwaltet die eingetragene Tatsache (Lebensdatenbank), `/api/days/baseline`
liefert die abgeleiteten Tage eines Zeitfensters (Schicht 4, nichts
gespeichert). Sie sehen sich ähnlich und dürfen nie zusammengelegt werden.
"""
from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BaselineLocation, DayMetric, User
from app.schemas import BaselineCreate, BaselineRead, BaselineUpdate
from app.services import baseline
from app.services.enrichment import discard_weather
from app.services.ingestion import place_from_point, resolve_place

router = APIRouter(prefix="/api", tags=["Wohnort"])

# Derselbe Riegel wie bei `/api/days/weather`: kein Größenschutz, sondern eine
# Grenze gegen offensichtlich unsinnige Eingaben — sie muss ein ganzes Leben
# umfassen können, sonst wird sie zur stillen Auslassung (Anmerkung 120).
MAX_DAYS = 40000


def _place(db: Session, user: User, place: str | None,
           lat: float | None, lng: float | None):
    """Ort aus dem Formular: gewählter Punkt schlägt getippten Namen.

    Eine Stelle für beide Aufrufer (anlegen und ändern) — die Regel „der Punkt
    ist die Aussage" zweimal aufzuschreiben hieße, sie beim ersten Sonderfall
    auseinanderlaufen zu lassen (Anmerkung 106).
    """
    if lat is not None and lng is not None:
        return place_from_point(db, user.id, lat, lng, (place or "").strip())
    return resolve_place(db, user.id, (place or "").strip())


def _to_read(row: BaselineLocation, days: int) -> BaselineRead:
    loc = row.location
    return BaselineRead(
        id=row.id, label=row.label,
        date_start=row.date_start, date_end=row.date_end,
        place=(loc.name if loc else ""),
        city=(loc.city if loc else None),
        country=(loc.country if loc else None),
        lat=(loc.lat if loc else None), lng=(loc.lng if loc else None),
        day_count=days,
    )


@router.get("/baselines", response_model=list[BaselineRead])
def list_baselines(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BaselineRead]:
    """Die eingetragenen Zeiträume, chronologisch — mit ihrer Tageszahl.

    `day_count` ist die Zahl der Tage, die dieser Zeitraum WIRKLICH füllt, also
    ohne die Tage, an denen ohnehin ein Eintrag steht. Die Spanne selbst wäre
    die einfachere Zahl und die unehrlichere: „2 190 Tage" neben einem Zeitraum,
    in dem 300 Tage längst erfasst sind, verspricht einen Zuwachs, den es nicht
    gibt.
    """
    rows = baseline.load(db, user.id)
    counts = baseline.day_counts(db, user.id)["per_baseline"] if rows else {}
    return [_to_read(r, counts.get(r.id, 0)) for r in rows]


def _check_span(db: Session, user: User, start: date_type,
                end: date_type | None, *, ignore_id: str | None = None) -> None:
    """Anfang vor Ende, und kein zweiter Wohnort im selben Zeitraum.

    **Ein Wohnort zur Zeit** (Anmerkung 144). Der Fehler nennt den Zeitraum,
    mit dem es sich schneidet — „überschneidet sich" allein wäre eine
    Ablehnung ohne Hinweis, was zu ändern ist, und der Nutzer sieht die andere
    Zeile in derselben Liste.
    """
    if end is not None and end < start:
        raise HTTPException(400, "Das Ende liegt vor dem Anfang.")
    clash = baseline.overlaps(baseline.spans(db, user.id), start, end,
                              ignore_id=ignore_id)
    if clash is not None:
        name = clash.label or (clash.location.name if clash.location else "?")
        raise HTTPException(409, f"Überschneidet sich mit „{name}“ "
                                 f"({clash.date_start} – {clash.date_end or '…'}).")


@router.post("/baselines", response_model=BaselineRead, status_code=201)
def create_baseline(
    payload: BaselineCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BaselineRead:
    """Einen Wohnort eintragen — „von … bis … war ich im Wesentlichen hier".

    Der Ort läuft durch dieselbe Auflösung wie bei einem Ereignis: vorhandener
    Ort wird wiederverwendet, ein neuer bekommt Stadt, Land und
    Adress-Bausteine. Ohne Koordinate bleibt der Eintrag gültig — er trägt dann
    nur kein Wetter, und das sagt die Oberfläche, statt es zu verschweigen.

    **Zwei Wege, und welcher gilt, entscheidet die Angabe.** Getippter Name →
    `resolve_place` (vorwärts geocodiert). Auf der Karte gewählter Punkt →
    `place_from_point`, und dann liegt der Wohnort dort, wo geklickt wurde.
    Gerade hier zählt das: „das Elternhaus" hat oft keine Adresse, die
    Nominatim kennt, und ohne Koordinate bekämen seine 7 000 abgeleiteten Tage
    nie ein Wetter.
    """
    _check_span(db, user, payload.date_start, payload.date_end)
    loc = _place(db, user, payload.place, payload.lat, payload.lng)
    if loc is None:
        raise HTTPException(400, "Ohne Ort ist ein Wohnort keine Aussage.")
    row = BaselineLocation(user_id=user.id, location_id=loc.id,
                           label=(payload.label or "").strip() or None,
                           date_start=payload.date_start,
                           date_end=payload.date_end)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_read(row, baseline.day_counts(db, user.id)["per_baseline"].get(row.id, 0))


def _own(db: Session, user: User, baseline_id: str) -> BaselineLocation:
    row = db.get(BaselineLocation, baseline_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Wohnort nicht gefunden.")
    return row


@router.patch("/baselines/{baseline_id}", response_model=BaselineRead)
def update_baseline(
    baseline_id: str,
    payload: BaselineUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BaselineRead:
    """Zeitraum, Ort oder Bezeichnung ändern.

    **Das ist der Vorgang, für den F20 überhaupt so gebaut ist.** Wären die Tage
    erzeugte Ereignisse, stünden nach dieser einen Änderung tausend bestätigte
    Zeilen falsch da — und nichts dürfte sie anfassen (Anmerkung 144). So ist es
    ein Feld; die Tage rechnen sich beim nächsten Blick neu.

    Das Tageswetter bleibt stehen. Es ist eine Tatsache über (Tag, Ort) und
    nicht über den Zeitraum: verschiebt sich der Zeitraum, hängen die alten
    Werte an Tagen, die der Wohnort nicht mehr füllt, und werden von keiner
    Ansicht mehr gelesen — verkehrt wäre erst, sie als neue Antwort auszugeben.
    Wer sie wirklich los sein will, hat den Aufräum-Knopf.
    """
    row = _own(db, user, baseline_id)
    start = payload.date_start if payload.date_start is not None else row.date_start
    end = payload.date_end if payload.date_end is not None else row.date_end
    if payload.clear_end:
        end = None
    _check_span(db, user, start, end, ignore_id=row.id)
    row.date_start, row.date_end = start, end
    if payload.label is not None:
        row.label = payload.label.strip() or None
    if payload.place or (payload.lat is not None and payload.lng is not None):
        loc = _place(db, user, payload.place, payload.lat, payload.lng)
        if loc is None:
            raise HTTPException(400, "Ort nicht auflösbar.")
        row.location_id = loc.id
    db.commit()
    db.refresh(row)
    return _to_read(row, baseline.day_counts(db, user.id)["per_baseline"].get(row.id, 0))


@router.delete("/baselines/{baseline_id}", status_code=204,
               response_class=Response)
def delete_baseline(
    baseline_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Den Zeitraum entfernen. Der ORT bleibt.

    Ein `Location` kann an Ereignissen hängen; ihn mitzulöschen wäre eine
    Änderung an der Lebensdatenbank als Nebenwirkung einer Änderung an einer
    Ableitungsgrundlage. Das Tageswetter bleibt aus demselben Grund wie beim
    Ändern stehen — es ist verwerfbar, aber nicht falsch.
    """
    db.delete(_own(db, user, baseline_id))
    db.commit()
    return Response(status_code=204)


@router.post("/baselines/weather/clear")
def clear_day_weather(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Das Tageswetter verwerfen — Schicht 4, jederzeit erlaubt.

    Die einzige Aktion in diesem Router, die etwas WEGNIMMT, und sie darf es,
    weil `day_metrics` restlos wiederbeschaffbar ist. `metrics` stünde hier
    nie: dort hinge dieselbe Aktion an bestätigten Ereignissen (Anmerkung 57) —
    dafür gibt es seit Anmerkung 186 den eigenen, ausdrücklichen Knopf unter
    `/api/weather/discard`, und beide gehen durch DIESELBE Funktion. Zwei
    Löschwege für dieselbe Tabelle liefen sonst auseinander, sobald einer von
    beiden eine Zeile mehr treffen muss.
    """
    return {"removed": discard_weather(db, user.id, events=False)["days"]}


@router.get("/days/baseline")
def baseline_days(
    date_from: Annotated[date_type, Query(alias="from")],
    date_to: Annotated[date_type, Query(alias="to")],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Die abgeleiteten Tage eines Zeitfensters.

    `{"periods": [{…}], "days": {"1994-03-14": 0}}` — die Beschreibung EINMAL,
    je Tag nur ihr Index. Ein Zeitraum über sechs Jahre sind 2 190 Tage, und
    „Elternhaus / Musterweg 1, Bad Segeberg / Bad Segeberg / Deutschland" an
    jedem einzelnen davon wäre dieselbe Zeichenkette zweitausendmal: 1,4 MB für
    eine Auskunft, die dreißig Byte trägt. Das ist wörtlich die Rechnung aus
    Anmerkung 157, nur eine Ableitung weiter — und der Grund, aus dem sie hier
    gleich beim ersten Bau steht.

    Bewusst ein EIGENER Abruf und nicht in `/api/events` eingemischt. Der
    Zeitstrahl blättert über Ereignisse (A37, `limit`/`offset`); ein
    hineingeschmuggelter Tag ohne Ereignis verschöbe jeden Versatz und ließe
    die Seitengrenzen auseinanderlaufen — dieselbe Falle, die A39 beim
    Verdichten VOR dem Blättern schon einmal gestellt hat. Die Ansicht legt die
    Tage daneben, der Server hält die beiden Mengen auseinander.
    """
    if date_to < date_from:
        raise HTTPException(400, "„to“ liegt vor „from“.")
    if (date_to - date_from).days > MAX_DAYS:
        raise HTTPException(400, f"Zeitraum zu groß (höchstens {MAX_DAYS} Tage).")
    days = baseline.inferred_days(db, user.id, start=date_from, end=date_to)
    periods: list[dict] = []
    index: dict[str, int] = {}
    out: dict[str, int] = {}
    for day in sorted(days):
        row = days[day]
        if row.id not in index:
            loc = row.location
            index[row.id] = len(periods)
            periods.append({
                "id": row.id, "label": row.label,
                "place": (loc.name if loc else None),
                "city": (loc.city if loc else None),
                "country": (loc.country if loc else None),
            })
        out[day.isoformat()] = index[row.id]
    return {"periods": periods, "days": out}
