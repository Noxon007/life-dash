// Immich — EIN Lauf, kein Jahr, kein Vorher-Ansehen (Anmerkung 206).
//
// **Hier stand das Gegenteil.** `check-p21-preview.js` bewachte die Regel „erst
// sehen, dann anlegen": der Anlege-Knopf war gesperrt, bis für genau dieses
// Jahr eine Vorschau gelaufen war. Der Nutzer hat die Regel gekippt — „im doing
// schaue ich mir keine 8.000 Vorschläge an" —, und damit ist der alte Wächter
// nicht kaputt, sondern gegenstandslos. Ihn stehen zu lassen hieße, eine
// Zusage zu bewachen, die niemand mehr gibt.
//
// **Was an ihre Stelle tritt, und warum es bewacht gehört.** Der Lauf schreibt
// weiterhin bestätigte Lebensdatenbank. Die Sicherheit liegt jetzt nicht mehr
// davor, sondern dahinter: der RÜCKWEG. Zwei Knöpfe, und sie sind ausdrücklich
// nicht dasselbe — Verknüpfungen sind eine Ableitung und dürfen kommentarlos
// weg, Foto-Ereignisse sind Einträge und müssen mit ihrer Zahl nachfragen. Eine
// Oberfläche, die beide gleich behandelt, hat entweder eine unnötige Rückfrage
// oder eine fehlende, und die fehlende merkt niemand, bevor es zu spät ist.
//
// Geprüft wird in BEIDE Richtungen (die Regel aus `check-a41-cities.js`): dass
// der neue Weg funktioniert UND dass vom alten nichts übrig ist. Ein
// zurückgebliebener `?year=`-Aufruf ginge gegen einen Endpunkt, den es nicht
// mehr gibt — das wäre still, denn ein `catch` steht überall.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-immich-run.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
let photoEvents = 1234;

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.confirm = () => { calls.push(['CONFIRM', 'window.confirm', null]); return true; };
    w.fetch = (u, opt) => {
      const path = String(u);
      calls.push([(opt && opt.method) || 'GET', path, opt && opt.body]);
      let body = [];
      if (/\/api\/jobs\/start/.test(path)) body = { id: 'j1', type: 'immich', status: 'running', done: 0, started_at: '2026-08-09T10:00:00', updated_at: '2026-08-09T10:00:00' };
      else if (/\/api\/jobs/.test(path)) body = [];
      // Anmerkung 215: der Rückweg läuft stapelweise. Das Doppel muss deshalb
      // BEIDE Zahlen liefern — `remaining` ist die, an der der Balken hängt und
      // an der der Aufrufer erkennt, dass er fertig ist. Ein Doppel, das ein
      // Feld auslässt, ist keine Vereinfachung, sondern eine andere Funktion:
      // ohne `remaining` liefe die Schleife weiter, bis der Server nichts mehr
      // hergibt, und der Wächter merkte davon nichts.
      else if (/\/api\/photos\/reset/.test(path)) { photoEvents = 0; body = { deleted: 1234, remaining: 0 }; }
      else if (/\/api\/media\/immich\/reset/.test(path)) body = { removed: 7 };
      // Der ECHTE Startweg — ohne ihn kommt die Seite nie bis zu der Zeile,
      // die den Immich-Zustand zeichnet (Anmerkung 112).
      else if (/auth\/config/.test(path)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(path)) body = { immich: { url: 'http://immich.local', has_key: true }, tracked_modules: null, place_name_parts: ['road', 'city', 'country'] };
      else if (/auth\/me$/.test(path)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(path)) body = [];
      else if (/\/health/.test(path)) body = { version: '0.39.0', display_version: '0.39.0-dev', channel: 'dev' };
      else if (/events\/index/.test(path)) body = { total: 0, dated: 0, undated: 0, unconfirmed: 0, fuzzy: 0, years: [], photo_events: photoEvents };
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

  // Den Weg gehen, den ein Mensch geht — nicht die Funktionen selbst rufen
  // (Anmerkung 112: genau so war der alte Wächter grün, während der Knopf beim
  // Nutzer nichts tat).
  w.gotoView('admin');
  w.showAdminTab('daten');
  await wait(140);

  const run = d.getElementById('im-run');
  ok('Der Immich-Lauf hat einen Knopf', !!run);

  // --- 1. Es ist EIN Lauf ------------------------------------------------- //
  ok('Es gibt keinen zweiten Anlege-Knopf mehr', !d.getElementById('ims-run'),
     'zwei Läufe für dieselbe Frage waren der gemeldete Defekt (Anmerkung 206)');
  ok('…und keine Jahresauswahl', !d.getElementById('ims-year'),
     'der Lauf geht über die ganze Bibliothek, nicht über ein Jahr');
  ok('…und keinen Vorschau-Knopf', !d.getElementById('ims-preview'));

  // --- 2. Er startet, sofort, ohne Vorbedingung --------------------------- //
  ok('Der Knopf ist NICHT gesperrt', !run.disabled,
     'die Vorschau-Pflicht ist weg — ein Knopf, der ohne Grund zu bleibt, ist eine Sackgasse');
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Ein Klick startet den Lauf', started().length === 1, `${started().length} Starts`);
  const body = JSON.parse(started()[0][2] || '{}');
  ok('…vom Typ immich', body.type === 'immich', JSON.stringify(body));
  // Der Lauf entscheidet selbst, welche Monate offen sind (die Fotozahl je
  // Monat ist die Marke). Ein Jahr mitzuschicken wäre eine zweite Antwort auf
  // dieselbe Frage — und die ältere.
  ok('…und OHNE Jahr im Gepäck',
     !body.params || (!('years' in body.params) && !('year' in body.params)),
     JSON.stringify(body.params));

  // --- 3. Vom alten Weg ist nichts übrig ---------------------------------- //
  // Die Gegenrichtung: ein zurückgebliebener Aufruf ginge gegen einen
  // Endpunkt, den es nicht mehr gibt, und `catch` verschluckt das lautlos.
  ok('Niemand fragt mehr die Jahresliste ab',
     !calls.some(([, p]) => /\/api\/immich\/years/.test(p)),
     JSON.stringify(calls.map(c => c[1]).filter(p => /immich/.test(p))));
  ok('Niemand fragt mehr die Vorschau ab',
     !calls.some(([, p]) => /\/api\/immich\/preview/.test(p)),
     JSON.stringify(calls.map(c => c[1]).filter(p => /immich/.test(p))));
  ok('Und kein Lauf heißt mehr photo_points',
     !started().some(([, , b]) => /photo_points/.test(b || '')),
     'den Job-Typ gibt es serverseitig nicht mehr — ein Start liefe ins Leere');

  // --- 4. Der Rückweg ist das, was die Vorschau ersetzt ------------------- //
  const undo = d.getElementById('im-reset');
  const drop = d.getElementById('pp-reset');
  ok('Verknüpfungen lassen sich verwerfen', !!undo);
  ok('Foto-Ereignisse lassen sich verwerfen', !!drop,
     'ohne Rückweg wäre der Wegfall der Vorschau eine Einbahnstraße');

  // **Die Rückfrage gehört genau an EINEN der beiden Knöpfe.** Verknüpfungen
  // sind eine Ableitung; Foto-Ereignisse sind Einträge, und der Lauf hat
  // tausende davon angelegt, ohne dass jemand sie vorher gesehen hat.
  //
  // Gefragt wird im EIGENEN Dialog, nicht mit `window.confirm` (Anmerkung 215):
  // die Rückfrage nennt die Zahl, und die holt der Knopf unmittelbar davor
  // frisch — `mp.photoTotal` ist eine Merkzelle, und wer den Reiter offen
  // liegen ließ, während der Immich-Lauf arbeitete, bekäme aus ihr „es gibt
  // keine" über achttausend Zeilen.
  calls.length = 0;
  drop.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(80);
  const modal = d.getElementById('confirm-modal');
  ok('Das Verwerfen der Foto-Ereignisse fragt nach',
     !!modal && modal.classList.contains('show'),
     'tausend bestätigte Zeilen ohne Rückfrage zu löschen ist die Einbahnstraße andersherum');
  ok('…und nennt dabei die Zahl',
     /1[.,]?234/.test(d.getElementById('cf-text').textContent),
     `„${d.getElementById('cf-text').textContent}" — eine Rückfrage ohne Zahl ist keine Entscheidungsgrundlage`);
  ok('…frisch geholt, nicht aus der Merkzelle',
     calls.some(([m, p]) => m === 'GET' && /events\/index/.test(p)),
     JSON.stringify(calls.map(c => c[1])));
  // Die Gegenrichtung: solange niemand zugestimmt hat, ist nichts gelöscht.
  ok('…und löscht nichts, bevor jemand zustimmt',
     !calls.some(([m, p]) => m === 'POST' && /\/api\/photos\/reset/.test(p)),
     'die Rückfrage wäre dann Zierde');
  d.getElementById('cf-ok').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(400);
  ok('…und löscht erst danach',
     calls.some(([m, p]) => m === 'POST' && /\/api\/photos\/reset/.test(p)));
  // **Der Lauf sagt, dass er läuft** — das war die Rückmeldung: „keine saubere
  // Meldung, wie lange das dauert und ob er noch was macht." Er ist deshalb
  // stapelweise (jede Anfrage trägt ihre Deckelung) und registriert (er steht
  // im Jobs-Reiter, obwohl der Browser ihn taktet).
  ok('…stapelweise, damit es etwas zu melden gibt',
     calls.some(([m, p]) => m === 'POST' && /\/api\/photos\/reset\?limit=\d+/.test(p)),
     'ohne Deckelung ist es EINE Anweisung über zehntausende Zeilen — daran ist nichts zu takten');
  ok('…und steht als Lauf im Protokoll',
     started().some(([, , b]) => /photo_reset/.test(b || '')),
     'ein Lauf, der Bestätigtes löscht, gehört in den Jobs-Reiter');

  console.log(fail ? `\nImmich-Lauf: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nImmich-Lauf: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
