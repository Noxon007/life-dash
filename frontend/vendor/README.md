# Third-party libraries, served by this instance

These files are **vendored on purpose** — copied into the repository and served
from the same origin as the rest of the app. They are not built, not minified
here and not patched; they are byte-for-byte what the upstream release ships.

| File | Package | Version | Licence |
|---|---|---|---|
| `leaflet.js`, `leaflet.css`, `images/*` | [Leaflet](https://leafletjs.com) | 1.9.4 | BSD-2-Clause — `LICENSE-leaflet.txt` |
| `leaflet.markercluster.js`, `MarkerCluster.css`, `MarkerCluster.Default.css` | [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster) | 1.5.3 | MIT — `LICENSE-markercluster.txt` |

## Why not a CDN

They came from unpkg until 2026-08-09, with pinned versions and no integrity
hash. Note 200 listed that among the ten open findings; note 207 closed it.
Four reasons, and only the first is the obvious one:

1. **A script tag with no `integrity` is a standing permission.** Whatever the
   CDN returns for that URL executes in a page that renders the entire life
   database. Pinning the version limits what *upstream* can change; it does
   nothing about what the delivery path can.
2. **A CSP is impossible while they are remote in any useful form.** With
   `script-src 'self'` the header can be strict instead of decorative — and a
   strict CSP is what the rest of the hardening leans on.
3. **Every start told a third party that this instance exists**, and roughly
   when it is used. For self-hosted software whose whole point is that the data
   stays home, that is the wrong first request of the session.
4. **The offline map was never offline.** The service worker caches the shell so
   the app opens without a network; it could not cache a cross-origin script it
   is not allowed to read. Without a network, Leaflet itself was missing — so
   the map failed at the library, not at the tiles. It is in `SHELL` now.

## Updating

Download the release files from unpkg or GitHub, replace them here unchanged,
update the version in the table above, and bump `CACHE` in `../sw.js` — the
shell cache is keyed by that name, and without the bump an installed app keeps
serving the old copy until the name changes.
