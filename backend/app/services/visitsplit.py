"""A46 — ein importierter Besuch endet am Tag, an dem er begonnen hat.

Der Google-Import übernahm `startTime`/`endTime` roh, also wurde jeder
Aufenthalt über Mitternacht ein **mehrtägiges** Ereignis. Bei einem Wohnort
sind das nicht Einzelfälle, sondern fast jede Nacht: gemeldet als „über 2.000
Zwei-Tages-Ereignisse", hunderte davon für dieselbe Stadt.

Der Schaden ist nicht die Zeile, sondern was daran hängt. Ein mehrtägiges
Ereignis taucht in jedem Tag seiner Spanne auf, macht aus einer Nacht zu Hause
zwei Einträge, zählt in „An diesem Tag" doppelt und ist der einzige Kandidat
für den F7-Sammellauf, der daraus dann noch Kind-Zeilen bauen würde. Eine
Spanne ist eine **Aussage** — „das dauerte mehrere Tage" —, und die will
niemand über eine Nacht im eigenen Bett treffen.

**Mehrtägig entsteht ab jetzt nur noch von Hand.** Was der Mensch einträgt,
bleibt unangetastet; was aus einer Maschine kommt, wird an der Tagesgrenze
geschnitten.

Diese Datei hält die Regel EINMAL, weil zwei Seiten sie brauchen: der Import
([routers/tracks.py]) für neue Besuche und der Aufräum-Lauf
([routers/events.py]) für die vorhandenen. Zwei Kopien derselben Regel laufen
auseinander, und zwar still (Anmerkung 106/111).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

# Ab welcher Spanne NICHT mehr geschnitten wird. Ein Besuch über Mitternacht
# ist eine Nacht; ein „Besuch" über drei Wochen ist etwas anderes — eine Lücke
# in den Aufzeichnungen, ein stehengelassenes Gerät, ein Urlaub im Ferienhaus —
# und daraus 21 Zeilen zu machen wäre genau das Rauschen, gegen das dieses
# Paket antritt. Solche Fälle bleiben, wie sie sind, und werden GENANNT
# (Anmerkung 110: was eine Aktion auslässt, gehört in ihre Antwort).
SPLIT_MAX_DAYS = 7


def day_pieces(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Zerlegt [start, end] in Stücke, die je auf einem Kalendertag liegen.

    Ein eintägiger Besuch kommt unverändert zurück — die Funktion ist damit
    überall aufrufbar, ohne vorher zu prüfen, ob es etwas zu tun gibt.

    Die Schnittkante ist 23:59:59 / 00:00:00 und nicht Mitternacht auf beiden
    Seiten: zwei Ereignisse, von denen eines um 00:00:00 endet und das nächste
    um 00:00:00 beginnt, lägen für jede Tagesabfrage in BEIDEN Tagen — der
    Fehler, den dieses Paket gerade behebt, nur eine Sekunde schmaler.

    Über `SPLIT_MAX_DAYS` hinaus wird nicht geschnitten (leere Liste), damit
    der Aufrufer die Entscheidung sieht, statt sie in einer Zahl zu verlieren.
    """
    if end < start:
        start, end = end, start
    if start.date() == end.date():
        return [(start, end)]
    span = (end.date() - start.date()).days + 1
    if span > SPLIT_MAX_DAYS:
        return []

    pieces: list[tuple[datetime, datetime]] = []
    day = start.date()
    while day <= end.date():
        lo = start if day == start.date() else datetime.combine(day, time.min)
        hi = end if day == end.date() else datetime.combine(day, time.max).replace(
            microsecond=0)
        pieces.append((lo, hi))
        day += timedelta(days=1)
    return pieces


def piece_id(base: str, index: int, total: int) -> str:
    """Der `external_id` eines Teilstücks — deterministisch.

    Bei einem einzigen Stück bleibt es beim nackten Schlüssel. Das ist keine
    Kosmetik: Bestandszeilen aus früheren Importen tragen genau diesen
    Schlüssel, und ein eintägiger Besuch muss sich beim Re-Import selbst
    wiedererkennen.

    `Event.external_id` ist String(64), `_seg_hash` liefert 40 Zeichen — für
    das Suffix ist Platz.
    """
    return base if total <= 1 else f"{base}#{index + 1}"


def piece_ids(base: str, total: int) -> list[str]:
    return [piece_id(base, i, total) for i in range(total)]
