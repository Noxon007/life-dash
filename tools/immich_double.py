"""Ein HTTP-Doppel für Immich, das sich an die echten DTOs hält (Anm. 109).

Unit-Tests ersetzen `search_assets_paged` komplett — der ganze Client-Rand
(URL-Bau, Kopfzeilen, Blättern über `nextPage`, Zeitstempel-Format, exifInfo)
ist damit prinzipiell unerreichbar. Genau dort saßen in 0.37.0 drei von fünf
Befunden.

Serviert:
  * GET  /api/server/about
  * GET  /api/users/me
  * POST /api/search/metadata   (mit `nextPage` als STRING-Token)
  * GET  /api/timeline/buckets
  * GET  /api/albums
  * GET  /api/assets/{id}/thumbnail
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

ME = "11111111-2222-3333-4444-555555555555"
OTHER = "99999999-8888-7777-6666-555555555555"
PAGE = 250

CITIES = [
    (51.9355, 8.8791, "Detmold", "Nordrhein-Westfalen", "Deutschland"),
    (51.5074, -0.1278, "London", "England", "Vereinigtes Königreich"),
    (39.5696, 2.6502, "Palma", "Balearen", "Spanien"),
    (68.4392, 17.4275, None, "Nordland", "Norwegen"),      # ohne Stadt
]


def _assets() -> list[dict]:
    """1 200 Assets über zwei Jahre — darunter alle Sonderfälle."""
    random.seed(42)
    out = []
    base = datetime(2024, 1, 1, 8, 0)
    for i in range(1200):
        when = base + timedelta(days=i // 4, hours=(i % 4) * 3)
        lat, lng, city, state, country = CITIES[i % len(CITIES)]
        exif = {
            "dateTimeOriginal": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "city": city, "state": state, "country": country,
            "exifImageWidth": 4032, "exifImageHeight": 3024,
        }
        # Jedes zwanzigste Bild ohne Koordinaten (Screenshot, WhatsApp).
        if i % 20:
            exif["latitude"] = round(lat + random.uniform(-0.02, 0.02), 6)
            exif["longitude"] = round(lng + random.uniform(-0.02, 0.02), 6)
        out.append({
            "id": f"asset-{i:05d}",
            "ownerId": OTHER if i % 37 == 0 else ME,       # fremde dazwischen
            "visibility": "archive" if i % 53 == 0 else "timeline",
            "originalMimeType": "image/jpeg",
            "originalFileName": f"IMG_{i:05d}.jpg",
            "fileCreatedAt": (when - timedelta(hours=2)).strftime(
                "%Y-%m-%dT%H:%M:%S.000Z"),
            "localDateTime": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "exifInfo": exif,
        })
    # Der Grenzfall aus Anmerkung 111: 01:30 Ortszeit, UTC ist der Vortag.
    out.append({
        "id": "asset-midnight", "ownerId": ME, "visibility": "timeline",
        "originalMimeType": "image/jpeg",
        "fileCreatedAt": "2024-05-12T23:30:00.000Z",
        "localDateTime": "2024-05-13T01:30:00.000Z",
        "exifInfo": {"latitude": 51.9355, "longitude": 8.8791,
                     "city": "Detmold", "state": "NRW", "country": "Deutschland"},
    })
    return out


ASSETS = _assets()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/server/about":
            return self._send({"version": "v1.140.0", "versionUrl": ""})
        if path == "/api/users/me":
            return self._send({"id": ME, "email": "me@example.org"})
        if path == "/api/albums":
            return self._send([{"id": "alb-1", "albumName": "Mallorca_2024",
                                "startDate": "2024-07-01T00:00:00.000Z",
                                "endDate": "2024-07-14T00:00:00.000Z"}])
        if path == "/api/timeline/buckets":
            return self._send([{"timeBucket": "2024-01-01", "count": 900},
                               {"timeBucket": "2025-01-01", "count": 301}])
        if path.startswith("/api/assets/") and path.endswith("/thumbnail"):
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"\xff\xd8\xff")
            return
        return self._send({"message": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if path != "/api/search/metadata":
            return self._send({"message": "not found"}, 404)

        # `takenAfter`/`takenBefore` sind laut Spezifikation Pflicht-MIT-Zone.
        # Fehlt sie, antwortet der echte Server mit 400 — Stufe 1 ist genau
        # darüber gestolpert, also lehnt das Doppel es ebenso ab.
        for field in ("takenAfter", "takenBefore"):
            value = payload.get(field)
            if value and not (value.endswith("Z") or "+" in value[10:]
                              or value[10:].count("-") > 0):
                return self._send(
                    {"message": f"{field} braucht eine Zeitzone"}, 400)

        page = int(payload.get("page") or 1)
        start = (page - 1) * PAGE
        chunk = ASSETS[start:start + PAGE]
        nxt = str(page + 1) if start + PAGE < len(ASSETS) else None
        return self._send({"assets": {"items": chunk, "total": len(ASSETS),
                                      "count": len(chunk), "nextPage": nxt}})


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8199), Handler).serve_forever()
