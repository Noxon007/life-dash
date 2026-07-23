// A46 — „In Tage schneiden" erst nach dem Nachsehen.
//
// Näher an der F7-Serie kann eine Aktion nicht sein, und trotzdem steht hier
// mehr auf dem Spiel: der F7-Lauf LEGT AN — was zu viel entsteht, kann man
// löschen. Dieser Lauf ÄNDERT bestätigte Zeilen. Er zerlegt sie, schreibt
// ihren Schlüssel um und legt Geschwister daneben; rückgängig macht das kein
// Knopf. Genau deshalb ist die Vorschau hier keine Bequemlichkeit, sondern
// die einzige Stelle, an der jemand widersprechen kann.
//
// Zwei Eigenschaften werden geprüft, die beim Bauen leise verschwinden:
//
//   1. **Ohne Vorschau kein Lauf** — auch dann nicht, wenn die Sperre am
//      Knopf umgangen wird. Ein `disabled` ist Kosmetik; die Regel muss im
//      Code stehen.
//   2. **Die Vorschau nennt die Zeilen DANACH**, nicht nur die Ereignisse.
//      „2.000 Besuche" klingt nach einer Aufräumaktion, „4.000 Zeilen danach"
//      ist die Zahl, die jemanden innehalten lässt — und die man hinterher
//      nicht mehr hören will (Anmerkung 110: was eine Aktion tut, gehört
//      dorthin, wo hingeschaut wird).
//
// Geprüft wird der Zustand, den es GEBEN MUSS (Regel aus check-a41-cities.js):
// die Seite, nachdem ein Mensch Verwaltung → „Meine Daten" geöffnet hat.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-a46-visit-split.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
// `rows_after` ist bewusst eine Zahl, die sonst nirgends vorkommen kann.
// Der erste Anlauf stand hier auf 4 — und ging auch dann durch, als die
// Oberfläche die Zeilenzahl gar nicht mehr nannte: die 4 stak im Datum
// „2026-07-04". Ein Test, der auch am kaputten Stand grün ist, prüft nichts
// (Anmerkung 108).
const preview = {
  events: 2, rows_after: 4711, more: 0, max_days: 7,
  list: [
    { id: 'e1', title: 'Besuch: Musterstraße', days: 2,
      start: '2026-07-01T22:00:00', end: '2026-07-02T07:00:00' },
    { id: 'e2', title: 'Besuch: Bahnhof Detmold', days: 2,
      start: '2026-07-03T23:10:00', end: '2026-07-04T06:20:00' },
  ],
  too_long: [{ id: 'e3', title: 'Besuch: Ferienhaus', days: 60,
               start: '2026-01-01T00:00:00', end: '2026-03-01T00:00:00' }],
  too_long_count: 1,
  with_children: 3,
};

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.fetch = (u, opt) => {
      const path = String(u);
      calls.push([(opt && opt.method) || 'GET', path]);
      let body = [];
      if (/events\/visits\/multiday/.test(path)) body = preview;
      else if (/events\/visits\/split/.test(path)) body = { events: 2, created: 2, too_long_count: 1, with_children: 3 };
      else if (/auth\/config/.test(path)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(path)) body = { immich: null, tracked_modules: null, place_name_parts: ['city'] };
      else if (/auth\/me$/.test(path)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(path)) body = [];
      else if (/\/health/.test(path)) body = { version: '0.39.0', display_version: '0.39.0-dev', channel: 'dev' };
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
const posted = () => calls.filter(([m, p]) => m === 'POST' && /visits\/split/.test(p));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  const run = d.getElementById('btn-md-run');
  const prev = d.getElementById('btn-md-preview');
  const box = d.getElementById('md-result');

  ok('Die Zeile „mehrtägige Besuche" existiert', !!run && !!prev && !!box);

  w.gotoView('admin');
  w.showAdminTab('daten');
  await wait(120);

  ok('„In Tage schneiden" ist von Anfang an gesperrt', run.disabled,
     'ein Klick ohne Vorschau schreibt tausende bestätigte Zeilen um');

  run.disabled = false;
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(30);
  ok('Selbst ein erzwungener Klick schneidet ohne Vorschau nichts',
     posted().length === 0,
     'die Sperre am Knopf ist Bequemlichkeit — die Regel muss im Code stehen');

  // --- Die Vorschau nennt, was entsteht … ------------------------------- //
  prev.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(60);
  const text = box.textContent;
  ok('Die Vorschau wird geholt',
     calls.some(([, p]) => /events\/visits\/multiday/.test(p)),
     JSON.stringify(calls.slice(-3)));
  // Die eigentliche Zahl: nicht „2 Besuche", sondern „4 Zeilen danach".
  ok('Sie nennt die Zeilen DANACH', /4711/.test(text),
     `„aus 2.000 werden 4.000" ist die Zahl, die überrascht — ${text.slice(0, 140)}`);
  ok('Sie NENNT die Besuche, statt nur zu zählen',
     /Musterstraße/.test(text) && /Bahnhof Detmold/.test(text),
     'eine Zahl ist keine Entscheidungsgrundlage (P2.5)');

  // --- … und vor allem, was NICHT entsteht ------------------------------ //
  // Sprachneutral prüfen: jsdom meldet `en-US`, die App startet deshalb
  // ENGLISCH — ein Test gegen den deutschen Quelltext prüft die Rückrichtung
  // (Selbstkontrolle 0.36.0, Anmerkung 108).
  ok('Zu lange Spannen werden genannt', /7|länger|longer/.test(text),
     'sonst sucht jemand vergeblich seinen Ferienhaus-Besuch');
  ok('Übersprungene mit Tages-Einträgen werden genannt',
     /Tages-Einträge|day entries/i.test(text),
     `sonst bleiben drei Ereignisse ohne Erklärung mehrtägig — ${text.slice(-220)}`);

  // --- Erst jetzt darf geschnitten werden -------------------------------- //
  ok('Nach dem Nachsehen ist der Knopf offen', !run.disabled);
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Der Lauf geht raus', posted().length === 1, `${posted().length} Läufe`);
  ok('Danach ist der Knopf wieder zu', run.disabled,
     'der Bestand ist ein anderer — die Vorschau ist verbraucht');

  // --- „Nichts zu tun" ist auch eine Antwort ----------------------------- //
  // Ein leerer Befund darf den Knopf NICHT freigeben: sonst steht dort ein
  // scharfer Lauf ohne alles, was ihn rechtfertigt.
  preview.events = 0; preview.rows_after = 0; preview.list = [];
  preview.too_long_count = 0; preview.with_children = 0;
  prev.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(60);
  ok('Ohne Befund bleibt der Knopf zu', run.disabled,
     'ein Lauf, der nichts zu tun hat, muss auch nichts dürfen');
  ok('…und die Oberfläche sagt es', /Nichts|Nothing/i.test(box.textContent),
     box.textContent.slice(0, 120));

  console.log(fail ? `\nA46-Schnitt: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nA46-Schnitt: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
