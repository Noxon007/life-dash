// F21 / Anmerkung 145 — die Lücken-Ansicht sagt, worüber sie berichtet.
//
// **Der teuerste Defekt hier wäre kein leerer Bildschirm, sondern eine
// glaubwürdige Zahl über die falsche Menge.** „87 % bekannt" ist eine
// beruhigende Auskunft — und sie bedeutet etwas völlig anderes, je nachdem, ob
// über ein LEBEN berichtet wird (Geburts-Meilenstein vorhanden) oder nur über
// den Zeitraum, in dem jemand etwas erfasst hat. Beides ist richtig; das eine
// zu zeigen und das andere zu behaupten ist der Fehler, den es hier zu
// verhindern gilt, und man sieht ihn dem Bildschirm nicht an.
//
// Fünf Zusagen:
//
//   1. **Der Kopf nennt den Bezug.** Mit Meilenstein „seit deiner Geburt",
//      ohne ihn die beiden Ecktage — und dann steht dabei, wie man es ändert.
//   2. **Der Deckel wird genannt.** Zwanzig Strecken sehen aus wie die ganze
//      Wahrheit, wenn niemand sagt, dass es vierhundert sind (A40).
//   3. **Die Herkunft des Wissens steht dabei** — erfasst gegen abgeleitet.
//      Eine Abdeckung, die zu 90 % aus einem Wohnort stammt, ist eine andere
//      Aussage als eine, die aus Einträgen kommt (Anmerkung 143).
//   4. **Der Klick führt dorthin, wo die Lücke zu schließen ist**, also ins
//      Wohnort-Formular mit übernommenen Daten — nicht in einen Zeitstrahl,
//      der an dieser Stelle per Definition leer ist.
//   5. **Ein Fehlschlag gilt nicht als beantwortet**, sonst ist ein einmaliger
//      Netzfehler eine dauerhaft leere Ansicht (dieselbe Umkehrung der
//      Endlos-Falle wie in `loadStatsTops`).
//
// Geprüft wird die ANZEIGE, nicht der deutsche Quelltext: unter jsdom startet
// die Seite englisch (Anmerkung 116/160).
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-gaps-view.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// Unverwechselbare Zahlen (Regel aus check-a46-visit-split.js): 7 331 und 4 219
// können aus keinem Datum und keiner Zählung dieser Seite stammen.
const TOTAL = 7331;
const RECORDED = 312;
const DERIVED = 4219;

const REPORT = {
  from: '1994-03-02', to: '2014-05-01', since_birth: true,
  total_days: TOTAL, known_days: RECORDED + DERIVED,
  unknown_days: TOTAL - RECORDED - DERIVED,
  recorded_days: RECORDED, baseline_days: DERIVED,
  stretch_count: 417,
  stretches: [{ from: '1996-01-05', to: '1996-08-11', days: 220 },
              { from: '2001-02-01', to: '2001-04-02', days: 61 }],
  per_year: [[1994, 300, 305], [1995, 0, 365]],
};

function makeDom(state) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      const base = new Proxy(function () { return base; }, {
        get: () => base, apply: () => base,
      });
      w.L = base;
      w.localStorage.setItem('ld_stats_pane', 'gaps');
      w.fetch = (u, opt) => {
        const p = String(u);
        state.calls.push([(opt && opt.method) || 'GET', p]);
        let body = [];
        if (/stats\/gaps/.test(p)) {
          if (state.gapsFail) return Promise.reject(new TypeError('Failed to fetch'));
          body = state.report;
        } else if (/stats\/overview/.test(p)) {
          body = { counts: {}, per_year: [], per_category: [], top_places: [],
                   top_cities: [], top_animals: [], extremes: {}, weather_days: 0,
                   rain_days_per_year: [], baseline_days: DERIVED };
        } else if (/stats\/toplists/.test(p)) {
          body = { weather: {}, places: [], cities: [], countries: [], years: [],
                   categories: [], streaks: {} };
        } else if (/stats\/widgets/.test(p)) body = [];
        else if (/events\/index/.test(p)) {
          body = { total: 1, dated: 1, undated: 0, unconfirmed: 0, fuzzy: 0,
                   years: [], visits: 0, photo_events: 0, machine_proposals: 0,
                   revision: 'r1', baseline_days: DERIVED, baseline_years: [] };
        } else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/api\/events\?/.test(p)) body = [];
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
const inPage = (w, code) => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };
const num = s => s.replace(/[ ., ]/g, '');   // 7.331 / 7,331 / 7 331

setTimeout(async () => {
  // --- 1. Mit Geburts-Meilenstein ----------------------------------------- //
  {
    const state = { calls: [], report: REPORT };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    await w.loadStatsGaps(true);
    await wait(80);
    const box = d.getElementById('stats-gaps');
    const text = num(box.textContent);

    ok('Die Ansicht berichtet über das ganze Leben',
       /birth|Geburt/i.test(box.textContent),
       box.textContent.slice(0, 200));
    ok('…und nennt den Bezugszeitraum in Tagen', text.includes(String(TOTAL)),
       `${TOTAL} fehlt in: ${text.slice(0, 220)}`);

    // (3) Woher das Wissen kommt — sonst liest sich eine Abdeckung aus einem
    //     Wohnort wie eine aus Einträgen.
    ok('Erfasst und abgeleitet stehen getrennt da',
       text.includes(String(RECORDED)) && text.includes(String(DERIVED)),
       text.slice(0, 260));

    // (2) Der Deckel.
    ok('Der Deckel wird genannt', text.includes('417') && text.includes('2'),
       `417 Strecken, gezeigt 2 — steht das da? ${text.slice(0, 260)}`);

    const rows = [...box.querySelectorAll('[data-gap-from]')];
    ok('Jede Strecke ist eine Zeile', rows.length === 2, `${rows.length}`);
    ok('…die längste zuerst',
       rows[0] && rows[0].dataset.gapFrom === '1996-01-05',
       rows.map(r => r.dataset.gapFrom).join(', '));

    // (4) Der Klick führt ins Wohnort-Formular, nicht in einen leeren
    //     Zeitstrahl.
    rows[0].dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(60);
    ok('Der Klick übernimmt den Zeitraum in das Wohnort-Formular',
       inPage(w, "document.getElementById('bl-from').value") === '1996-01-05'
       && inPage(w, "document.getElementById('bl-to').value") === '1996-08-11',
       `von=${inPage(w, "document.getElementById('bl-from').value")} `
       + `bis=${inPage(w, "document.getElementById('bl-to').value")} — eine Lücke `
       + 'ist per Definition leer, ein Sprung in den Zeitstrahl zeigte dort nichts');
    ok('…und öffnet die Seite, auf der das Formular steht',
       d.getElementById('view-admin').classList.contains('active'),
       'sonst liegt der übernommene Zeitraum auf einer Seite, die niemand sieht');
    w.close();
  }

  // --- 2. Ohne Geburts-Meilenstein ---------------------------------------- //
  {
    const state = { calls: [], report: { ...REPORT, since_birth: false } };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    await w.loadStatsGaps(true);
    await wait(80);
    const box = d.getElementById('stats-gaps');
    ok('Ohne Meilenstein wird NICHT „seit deiner Geburt" behauptet',
       !/since your birth|seit deiner Geburt/i.test(box.textContent),
       box.textContent.slice(0, 200));
    ok('…und die Ansicht sagt, wie man das ändert',
       /milestone|Meilenstein/i.test(box.textContent),
       'eine Ansicht, die weniger zeigt, als sie könnte, muss den Grund nennen (A40)');
    w.close();
  }

  // --- 3. Ein Fehlschlag gilt nicht als beantwortet ------------------------ //
  //
  // **Erst erfolgreich, dann fehlgeschlagen** — und das ist der ganze Test.
  // Im ersten Anlauf stand hier nur der Fehlschlag, und die Zusicherung war
  // grün, auch mit herausgenommenem `statsGapsFor = null`: die Kennung war ja
  // von Anfang an `null`. Geprüft wurde damit der Startwert, nicht das
  // Vergessen (Anmerkung 108).
  {
    const state = { calls: [], report: REPORT, gapsFail: false };
    const w = makeDom(state).window;
    await wait(200);
    await w.loadStatsGaps(true);
    await wait(80);
    ok('Ein erfolgreicher Abruf wird vermerkt',
       inPage(w, 'statsGapsFor') === 'r1',
       `${inPage(w, 'statsGapsFor')} — sonst prüft der Rest dieses Blocks nichts`);

    state.gapsFail = true;
    await w.loadStatsGaps(true);
    await wait(80);
    ok('…und ein Fehlschlag danach löscht die Marke wieder',
       inPage(w, 'statsGapsFor') === null,
       `${inPage(w, 'statsGapsFor')} — sonst ist ein einmaliger Netzfehler eine `
       + 'dauerhaft leere Ansicht, die als „für diesen Stand geladen" gilt');
    w.close();
  }

  console.log(fail ? `\nLücken-Ansicht: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nLücken-Ansicht: alles grün');
  process.exit(fail ? 1 : 0);
}, 60);
