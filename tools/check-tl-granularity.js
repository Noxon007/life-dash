// A47 — die Verdichtungsstufe ist eine Frage, und die Oberfläche stellt sie.
//
// Drei Eigenschaften, die man dem Bildschirm nicht ansieht:
//
//   1. **Die Stufe geht an den SERVER.** Verdichtet wird vor dem Blättern
//      (A39/A37); im Browser gruppiert zerschneidet die Seitengrenze eine
//      Gruppe, und beide Hälften zeigen dann eine zu kleine Zahl. Ein
//      Wechsel muss deshalb eine neue Abfrage auslösen, keine Neuzeichnung.
//   2. **Sie geht IMMER mit**, auch wenn gerade nicht verdichtet wird — sonst
//      hinge die Antwort davon ab, in welcher Reihenfolge zwei Schalter
//      umgelegt wurden.
//   3. **Fehlende Daten werden GESAGT.** Die Stufe „Ortsteil" liest
//      `Location.address`, und die gibt es erst seit 0.38. Ein Auswahlfeld,
//      das man anklickt und bei dem nichts passiert, ist genau der stille
//      Defekt, den A40 abgeschafft hat.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-tl-granularity.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
// Unverwechselbare Zahlen: 813 von 907 Orten ohne Bausteine. Ein Test auf „3"
// wäre auch grün, wenn die 3 aus einem Datum stammt.
let index = {
  total: 6, dated: 6, undated: 0, unconfirmed: 0, fuzzy: 0, visits: 6,
  years: [{ year: 2024, count: 6 }], year_min: 2024, year_max: 2024,
  locations_no_address: 813, locations_total: 907,
};
const EVENT = {
  id: 'e1', title: 'Besuch: Rosenthaler Str.', date_start: '2024-07-12T09:00:00',
  date_precision: 'exact', category: 'event', confirmed: 'confirmed',
  source: 'google_timeline',
  location: { id: 'l1', name: 'Rosenthaler Str.', lat: 52.5, lng: 13.4, city: 'Berlin' },
};

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.fetch = (u, opt) => {
      const p = String(u);
      calls.push([(opt && opt.method) || 'GET', p]);
      let body = [];
      if (/events\/index/.test(p)) body = index;
      else if (/api\/events\?/.test(p) || /api\/events$/.test(p)) body = [EVENT];
      else if (/days\/media/.test(p)) body = {};
      else if (/photos\/index/.test(p)) body = { total: 0, years_scanned: [], max_points: 5000 };
      else if (/auth\/config/.test(p)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(p)) body = { immich: null, tracked_modules: null, place_name_parts: ['city'] };
      else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(p)) body = [];
      else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev', channel: 'dev' };
      else if (/\/api\/jobs/.test(p)) body = [];
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
  },
});

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const listCalls = () => calls.filter(([, p]) => /api\/events\?/.test(p));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  const sel = d.getElementById('tl-level');
  const note = d.getElementById('tl-level-note');

  ok('Die Stufen-Auswahl existiert', !!sel);
  ok('…mit vier Stufen', sel && sel.options.length === 4,
     sel ? [...sel.options].map(o => o.value).join(',') : '—');
  ok('…und sie sind BESCHRIFTET', sel && [...sel.options].every(o => o.textContent.trim()),
     'ein Schieber ohne Rasterung müsste man ausprobieren statt lesen');
  ok('Voreingestellt ist die Stadt', sel && sel.value === 'city', sel && sel.value);

  await wait(200);

  // --- 1. Die Stufe geht mit, auch ohne Verdichtung ----------------------- //
  ok('Jede Listenabfrage nennt die Stufe',
     listCalls().length > 0 && listCalls().every(([, p]) => /group=/.test(p)),
     JSON.stringify(listCalls().slice(-3)));

  // --- 2. Ein Wechsel fragt NEU ------------------------------------------ //
  calls.length = 0;
  sel.value = 'country';
  sel.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(200);
  ok('Ein Stufenwechsel löst eine neue Abfrage aus',
     listCalls().some(([, p]) => /group=country/.test(p)),
     `verdichtet wird auf dem Server — ${JSON.stringify(listCalls())}`);

  calls.length = 0;
  sel.value = 'point';
  sel.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(200);
  ok('…auch für „exakter Punkt"',
     listCalls().some(([, p]) => /group=point/.test(p)),
     JSON.stringify(listCalls()));

  // --- 3. Fehlende Bausteine werden GESAGT -------------------------------- //
  ok('Ohne Ortsteil-Stufe steht kein Hinweis da',
     note && note.style.display === 'none',
     'ein Hinweis, der immer dasteht, wird nicht gelesen');

  calls.length = 0;
  sel.value = 'district';
  sel.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(200);
  ok('Bei „Ortsteil" mit dünner Datenlage erscheint der Hinweis',
     note && note.style.display !== 'none',
     'sonst klickt man ein Feld an und es passiert nichts');
  ok('…mit beiden Zahlen',
     /813/.test(note.textContent) && /907/.test(note.textContent),
     note.textContent);
  ok('…und sagt, wo man es nachholt',
     /Ortsnamen|Place names/i.test(note.textContent),
     note.textContent);

  // --- 4. Ist die Datenlage gut, schweigt der Hinweis --------------------- //
  // Eine EIGENE Seite: `fetchIndex()` merkt sich seine Antwort bewusst (ein
  // Index je Sitzung), also lässt sich diese Lage nicht durch Umschalten
  // herstellen — nur durch einen zweiten Start. Der erste Anlauf hier hat
  // genau das übersehen und prüfte in Wahrheit den Zwischenspeicher.
  index = { ...index, locations_no_address: 2, locations_total: 907 };
  const fine = new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w2) {
      w2.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w2.L = new Proxy(function () { return w2.L; }, { get: () => w2.L, apply: () => w2.L });
      w2.fetch = w.fetch;
    },
  });
  const fw = fine.window, fd = fw.document;
  await wait(200);
  const fsel = fd.getElementById('tl-level'), fnote = fd.getElementById('tl-level-note');
  fsel.value = 'district';
  fsel.dispatchEvent(new fw.Event('change', { bubbles: true }));
  await wait(250);
  ok('Bei guter Datenlage bleibt er weg', fnote.style.display === 'none',
     `sonst wird er zur Tapete — ${fnote.textContent.slice(0, 120)}`);
  fw.close();

  console.log(fail ? `\nA47-Stufen: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nA47-Stufen: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
