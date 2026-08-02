// Eine Rekord-Kachel führt zu IHREM TAG (Anmerkung 142).
//
// Gemeldet: „Wenn ich in der Statistik auf den heißesten Tag klicke, bekomme
// ich das Fenster für den Eintrag bearbeiten — ich möchte, dass zum Zeitstrahl
// oder zur Karte gesprungen wird."
//
// Der Klick öffnete `openEventEdit()`, und das ist an drei Stellen die falsche
// Antwort:
//
//   1. Es beantwortet die gestellte Frage nicht. Wer auf „38,4 °C · heißester
//      Tag" klickt, will wissen, was an diesem Tag war, und bekommt ein
//      Formular.
//   2. Der geöffnete Eintrag IST nicht der Tag, sondern der eine, der zufällig
//      den Messwert trägt. Seit Anmerkung 119 entsteht der Tageswert aus einer
//      Verdichtung über ALLE Einträge des Tages — die Kachel nennt einen Tag,
//      die gespeicherte Kennung zeigte auf einen Eintrag. Anmerkung 106 in
//      klein: zwei Angaben über verschiedene Dinge, die aussehen wie eine.
//   3. Ein Bearbeiten-Dialog aus einer Statistik heraus lädt dazu ein,
//      Bestätigtes zu ändern, wo niemand danach gefragt hat.
//
// Geprüft wird der Zustand, den es geben MUSS (Regel aus check-a41-cities.js):
// die Statistik, nachdem sie ihre Zahlen bekommen hat.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-stat-day-jump.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];

// Unverwechselbare Werte: ein Test, der auf „7" prüft, ist auch grün, wenn die
// 7 aus einer Seitenzahl stammt (beim Schreiben von check-a46-visit-split.js
// genau so passiert).
const HOT_DAY = '2015-07-03';
const HOT_EVENT = 'ereignis-mit-dem-messwert';
const OVERVIEW = {
  counts: { events: 99, places: 12, cities: 4, concerts: 1, artists: 0,
            unconfirmed: 0, milestones: 2, moves: 1, meals: 3 },
  age: 30, birth: null, weather: {},
  per_year: [], per_category: [], top_places: [], top_cities: [], top_animals: [],
  extremes: {
    hot: { value: 38.4, id: HOT_EVENT, title: 'Grillen',
           date_start: `${HOT_DAY}T14:00:00`, date_precision: 'exact',
           place: 'Detmold' },
  },
};

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.__zoom = 6;
    w.L = new Proxy(function () { return w.L; }, {
      get: (_t, k) => (k === 'getZoom' ? () => w.__zoom : w.L), apply: () => w.L });
    w.fetch = (u, opt) => {
      const p = String(u);
      calls.push([(opt && opt.method) || 'GET', p]);
      let body = [];
      if (/stats\/overview/.test(p)) body = OVERVIEW;
      else if (/events\/index/.test(p)) body = { total: 1, dated: 1, undated: 0,
        unconfirmed: 0, fuzzy: 0, years: [2015], visits: 0, machine_proposals: 0 };
      else if (/auth\/config/.test(p)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(p)) body = { immich: null };
      else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(p)) body = [];
      else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
      else if (/api\/tracks/.test(p)) body = { total: 0, shown: 0, tracks: [] };
      else if (/photos\/index/.test(p)) body = { total: 0, years_scanned: [] };
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

setTimeout(async () => {
  const w = dom.window, d = w.document;
  await wait(140);

  const card = d.querySelector('#view-stats .stat-card[data-event-slot="hot"]');
  ok('Die Kachel „heißester Tag" gibt es', !!card);

  // Zustand HERSTELLEN: die Statistik, nachdem der Server geantwortet hat.
  // Den Auslieferungszustand zu lesen prüfte einen Zustand, in dem niemand ist
  // — die Kacheln stehen bis dahin auf „–" und tragen gar kein Datum
  // (Regel aus check-a41-cities.js).
  let painted = true;
  try { await w.loadStats(); }
  catch (e) { painted = false; ok('Die Statistik lässt sich zeichnen', false, e.message); }
  await wait(60);

  if (painted && card) {
    ok('Die Kachel merkt sich den TAG', card.dataset.day === HOT_DAY,
       `dataset.day = ${JSON.stringify(card.dataset.day)} — der Messwert hängt `
       + 'seit Anmerkung 119 am Tag, nicht an einem Eintrag');
    ok('…und NICHT die Ereigniskennung', !card.dataset.eventId,
       `dataset.eventId = ${card.dataset.eventId} — das war der Weg in den `
       + 'Bearbeiten-Dialog');

    // Der eigentliche Bericht: was passiert beim Klick?
    let edited = null;
    w.openEventEdit = id => { edited = id; };
    calls.length = 0;
    card.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(120);

    ok('Ein Klick öffnet KEINEN Bearbeiten-Dialog', edited === null,
       `openEventEdit(${edited}) — genau das war der Bericht`);
    ok('…sondern führt in den Zeitstrahl',
       d.getElementById('view-timeline').classList.contains('active'),
       'eine Zahl, die man nicht aufmachen kann, ist eine Sackgasse (Anm. 94)');
    ok('…und schränkt ihn auf den Tag ein', w.eval('tl.day') === HOT_DAY,
       String(w.eval('tl.day')));
    const evCalls = calls.filter(([, p]) => /api\/events\?/.test(p)).map(c => c[1]);
    ok('…serverseitig, mit Fenster',
       evCalls.some(p => p.includes(`from=${HOT_DAY}`)),
       `${JSON.stringify(evCalls.slice(-3))} — im Browser gefiltert träfe der `
       + 'Tag nur die geladene Seite, und die reicht nie bis 2004');
    ok('…mit eingeblendeten importierten Besuchen',
       evCalls.some(p => /visits=1/.test(p)),
       'an so einem Tag stehen oft nur Besuche — sonst ist die Antwort auf eine '
       + 'sichtbare Zahl eine leere Liste');
    // `evCalls.length > 0` gehört in die Bedingung: eine Negativ-Zusicherung
    // über eine LEERE Liste ist immer wahr. Gegen den kaputten Stand gefahren
    // stand hier „ok …und UNverdichtet", obwohl gar keine Anfrage abging —
    // dritte Zusicherung in diesem Projekt, die aus dem falschen Grund grün
    // war (Anmerkung 108).
    ok('…und UNverdichtet',
       evCalls.length > 0 && !evCalls.some(p => /condense=1/.test(p)),
       `${JSON.stringify(evCalls.slice(-3))} — „12× Detmold" ist die Antwort auf `
       + 'eine Übersicht, nicht auf einen einzelnen Tag');
    ok('Der Tages-Zoom greift', w.eval("tl.zoom") === 'day',
       'ein einzelner Tag unter einer Jahresüberschrift sieht aus wie ein Jahr '
       + 'mit einem Eintrag');

    // Der Chip: sichtbar, benannt, abwerfbar (Anmerkung 92).
    const chip = d.getElementById('tl-day-chip');
    ok('Der Zeitstrahl zeigt einen Chip', chip && chip.style.display !== 'none',
       'ein fast leerer Zeitstrahl ohne sichtbaren Grund ist die stille '
       + 'Falschaussage aus Anmerkung 92');
    if (chip) {
      ok('…mit dem Datum', /2015/.test(chip.textContent) && /3/.test(chip.textContent),
         chip.textContent);
      ok('…und mit dem Anlass', /heiß|hot/i.test(chip.textContent),
         `${chip.textContent} — sonst ist es ein Datum ohne Herkunft`);

      chip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      await wait(80);
      ok('Ein Klick auf den Chip hebt die Einschränkung auf',
         !w.eval('tl.day') && chip.style.display === 'none',
         'ein Chip ohne Abschaltung ist eine Sackgasse mit Beschriftung');
    }
  }

  // Eine Kachel OHNE Wert hat keinen Tag und tut deshalb nichts (A40).
  const cold = d.querySelector('#view-stats .stat-card[data-event-slot="cold"]');
  ok('Eine Kachel ohne Wert merkt sich keinen Tag', cold && !cold.dataset.day,
     `dataset.day = ${cold && cold.dataset.day} — „–" hat keinen Tag, zu dem `
     + 'es führen könnte');

  console.log(fail ? `\nRekord-Kacheln: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nRekord-Kacheln: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
