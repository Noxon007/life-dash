// P2.1 Stufe 2 — die Vorschau ist Pflicht, nicht Empfehlung.
//
// Anmerkung 107 begründet die jahresweisen Läufe mit einer Zahl: eine zwanzig
// Jahre alte Bibliothek ergibt vierstellig viele Vorschläge in einer
// Warteschlange, die für Dutzende gebaut ist. Der Schutz davor ist ein
// einziges Verhalten der Oberfläche — **anlegen geht erst nach ansehen** —,
// und das ist genau die Sorte Eigenschaft, die beim Bauen aus Versehen
// verschwindet: der Knopf funktioniert ja, er tut nur zu viel.
//
// Geprüft wird deshalb der Zustand, den es GEBEN MUSS (die Regel aus
// `check-a41-cities.js`): der Knopf ist anfangs gesperrt, geht erst nach einer
// Vorschau auf, und schließt wieder, sobald das Jahr gewechselt wird — sonst
// legt er Vorschläge für ein Jahr an, das niemand gesehen hat.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-p21-preview.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
let preview = {
  year: 2024, total: 3, days: 2, albums: 1, photos: 61, shared: 1,
  proposals: [
    { slot: 'immich:album:a1', kind: 'album', title: 'Dänemark 2024',
      start: '2024-08-03T00:00:00', end: '2024-08-09T23:59:59',
      precision: 'day', place: 'Aarhus', photos: 40, shared: false },
    { slot: 'immich:day:2024-07-12:Detmold', kind: 'day', title: '15 Fotos in Detmold',
      start: '2024-07-12T00:00:00', end: '2024-07-12T23:59:59',
      precision: 'day', place: 'Detmold', photos: 15, shared: false },
    { slot: 'immich:album:a2', kind: 'album', title: 'Kreta mit Jan',
      start: '2024-06-05T00:00:00', end: '2024-06-12T23:59:59',
      precision: 'day', place: 'Chania', photos: 6, shared: true },
  ],
};

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.fetch = (u, opt) => {
      const path = String(u);
      calls.push([(opt && opt.method) || 'GET', path, opt && opt.body]);
      let body = [];
      // Form wie der Endpunkt sie liefert: Jahr PLUS Fotozahl. Die Zahl ist
      // der Grund, warum die Liste aus Immich kommt und nicht aus dem eigenen
      // Bestand — 2004 hat 412 Fotos und sonst nichts (Anmerkung 107).
      if (/\/api\/immich\/years/.test(path)) {
        body = { current: 2024, source: 'immich', years: [
          { year: 2024, photos: 61 }, { year: 2023, photos: 240 },
          { year: 2004, photos: 412 }] };
      }
      else if (/\/api\/immich\/preview/.test(path)) body = preview;
      else if (/\/api\/jobs\/start/.test(path)) body = { id: 'j1', type: 'immich_source', status: 'running', done: 0, started_at: '2026-07-22T10:00:00', updated_at: '2026-07-22T10:00:00' };
      else if (/\/api\/jobs/.test(path)) body = [];
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
const started = () => calls.filter(([m, p]) => m === 'POST' && /\/api\/jobs\/start/.test(p));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  const run = d.getElementById('ims-run');
  const sel = d.getElementById('ims-year');
  const box = d.getElementById('ims-result');

  ok('Die Zeile für „Immich als Quelle" existiert', !!run && !!sel && !!box);

  // --- 1. Ohne Vorschau geht nichts -------------------------------------- //
  ok('Der Anlegen-Knopf ist von Anfang an gesperrt', run.disabled,
     'ein Klick ohne Vorschau legt hunderte Vorschläge an');

  await w.loadImmichYears();
  await wait(20);
  ok('Die Jahresauswahl kommt vom Server', sel.options.length === 3,
     `${sel.options.length} Einträge`);
  ok('Das laufende Jahr ist vorgewählt', sel.value === '2024', sel.value);
  // Ein Jahr ohne eigene Daten muss wählbar sein — das ist der Fall, für den
  // das Paket überhaupt existiert („die Erinnerungen von vor dem Smartphone").
  ok('Alte Jahre stehen zur Wahl',
     [...sel.options].some(o => o.value === '2004'),
     [...sel.options].map(o => o.value).join(','));
  ok('…und sagen, wie viel dort liegt',
     /412/.test([...sel.options].map(o => o.textContent).join(' ')),
     'ohne die Zahl ist die Liste eine Aufzählung statt einer Empfehlung');

  // Auch wenn jemand die Sperre umgeht (Konsole, kaputtes CSS): der Klick
  // darf keinen Lauf starten.
  run.disabled = false;
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(20);
  ok('Selbst ein erzwungener Klick startet ohne Vorschau nichts',
     started().length === 0,
     'die Sperre am Knopf ist Bequemlichkeit — die Regel muss im Code stehen');

  // --- 2. Die Vorschau zeigt, was entstehen würde ------------------------ //
  d.getElementById('ims-preview').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);

  const prev = calls.filter(([, p]) => /\/api\/immich\/preview/.test(p));
  ok('Die Vorschau fragt ihr Jahr ab', prev.some(([, p]) => /year=2024/.test(p)),
     JSON.stringify(prev));
  ok('Die Vorschau legt nichts an', started().length === 0);
  ok('Der Kasten ist sichtbar', box.style.display !== 'none');

  const text = box.textContent;
  ok('Sie nennt die Gesamtzahl', /3/.test(text), text.slice(0, 160));
  ok('Sie NENNT die Vorschläge, statt nur zu zählen',
     /Dänemark 2024/.test(text) && /Detmold/.test(text),
     'eine Zahl ist keine Entscheidungsgrundlage (P2.5)');
  ok('Ein geteiltes Album sagt, dass es geteilt ist',
     /geteilt|shared/i.test(text),
     'sonst wandert eine fremde Reise still in die eigene Lebensdatenbank');

  // --- 3. Erst jetzt darf angelegt werden -------------------------------- //
  ok('Nach der Vorschau ist der Knopf offen', !run.disabled);
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(30);
  ok('Der Lauf startet als Job', started().length === 1, `${started().length} Starts`);
  const body = JSON.parse(started()[0][2] || '{}');
  ok('…vom Typ immich_source', body.type === 'immich_source', JSON.stringify(body));
  ok('…und mit dem Jahr im Gepäck', body.params && body.params.year === 2024,
     JSON.stringify(body.params));

  // --- 4. Jahreswechsel entwertet die Vorschau --------------------------- //
  // Der teuerste stille Fehler dieser Oberfläche: Vorschau für 2024 ansehen,
  // auf 2019 umschalten, anlegen — und 2019 hat nie jemand gesehen.
  calls.length = 0;
  preview = { year: 2024, total: 1, days: 1, albums: 0, photos: 9, shared: 0,
              proposals: [preview.proposals[1]] };
  d.getElementById('ims-preview').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Vorschau erneut gelaufen', !run.disabled);

  sel.value = '2022';
  sel.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(20);
  ok('Jahreswechsel sperrt den Knopf wieder', run.disabled,
     'die Vorschau von 2024 hätte den Lauf für 2022 freigegeben');
  ok('…und räumt die alte Vorschau weg', box.style.display === 'none',
     'die Zahlen von 2024 stünden unter dem Jahr 2022');

  console.log(fail ? `\nP2.1/2: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nP2.1/2: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
