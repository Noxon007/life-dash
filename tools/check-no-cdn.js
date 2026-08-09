// Anmerkung 207: Die Seite lädt nichts von fremden Rechnern — und die
// Bibliotheken, die sie stattdessen aus dem eigenen Haus lädt, stehen im
// Shell-Cache des Service Workers.
//
// Warum das ein Wächter sein muss und keine Zusage im Kopf: die Content
// Security Policy in `backend/app/main.py` sagt `script-src 'self'`. Ein
// einziges wiedereingefügtes `<script src="https://…">` ist danach kein
// Fehler, den jemand sieht — der Browser verweigert es still, die Karte
// bleibt leer, und in der Konsole steht ein CSP-Verstoß, den der Betreiber
// nie öffnet. Genau die Stille, die dieses Projekt jagt.
//
// Die dritte Prüfung ist die eigentliche: eine Regel an ZWEI Orten
// (`index.html` referenziert, `sw.js` legt in den Cache) läuft still
// auseinander. Wer eine Bibliothek dazunimmt und den Worker vergisst, hat
// wieder eine Offline-Karte, die keine ist — und merkt es erst ohne Netz.
const fs = require('fs');
const path = require('path');

const htmlPath = process.argv[2] || 'frontend/index.html';
const dir = path.dirname(htmlPath);
const html = fs.readFileSync(htmlPath, 'utf8');
const sw = fs.readFileSync(path.join(dir, 'sw.js'), 'utf8');

let fail = 0;
const ok = (n, c) => { console.log((c ? '  ok  ' : '  FAIL ') + n); if (!c) fail++; };

// --- 1. Nichts von fremden Rechnern -----------------------------------------
// Nur die Auslieferung zählt: `src`/`href` an <script>, <link>, <img>, <iframe>.
// Ein href="https://…" in einem <a> ist ein Verweis zum Anklicken, kein
// Ladevorgang, und wäre hier ein Fehlalarm.
const loaders = [...html.matchAll(/<(script|link|img|iframe)\b[^>]*?\b(?:src|href)\s*=\s*"([^"]*)"/gi)];
const remote = loaders.filter(m => /^(https?:)?\/\//i.test(m[2])).map(m => `${m[1]} → ${m[2]}`);
ok('Kein Skript, Stil oder Bild kommt von einem fremden Rechner'
   + (remote.length ? `\n        ${remote.join('\n        ')}` : ''),
   remote.length === 0);

// Gegenrichtung: der Wächter muss auch etwas FINDEN können. Fände er gar
// keine Einbindungen, wäre er grün, weil sein Muster kaputt ist.
ok('…und der Wächter sieht die Einbindungen überhaupt', loaders.length >= 5);

// --- 2. Was eingebunden wird, liegt auch da ---------------------------------
const local = loaders.map(m => m[2])
  .filter(u => u.startsWith('vendor/'))
  .filter((u, i, a) => a.indexOf(u) === i);
ok('Die Seite bindet die eigenen Bibliotheken ein', local.length >= 5);
for (const rel of local) {
  ok(`${rel} liegt im Arbeitsverzeichnis`, fs.existsSync(path.join(dir, rel)));
}

// --- 3. …und der Service Worker legt sie in den Shell-Cache ------------------
for (const rel of local) {
  ok(`${rel} steht in SHELL (sonst gibt es die Karte ohne Netz nicht)`,
     sw.includes(`"/${rel}"`));
}

// Und die Bilder, die Leaflet RELATIV ZU SEINEM CSS sucht — sie stehen in
// keinem `src`, deshalb findet Prüfung 2 sie nicht. Ohne sie öffnet die Karte
// offline ohne Marker: kein Fehler, nur nichts zu sehen.
const cssImages = [...fs.readFileSync(path.join(dir, 'vendor/leaflet.css'), 'utf8')
  .matchAll(/url\((images\/[^)]+)\)/g)].map(m => m[1])
  .filter((u, i, a) => a.indexOf(u) === i);
ok('Das Leaflet-CSS verlangt Bilder', cssImages.length > 0);
for (const img of cssImages) {
  ok(`vendor/${img} liegt da`, fs.existsSync(path.join(dir, 'vendor', img)));
  ok(`vendor/${img} steht in SHELL`, sw.includes(`"/vendor/${img}"`));
}
// Die Marker-Bilder stehen in keinem CSS-`url()` (Leaflet setzt sie im Code
// zusammen) und sind trotzdem das Sichtbarste an der Karte.
for (const img of ['marker-icon.png', 'marker-icon-2x.png', 'marker-shadow.png']) {
  ok(`vendor/images/${img} liegt da`, fs.existsSync(path.join(dir, 'vendor/images', img)));
}

console.log(fail ? `\n${fail} FEHLER` : '\nEigenes Haus: alles grün');
process.exit(fail ? 1 : 0);
