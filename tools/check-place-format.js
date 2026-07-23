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
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
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

  console.log(fail ? `\nOrtsnamen-Format: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nOrtsnamen-Format: alles grün');
  process.exit(fail ? 1 : 0);
}, 800);
