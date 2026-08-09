// F10-Rest — der Welt-Reiter und die Ranglisten werden im SERVER benannt.
//
// Der Rest der Oberfläche übersetzt sich selbst: deutscher Quelltext, `I18N_EN`
// daneben, `t()` dazwischen. Länder- und Kontinentnamen können das nicht — es
// sind zweihundert Stammdatenzeilen, und sie liegen im Backend. Damit hängt
// dieser eine Reiter an einer Antwort, die schon gefallen ist, bevor der Browser
// sie zeichnet, und das erzeugt genau zwei Fallen:
//
//   1. **Die Frage muss die Sprache NENNEN.** Der Sprachknopf schaltet die
//      Oberfläche um und schickt die neue Sprache erst DANACH ins Konto
//      (`PATCH /auth/me/settings`, absichtlich ohne `await`). `redrawForLang()`
//      holt den Reiter im selben Atemzug neu — ohne ausdrückliche Angabe kommt
//      er in der ALTEN Sprache zurück und bleibt bis zum Neuladen so stehen.
//   2. **Die Merkzelle muss die Sprache KENNEN.** `loadStatsTops` merkt sich
//      die Ranglisten unter dem Bestandsstempel. Ein Sprachwechsel ändert den
//      Bestand nicht: die Listen galten als „schon geladen" und blieben
//      deutsch. Was die Antwort mitbestimmt, gehört in den Schlüssel, unter dem
//      man sie sich merkt.
//
// Beide Male ist nichts kaputt — es ist nur die Hälfte übersetzt, und das sieht
// nicht wie eine Lücke aus, sondern wie ein Fehler (Anmerkung 114).
//
// Der Wächter fährt deshalb die KETTE: Reiter öffnen, Sprache umschalten,
// nachsehen was auf dem Draht steht UND was in der Seite steht. Ein
// Doppel, das jede Anfrage gleich beantwortet, würde die erste Falle nie
// zeigen — dieses hier antwortet wie der echte Server, also nach `lang`.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-world-lang.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));

// Das Doppel antwortet wie der echte Server: nach der GEFRAGTEN Sprache, und
// ohne Frage nach dem gespeicherten Konto — das hier absichtlich auf Deutsch
// steht, damit „hat nicht gefragt" und „hat richtig gefragt" unterscheidbar
// bleiben.
const ACCOUNT_LANG = 'de';
const askedLang = p => (String(p).match(/[?&]lang=([a-z]+)/) || [])[1] || ACCOUNT_LANG;

const WORLD = lang => ({
  countries_total: 200,
  countries_visited: 1,
  continents_total: 7,
  continents_visited: 1,
  unmatched: [],
  recent: [{ iso: 'DE', name: lang === 'en' ? 'Germany' : 'Deutschland',
             continent: 'EU', event_count: 3, day_count: 2,
             first_visit: '2020-05-01T00:00:00', last_visit: '2022-08-03T00:00:00',
             avg_temp_c: null }],
  continents: [
    { code: 'EU', label: lang === 'en' ? 'Europe' : 'Europa', total: 44, visited: 1,
      countries: [{ iso: 'DE', name: lang === 'en' ? 'Germany' : 'Deutschland',
                    continent: 'EU', event_count: 3, day_count: 2,
                    first_visit: '2020-05-01T00:00:00',
                    last_visit: '2022-08-03T00:00:00', avg_temp_c: null }],
      missing: [lang === 'en' ? 'France' : 'Frankreich'] },
    // Der zweite Kontinent ist der interessante: sein Name ist in beiden
    // Sprachen ZWEI Wörter und teilt kein Wort mit dem deutschen — „Europe"
    // gegen „Europa" könnte ein Wächter versehentlich durchgehen lassen.
    { code: 'NA', label: lang === 'en' ? 'North America' : 'Nordamerika',
      total: 23, visited: 0, countries: [],
      missing: [lang === 'en' ? 'Canada' : 'Kanada'] },
  ],
});

const TOPLISTS = lang => ({
  weather: { hot: [], cold: [], sunny: [], rainy: [], windy: [], snowy: [],
             gust: [], felt_hot: [], felt_cold: [], longest_day: [],
             shortest_day: [], rain_long: [] },
  places: [], cities: [], years: [], categories: [],
  countries: [{ name: lang === 'en' ? 'Greece' : 'Griechenland',
                days: 4711, events: 8123 }],
  streaks: {}, photos: null, farthest: null, reach: [],
});

function makeDom() {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      // Der Auffang-Proxy gibt sich selbst zurück — für `getZoom` wäre das
      // keine Zahl (die Lehre aus check-stats-panes.js).
      w.L = new Proxy(function () { return w.L; },
        { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
      w.fetch = (u, opt) => {
        const p = String(u);
        calls.push([(opt && opt.method) || 'GET', p]);
        let body = [];
        if (/\/api\/world/.test(p)) body = WORLD(askedLang(p));
        else if (/stats\/toplists/.test(p)) body = TOPLISTS(askedLang(p));
        else if (/stats\/tracks/.test(p)) body = { total_km: 0, count: 0, modes: [], years: [], longest: [] };
        else if (/stats\/overview/.test(p)) body = {
          counts: { events: 0, unconfirmed: 0, places: 0, cities: 0, concerts: 0,
                    milestones: 0, meals: 0, moves: 0 },
          birth: null, age: null, per_year: [], per_category: [], top_places: [],
          top_cities: [], top_animals: [], extremes: {}, weather: { days: 0 } };
        else if (/stats\/widgets/.test(p)) body = [];
        else if (/events\/index/.test(p)) body = { revision: 'r1', total: 0, dated: 0,
          undated: 0, unconfirmed: 0, years: [] };
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/world-countries\.geojson/.test(p)) body = { type: 'FeatureCollection', features: [] };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      };
    },
  });
}

const flat = el => (el ? el.textContent : '').replace(/\s+/g, ' ');
// `LANG` steht als `let` im Skript und ist deshalb KEINE Fenster-Eigenschaft —
// `w.LANG` wäre stumm `undefined` und die Prüfung eine über nichts.
const inPage = (w, code) => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };
const worldCalls = () => calls.filter(([, p]) => /\/api\/world/.test(p)).map(c => c[1]);
const topsCalls = () => calls.filter(([, p]) => /stats\/toplists/.test(p)).map(c => c[1]);
// **`every` auf einer leeren Liste ist wahr.** „Jede Anfrage nennt die Sprache"
// wäre also genau dann grün, wenn gar keine gestellt wurde — die teuerste
// Sorte Prüfung: eine, die schweigt, weil nichts passiert ist.
const allAsk = (list, lang) =>
  list.length > 0 && list.every(p => new RegExp(`[?&]lang=${lang}(&|$)`).test(p));

setTimeout(async () => {
  const w = makeDom().window, d = w.document;
  await wait(200);

  // --- 1. Der Reiter, wie er startet -------------------------------------- //
  //
  // Unter jsdom startet die Seite ENGLISCH (kein gespeicherter Wert, Katalog
  // greift) — der Reiter muss also schon beim ersten Öffnen englisch fragen,
  // und nicht erst nach einem Umschalten.
  ok('Die Seite startet englisch', inPage(w, 'LANG') === 'en', `LANG = ${inPage(w, 'LANG')}`);

  calls.length = 0;
  d.querySelector('.nav-item[data-view="world"]')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(250);

  ok('Der Welt-Reiter wird geholt', worldCalls().length > 0, JSON.stringify(calls.map(c => c[1])));
  ok('…und die Anfrage NENNT die Sprache',
     allAsk(worldCalls(), 'en'),
     `${worldCalls().join(', ')} — ohne Angabe entscheidet das gespeicherte `
     + 'Konto, und das hinkt beim Umschalten eine Runde hinterher');

  const box = d.getElementById('world-checklist');
  let txt = flat(box);
  ok('Die Kontinente stehen englisch da',
     /North America/.test(txt) && !/Nordamerika/.test(txt), txt.slice(0, 200));
  ok('…die besuchten Länder auch',
     /Germany/.test(txt) && !/Deutschland/.test(txt), txt.slice(0, 200));
  // Die Checkliste ist überwiegend die FEHLENDE Hälfte — sie ist der Reiter.
  const missing = d.querySelector('#world-checklist .world-missing');
  ok('…und die fehlenden ebenfalls',
     /France/.test(flat(missing)) && !/Frankreich/.test(flat(missing)),
     flat(missing).slice(0, 200));

  // --- 2. Umschalten: die ganze Kette -------------------------------------- //
  calls.length = 0;
  d.getElementById('lang-btn').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(300);

  ok('Der Sprachknopf schaltet um', inPage(w, 'LANG') === 'de', `LANG = ${inPage(w, 'LANG')}`);
  ok('…holt den Reiter neu', worldCalls().length > 0, JSON.stringify(calls.map(c => c[1])));
  ok('…und fragt in der NEUEN Sprache',
     allAsk(worldCalls(), 'de'),
     `${worldCalls().join(', ')} — der PATCH ins Konto läuft absichtlich ohne `
     + '`await`, die Anfrage darf also nicht auf ihn warten');
  txt = flat(d.getElementById('world-checklist'));
  ok('…und der Reiter steht danach deutsch da',
     /Nordamerika/.test(txt) && !/North America/.test(txt), txt.slice(0, 200));

  // Die Gegenrichtung: die Sprache wandert trotzdem ins Konto — sie steuert den
  // Ortsnamen-Lauf im Server, der keinen Aufrufer hat, den man fragen könnte.
  ok('Die Sprache wandert weiterhin ins Konto',
     calls.some(([m, p]) => m === 'PATCH' && /auth\/me\/settings/.test(p)),
     'ohne sie fragt der Ortsnamen-Lauf Nominatim in der alten Sprache');

  // --- 3. Die Ranglisten und ihre Merkzelle -------------------------------- //
  //
  // Der Zustand wird HERGESTELLT: erst ansehen (damit die Merkzelle gefüllt
  // ist), dann umschalten. Ohne den ersten Schritt greift die Merkzelle nie,
  // und der Wächter prüfte genau die Falle nicht, für die es ihn gibt.
  d.querySelector('.nav-item[data-view="stats"]')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(250);
  d.querySelector('#stats-tabs [data-stats="tops"]')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(250);

  let tops = flat(d.getElementById('stats-tops'));
  ok('Die Ranglisten stehen deutsch da', /Griechenland/.test(tops), tops.slice(0, 200));
  ok('…und ihre Anfrage nennt die Sprache',
     allAsk(topsCalls(), 'de'),
     topsCalls().join(', '));

  calls.length = 0;
  d.getElementById('lang-btn').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(350);

  ok('Ein Sprachwechsel holt die Ranglisten NEU',
     topsCalls().length > 0,
     'der Bestandsstempel ist derselbe geblieben — hängt die Merkzelle nur an '
     + 'ihm, gilt der Reiter als „schon geladen" und bleibt in der alten Sprache');
  ok('…in der neuen Sprache',
     allAsk(topsCalls(), 'en'), topsCalls().join(', '));
  tops = flat(d.getElementById('stats-tops'));
  ok('…und die Liste steht danach englisch da',
     /Greece/.test(tops) && !/Griechenland/.test(tops), tops.slice(0, 200));

  w.close();
  console.log(fail ? `\nF10/Welt: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nF10/Welt: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
