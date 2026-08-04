// Anmerkung 179 — die Sammel-Ansichten des Zeitstrahls kommen aus dem INDEX.
//
// Gemeldet: „ältere Einträge laden finde ich schwierig umgesetzt. man kann
// nicht einfach runterscrollen und es dauert alles lange."
//
// Die Messung (`tools/measure-timeline.js`) hat gezeigt, dass es nicht das
// Zeichnen war: im Jahres-Zoom besteht die Liste aus zwei Dutzend Knoten und
// ist in 4 ms gebaut. Genau das ist das Problem — eine Seite von 300
// Ereignissen deckt bei einem Bestand mit importierten Besuchen ein paar Tage
// ab und wird zu EINER Überschrift. Die Seite ist zu kurz zum Scrollen, der
// Nachlade-Auslöser feuert nie, und der Weg nach 2004 sind hundert Klicks auf
// „▼ Ältere Einträge laden".
//
// Vier Zusagen:
//   1. **Jedes Jahr steht sofort da**, auch ohne dass ein einziger Eintrag
//      daraus geladen wäre — die Verteilung liegt seit A37 im Index.
//   2. **Mit seiner echten Zahl**, und zwar der, die zu den eingeblendeten
//      Ebenen passt: wer die automatisch erfassten ausblendet, darf an 2016
//      nicht „4.812" lesen und drei finden (Anm. 92, eine Ebene höher).
//   3. **Ein Klick holt genau dieses Jahr** — eine Anfrage mit `from`/`to`,
//      nicht hundert Seiten auf dem Weg dorthin.
//   4. **Bei einer Suche oder einem Tag-/Stadtfilter gilt das Gerüst NICHT.**
//      Das sind Auswahlen über EINTRÄGE; der Index kennt sie nicht, und ein
//      Gerüst aus allen Jahren behauptete dort Treffer, die es nicht gibt.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-tl-index.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// Zwanzig Jahre Bestand. Nur 2024 ist „geladen" (die erste Seite); alles davor
// kennt ausschließlich der Index — genau die Lage, um die es geht.
const YEARS = [];
for (let y = 2005; y <= 2024; y++) {
  // Unverwechselbare Zahlen: 2016 trägt 4.812 gesamt, davon 112 von Hand.
  YEARS.push(y === 2016
    ? { year: y, count: 4812, manual: 112, visits: 4700, photos: 0 }
    : { year: y, count: 30, manual: 10, visits: 20, photos: 0 });
}
const LOADED = Array.from({ length: 10 }, (_, i) => ({
  id: 'e' + i, title: 'Eintrag ' + i, category: 'event', source: 'manual',
  date_start: `2024-12-${String(10 + i).padStart(2, '0')}T10:00:00`,
  date_precision: 'exact', confirmed: 'confirmed', entities: [], metrics: [], media: [],
  location: { id: 'l1', name: 'Detmold', lat: 51.93, lng: 8.87, city: 'Detmold' },
}));
// Was ein aufgeklapptes Jahr zurückgibt — erkennbar an einem eigenen Titel.
const YEAR_2016 = [{
  id: 'y16', title: 'Aus dem Jahr 2016', category: 'trip', source: 'manual',
  date_start: '2016-06-01T10:00:00', date_precision: 'exact', confirmed: 'confirmed',
  entities: [], metrics: [], media: [],
  location: { id: 'l2', name: 'Rom', lat: 41.9, lng: 12.5, city: 'Rom' },
}];

const eventCalls = [];

function makeDom() {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.__zoom = 6;
      const base = new Proxy(function () { return base; }, {
        get: (_t, k) => (k === 'getZoom' ? () => w.__zoom : base), apply: () => base,
      });
      w.L = base;
      w.fetch = u => {
        const p = String(u);
        let body = [];
        if (/api\/events\?/.test(p)) {
          eventCalls.push(p);
          body = /from=2016/.test(p) ? YEAR_2016
               : (/from=/.test(p) ? [] : LOADED);
        } else if (/events\/index/.test(p)) {
          body = { total: 5412, dated: 5412, undated: 0, unconfirmed: 0, fuzzy: 0,
                   visits: 5100, photo_events: 1, machine_proposals: 0, years: YEARS };
        } else if (/days\/media|days\/weather|days\/baseline/.test(p)) body = {};
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/api\/search/.test(p)) body = [];
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      };
    },
  });
}

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));

setTimeout(async () => {
  const w = makeDom().window, d = w.document;
  await wait(200);
  w.eval("tl.zoom = 'year';");
  await w.loadTimeline();
  await wait(200);
  const list = d.getElementById('timeline-list');
  const text = () => list.textContent;

  // --- 1. Jedes Jahr steht sofort da -------------------------------------- //
  const headers = [...list.querySelectorAll('.tl-year-label')].map(e => e.textContent.trim());
  ok('Alle zwanzig Jahre stehen da', headers.length >= 20,
     `${headers.length} Überschriften: ${headers.slice(0, 5).join(', ')} … — `
     + 'aus der geladenen Seite wäre es genau eine');
  ok('…auch das älteste', headers.some(h => h.startsWith('2005')),
     `${headers.join(', ')} — der Weg dorthin waren hundert Klicks`);
  ok('…und es wurde dafür NICHT geblättert',
     eventCalls.filter(p => /offset=[1-9]/.test(p)).length === 0,
     JSON.stringify(eventCalls));

  // --- 2. Mit der Zahl, die zu den Ebenen passt --------------------------- //
  // Voreingestellt sind die automatisch erfassten AUS. 2016 trägt 4.812
  // insgesamt, davon 112 von Hand — steht dort die große Zahl, klickt man ein
  // Jahr auf und findet ein Vierzigstel davon.
  ok('Ausgeblendete Ebenen zählen nicht mit',
     /112/.test(text()) && !/4[.,]812/.test(text()),
     'die große Zahl neben einer Ansicht, die sie nicht zeigt');
  w.eval('tl.showVisits = true;');
  w.renderTimeline();
  await wait(60);
  ok('Eingeblendet zählen sie sehr wohl mit', /4[.,]812/.test(text()),
     'sonst wäre die Zahl einfach nur eine andere feste Zahl');
  w.eval('tl.showVisits = false;');
  w.renderTimeline();

  // --- 3. Ein Klick holt genau dieses Jahr -------------------------------- //
  const row = [...list.querySelectorAll('[data-agg-group]')]
    .find(e => /2016/.test(e.textContent));
  ok('Das Jahr 2016 ist eine anklickbare Zeile', !!row, headers.join(', '));
  ok('…und sagt, dass es noch nicht geladen ist',
     !!row && /noch nicht geladen|not loaded/i.test(row.textContent),
     row && row.textContent);
  eventCalls.length = 0;
  row.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(300);
  const fetched = eventCalls.filter(p => /from=2016/.test(p));
  ok('Der Klick holt GENAU dieses Jahr', fetched.length === 1,
     JSON.stringify(eventCalls));
  ok('…mit from und to statt mit Seiten', fetched.length === 1
     && /from=2016-01-01/.test(fetched[0]) && /to=2016-12-31/.test(fetched[0]),
     fetched[0]);
  // Im Jahres-Zoom sind die Zeilen MONATE, nicht Karten — geprüft wird
  // deshalb, dass aus „noch nicht geladen" ein anfassbarer Monat geworden
  // ist. Auf den Ereignistitel zu prüfen hieße, eine Ansicht zu erwarten,
  // die diese Zoomstufe gar nicht zeigt.
  const row16 = [...list.querySelectorAll('[data-agg-group]')]
    .find(e => /2016/.test(e.textContent));
  ok('…und aus der Zeile wird ein anfassbarer Monat',
     !!row16 && !/noch nicht geladen|not loaded/i.test(row16.textContent)
     && /Juni|June/i.test(row16.textContent),
     row16 && row16.textContent.replace(/\s+/g, ' ').slice(0, 160));

  // --- 4. Bei einer Auswahl über EINTRÄGE gilt das Gerüst nicht ----------- //
  w.eval("tl.city = 'Rom';");
  w.renderTimeline();
  await wait(60);
  const cityHeaders = [...list.querySelectorAll('.tl-year-label')].map(e => e.textContent.trim());
  ok('Mit Stadtfilter kein Gerüst', cityHeaders.length < 20,
     `${cityHeaders.length} Überschriften — der Index weiß nichts über Städte, `
     + 'ein Gerüst behauptete dort Treffer');
  w.eval('tl.city = null;');
  w.eval("tl.query = 'irgendwas';");
  w.renderTimeline();
  await wait(60);
  ok('Mit Suche ebenso',
     [...list.querySelectorAll('.tl-year-label')].length < 20);
  w.eval("tl.query = '';");

  // --- 5. Die Fußzeile bietet nicht mehr an, was nichts bringt ------------ //
  w.renderTimeline();
  await wait(60);
  ok('Kein „Ältere Einträge laden" mehr im Jahres-Zoom',
     !d.getElementById('tl-load-more'),
     'genau der Knopf, den hundertmal zu drücken die Beschwerde war');
  // `tl.done` steht hier auf true (die Seite war kürzer als TL_PAGE) — dann
  // sagt die Fußzeile zu Recht „das ist der Anfang". Geprüft werden soll der
  // Fall, in dem es noch etwas zu holen GIBT.
  w.eval("tl.zoom = 'day'; tl.done = false;");
  w.renderTimeline();
  await wait(60);
  ok('…im Tages-Zoom aber sehr wohl', !!d.getElementById('tl-load-more'),
     'dort ist Blättern weiterhin der Weg — ein Gerüst über Tage gibt es nicht');

  console.log(fail ? `\nZeitstrahl-Index: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nZeitstrahl-Index: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
