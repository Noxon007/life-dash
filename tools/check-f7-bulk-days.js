// F7 in Serie — „Alle aufteilen" erst nach dem Nachsehen (Anmerkung 113).
//
// Die Aktion schreibt VERVIELFACHT in die Lebensdatenbank: zwölf Ereignisse
// können zweihundert Zeilen sein, und die müsste man einzeln wieder löschen.
// Der Schutz davor ist ein einziges Verhalten der Oberfläche — anlegen erst
// nach ansehen —, und das ist genau die Sorte Eigenschaft, die beim Bauen aus
// Versehen verschwindet: der Knopf funktioniert ja, er tut nur zu viel.
//
// Geprüft wird der Zustand, den es GEBEN MUSS (Regel aus check-a41-cities.js):
// nicht das Markup im Auslieferungszustand, sondern die Seite, nachdem ein
// Mensch den Weg gegangen ist — Verwaltung öffnen, Reiter „Meine Daten".
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-f7-bulk-days.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
const pending = {
  max_span: 31, events: 2, days: 17, more: 0, vague: 1,
  list: [
    { id: 'e1', title: 'Urlaub auf Mallorca', span: 14, days: 14,
      start: '2005-07-23', end: '2005-08-05' },
    { id: 'e2', title: 'Wochenende Kreta', span: 3, days: 3,
      start: '2019-08-03', end: '2019-08-05' },
  ],
  too_long: [{ id: 'e3', title: 'Auslandsjahr', span: 365, days: 365,
               start: '2011-01-01', end: '2011-12-31' }],
  too_long_count: 1,
};

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.fetch = (u, opt) => {
      const path = String(u);
      calls.push([(opt && opt.method) || 'GET', path]);
      let body = [];
      if (/events\/days\/pending/.test(path)) body = pending;
      else if (/events\/days\/all/.test(path)) body = { events: 2, created: 17, max_span: 31 };
      else if (/auth\/config/.test(path)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(path)) body = { immich: null, tracked_modules: null, place_name_parts: ['city'] };
      else if (/auth\/me$/.test(path)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(path)) body = [];
      else if (/\/health/.test(path)) body = { version: '0.38.0', display_version: '0.38.0-dev', channel: 'dev' };
      else if (/events\/index/.test(path)) body = { total: 0, dated: 0, undated: 0, unconfirmed: 0, fuzzy: 0, years: [] };
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
const posted = () => calls.filter(([m, p]) => m === 'POST' && /days\/all/.test(p));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  const run = d.getElementById('btn-days-run');
  const prev = d.getElementById('btn-days-preview');
  const span = d.getElementById('days-max-span');
  const box = d.getElementById('days-result');

  ok('Die Zeile „Tages-Einträge" existiert', !!run && !!prev && !!span && !!box);

  w.gotoView('admin');
  w.showAdminTab('daten');
  await wait(120);

  ok('„Alle aufteilen" ist von Anfang an gesperrt', run.disabled,
     'ein Klick ohne Vorschau legt hunderte Zeilen an');

  // Auch wenn jemand die Sperre umgeht (Konsole, kaputtes CSS): kein Lauf.
  run.disabled = false;
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(30);
  ok('Selbst ein erzwungener Klick legt ohne Vorschau nichts an',
     posted().length === 0,
     'die Sperre am Knopf ist Bequemlichkeit — die Regel muss im Code stehen');

  // --- Die Vorschau nennt, was entsteht … ------------------------------- //
  prev.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(60);
  const text = box.textContent;
  ok('Die Vorschau fragt mit der eingestellten Spanne',
     calls.some(([, p]) => /days\/pending\?max_span=31/.test(p)),
     JSON.stringify(calls.slice(-3)));
  ok('Sie nennt beide Zahlen', /2/.test(text) && /17/.test(text), text.slice(0, 120));
  ok('Sie NENNT die Ereignisse, statt nur zu zählen',
     /Mallorca/.test(text) && /Kreta/.test(text),
     'eine Zahl ist keine Entscheidungsgrundlage (P2.5)');

  // --- … und vor allem, was NICHT entsteht ------------------------------ //
  ok('Übersprungene lange Spannen stehen dabei', /Auslandsjahr/.test(text),
     'sonst sucht jemand vergeblich sein Jahr in der Liste');
  ok('…mit dem Grund', /365|länger|longer/.test(text), text.slice(-200));
  // Sprachneutral prüfen: jsdom meldet `en-US`, die App startet deshalb
  // ENGLISCH — ein Test gegen den deutschen Quelltext prüft die Rückrichtung
  // und fällt fälschlich durch (Selbstkontrolle 0.36.0, Anmerkung 108).
  ok('Unscharf datierte werden genannt', /unscharf|vaguely/i.test(text),
     'aus „Sommer 2002" 92 Tage zu machen wäre erfunden — das muss dastehen');

  // --- Erst jetzt darf angelegt werden ---------------------------------- //
  ok('Nach dem Nachsehen ist der Knopf offen', !run.disabled);
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Der Lauf geht raus', posted().length === 1, `${posted().length} Läufe`);
  ok('…mit derselben Spanne', /days\/all\?max_span=31/.test(posted()[0][1]),
     posted()[0][1]);
  ok('Danach ist der Knopf wieder zu', run.disabled,
     'der Bestand ist ein anderer — die Vorschau ist verbraucht');

  // --- Spanne geändert = Vorschau entwertet ------------------------------ //
  // Derselbe teure stille Fehler wie beim Jahreswechsel in der Immich-
  // Vorschau: 31 Tage ansehen, auf 366 stellen, aufteilen — und 366 hat nie
  // jemand gesehen.
  calls.length = 0;
  prev.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(60);
  ok('Vorschau erneut gelaufen', !run.disabled);
  span.value = '90';
  span.dispatchEvent(new w.Event('input', { bubbles: true }));
  await wait(20);
  ok('Andere Spanne sperrt den Knopf wieder', run.disabled,
     'die Vorschau für 31 Tage hätte den Lauf über 90 freigegeben');

  console.log(fail ? `\nF7-Serie: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nF7-Serie: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
