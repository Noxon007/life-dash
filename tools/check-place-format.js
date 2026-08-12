// Anmerkung 114: Die Bausteine-Auswahl des Ortsnamen-Formats muss an BEIDEN
// Enden dieselbe Voreinstellung haben.
//
// Der Server liest ein fehlendes oder leeres `place_name_parts` seit jeher als
// „alle vier Bausteine" (`geocode.sanitize_parts`). Die Oberfläche machte
// daraus vier LEERE Kästchen — sie behauptete also das Gegenteil dessen, was
// tatsächlich galt. Und weil ein Klick den kompletten Stand speichert, hat wer
// dort „Straße" ankreuzte, damit die anderen drei ABGESCHALTET. Aus einer
// falschen Anzeige wurde so eine falsche Einstellung, und danach standen die
// Ortsnamen anders da, als der Nutzer je gewählt hatte.
//
// Geprüft wird der Zustand, nicht das Markup: die Kästchen stehen im HTML
// bereits auf `checked`, und genau das hat den Defekt verdeckt —
// `loadPlaceFormat()` hat sie danach abgeräumt.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-place-format.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const PARTS = ['road', 'suburb', 'city', 'country'];

let fail = 0;
const ok = (name, cond, detail = '') => {
  console.log((cond ? '  ok  ' : '  XX  ') + name + (cond ? '' : ` — ${detail}`));
  if (!cond) fail++;
};

// Antwort des Servers auf /api/auth/me/settings — je Lauf eine andere.
let settings = {};
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.fetch = (url) => Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve(
        String(url).includes('/auth/me/settings') ? settings : []),
    });
  },
});

const checked = d => PARTS.filter(p =>
  d.querySelector(`#fmt-parts [data-part="${p}"]`).checked);

setTimeout(async () => {
  const w = dom.window, d = w.document;

  // 1. Konto ohne gespeicherte Auswahl — der Normalfall bis zum ersten Klick
  settings = {};
  await w.loadPlaceFormat();
  ok('ohne gespeicherte Auswahl sind alle vier Bausteine angehakt',
     checked(d).length === 4,
     `angehakt: ${checked(d).join(', ') || 'keiner'} — der Server rechnet mit allen vieren`);

  // 2. Leere Liste heißt dasselbe wie „nichts gespeichert" (sanitize_parts)
  settings = { place_name_parts: [] };
  await w.loadPlaceFormat();
  ok('leere Liste zählt ebenfalls als „alle"', checked(d).length === 4,
     `angehakt: ${checked(d).join(', ') || 'keiner'}`);

  // 3. Eine echte Auswahl wird unverändert gespiegelt
  settings = { place_name_parts: ['road', 'city'] };
  await w.loadPlaceFormat();
  ok('eine getroffene Auswahl steht genau so da',
     checked(d).join(',') === 'road,city', `angehakt: ${checked(d).join(', ')}`);

  // 4. Die Reihenfolge im Markup ist die kanonische des Servers
  //    (PLACE_NAME_PARTS) — sie ist zugleich die Reihenfolge im Ortsnamen.
  const order = [...d.querySelectorAll('#fmt-parts [data-part]')].map(c => c.dataset.part);
  ok('Bausteine stehen in der Reihenfolge Straße/Ortsteil/Stadt/Land',
     order.join(',') === PARTS.join(','), order.join(','));

  // 5. Anmerkung 221 — der Ort OHNE Namen wird nicht in der Zahl zerschnitten.
  //
  // Wo Nominatim nichts kennt, IST die Koordinate der Name. Das Komma darin
  // trennt Breite von Länge und keine Bestandteile; wer stumpf am ersten Komma
  // kürzt, zeigt „Ort (54.358". Drei Stellen im Frontend taten genau das.
  //
  // `shortPlace` steht auf oberster Skriptebene und ist deshalb KEINE
  // Fenster-Eigenschaft (CLAUDE.md) — `w.shortPlace` wäre stumm `undefined`
  // und die Prüfung eine über nichts. Geholt wird sie über `w.eval`.
  const shortPlace = w.eval('shortPlace');
  ok('shortPlace() gibt es überhaupt', typeof shortPlace === 'function');
  ok('eine Langadresse wird auf den ersten Bestandteil gekürzt',
     shortPlace('Kirschenallee 12, Bad Segeberg') === 'Kirschenallee 12',
     shortPlace('Kirschenallee 12, Bad Segeberg'));
  ok('ein Koordinaten-Platzhalter bleibt ganz',
     shortPlace('Ort (54.358, 10.123)') === 'Ort (54.358, 10.123)',
     shortPlace('Ort (54.358, 10.123)'));
  ok('leer bleibt leer', shortPlace(null) === '' && shortPlace('') === '');

  // Und die Kürzung wird auch BENUTZT: ein ausgeschriebenes
  // `name.split(',')[0]` auf einem Ortsnamen ist die alte Fassung.
  // `\.name\.split` verlangt einen ZUGRIFF (`loc.name`, `e.location.name`) —
  // die Zuweisung in `shortPlace` selbst arbeitet auf dem Parameter und hat
  // keinen Punkt davor, sonst würde die Regel ihre eigene Umsetzung melden.
  ok('keine Stelle kürzt einen Ortsnamen mehr von Hand',
     !/\.name\.split\(',' *\)\[0\]/.test(html.replace(/^\s*\/\/.*$/gm, '')),
     'irgendwo steht noch <etwas>.name.split(\',\')[0] statt shortPlace()');

  // Der Prefix muss zu `geocode.COORD_NAME_PREFIX` im Server passen — sonst
  // kürzt die eine Hälfte, was die andere für einen echten Namen hält.
  const py = fs.readFileSync(process.argv[3] || 'backend/app/services/geocode.py', 'utf8');
  const server = (py.match(/COORD_NAME_PREFIX\s*=\s*"([^"]+)"/) || [])[1];
  ok('Frontend und Server meinen denselben Platzhalter',
     server !== undefined && w.eval('COORD_PREFIX') === server,
     `Server: ${JSON.stringify(server)}, Frontend: ${JSON.stringify(w.eval('COORD_PREFIX'))}`);

  console.log(fail ? `\nOrtsnamen-Format: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nOrtsnamen-Format: alles grün');
  process.exit(fail ? 1 : 0);
}, 800);
