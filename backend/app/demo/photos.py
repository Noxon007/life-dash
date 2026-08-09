"""Bilder für den Demo-Bestand — erzeugt, nicht mitgeliefert.

**Warum es überhaupt Bilder braucht.** Fotoleisten im Zeitstrahl, die Lightbox,
Bilder an einem TAG (F18) und die Foto-Tafel der Statistik sind vier Ansichten,
die ohne ein einziges Bild leer bleiben — und eine leere Ansicht liest sich in
einem Schaufenster als „kann das nicht".

**Warum sie erzeugt und nicht beigelegt werden.** Ein Beutel echter Fotos im
Repository wäre ein Lizenz- und Größenproblem für jeden, der es klont, und
freie Bilder aus dem Netz zu holen hieße, dass der Demo-Aufbau doch wieder eine
Verbindung braucht. Erzeugt sind sie ein paar Kilobyte Code, immer dieselben,
und offensichtlich das, was sie sind.

**Sie geben sich als Platzhalter zu erkennen, und das ist Absicht.** Ein
abstrakter Farbverlauf mit Ort und Datum darauf behauptet nichts. Ein Bild, das
wie ein Foto aussieht, es aber nicht ist, wäre in einem Schaufenster für eine
LEBENSdatenbank die eine Unehrlichkeit, die man ihr nicht verzeiht.

**Sie gehen denselben Weg wie ein Upload** (`services.media.store`): Format
geprüft, Vorschau erzeugt, Maße vermessen. Ein eigener Schreibweg wäre eine
zweite Sorte hochgeladenes Bild — und die eine, die kein Test kennt.

**Was die Demo damit NICHT zeigt: die Foto-Ebene der Karte.** Die besteht seit
Anmerkung 139 aus Ereignissen der Quelle `immich` und lebt von Vorschaubildern,
die ein fremder Server ausliefert. Ohne eine Immich-Instanz wären das tausende
tote Verweise — ein kaputtes Bild an jedem Punkt ist schlechter als kein Punkt.
Diese Ebene bleibt der Konnektor-Funktion vorbehalten, die sie ist.
"""
from __future__ import annotations

import hashlib
import io
import math
import struct

from PIL import Image, ImageDraw, ImageFont

# Bewusst klein: der Demo-Bestand soll ein Volume nicht sprengen. 1024 px ist
# über der Vorschaugröße (640) und damit gross genug, dass die Lightbox etwas
# zu zeigen hat.
SIZE = (1024, 768)
QUALITY = 72


def _seed(*parts: object) -> int:
    raw = "|".join(str(p) for p in parts).encode()
    return struct.unpack("<Q", hashlib.blake2b(raw, digest_size=8).digest())[0]


def _palette(seed: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Zwei Töne desselben Farbkreis-Abschnitts — nie zwei zufällige Farben.

    Zufällig gewählte RGB-Paare ergeben verlässlich Schlamm. Der Ton kommt
    deshalb aus dem Startwert, die Helligkeit aus einem festen Abstand.
    """
    hue = (seed % 360) / 360
    def rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
        i = int(h * 6) % 6
        f = h * 6 - int(h * 6)
        p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
        r, g, b = ((v, t, p), (q, v, p), (p, v, t),
                   (p, q, v), (t, p, v), (v, p, q))[i]
        return int(r * 255), int(g * 255), int(b * 255)
    return rgb(hue, 0.42, 0.86), rgb((hue + 0.08) % 1, 0.62, 0.38)


def _font(px: int) -> ImageFont.ImageFont:
    """Die eingebaute Schrift in der gewünschten Größe.

    Keine Schriftdatei aus dem System: die gibt es auf einem Alpine-Container
    nicht, und ein Bild, das nur auf dem Rechner des Autors eine Beschriftung
    trägt, ist genau die Sorte Unterschied, die niemand bemerkt.
    """
    try:
        return ImageFont.load_default(size=px)
    except TypeError:      # sehr alte Pillow-Fassungen kennen `size` nicht
        return ImageFont.load_default()


def make_photo(place: str, when: str, caption: str) -> bytes:
    """Ein Platzhalterbild als JPEG-Bytes — gleiche Eingabe, gleiches Bild."""
    seed = _seed(place, when, caption)
    top, bottom = _palette(seed)
    img = Image.new("RGB", SIZE, top)
    draw = ImageDraw.Draw(img)

    # Verlauf von oben nach unten, zeilenweise — für 768 Zeilen billiger als
    # jede Bibliothek und ohne Abhängigkeit.
    for y in range(SIZE[1]):
        f = y / (SIZE[1] - 1)
        draw.line([(0, y), (SIZE[0], y)],
                  fill=tuple(int(top[i] + (bottom[i] - top[i]) * f) for i in range(3)))

    # Drei weiche Kreise als Horizont-Andeutung. Sie sagen nichts aus — sie
    # sorgen nur dafür, dass zwei Bilder desselben Ortes sich unterscheiden.
    for k in range(3):
        r = 120 + (seed >> (k * 7)) % 260
        cx = (seed >> (k * 5)) % SIZE[0]
        cy = SIZE[1] - 80 - (seed >> (k * 3)) % 220
        shade = tuple(min(255, int(bottom[i] + 40 + 25 * math.sin(k + seed % 7)))
                      for i in range(3))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade)

    # Der Balken unten trägt die Beschriftung und macht sie auf jedem Verlauf
    # lesbar — heller Text auf hellem Himmel wäre die Hälfte der Bilder.
    draw.rectangle([0, SIZE[1] - 132, SIZE[0], SIZE[1]], fill=(18, 18, 22))
    draw.text((44, SIZE[1] - 108), caption[:52], font=_font(38), fill=(245, 245, 248))
    draw.text((44, SIZE[1] - 56), f"{place} · {when}", font=_font(26),
              fill=(168, 168, 178))
    draw.text((SIZE[0] - 250, SIZE[1] - 56), "Demo-Bild", font=_font(22),
              fill=(120, 120, 132))

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=QUALITY)
    return buf.getvalue()
