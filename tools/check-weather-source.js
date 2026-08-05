// Anmerkung 186 — die Wetterquelle steht fest, und die Oberfläche sagt es.
//
// **Warum das ein Wächter ist und keine Selbstverständlichkeit.** Gemessen am
// 27.06.2026 in Hamburg, gegen 39,1 °C einer DWD-Station:
//
//     ohne Modellangabe (bis 0.39)   31,3 °C   ← der Dienst wählte selbst
//     ERA5                           37,6 °C
//
// Und die Wahl des Dienstes hing am ALTER des Tages: für 1990 und 1962
// antwortete dieselbe Anfrage aus ERA5-Land. Ein Archiv über ein Leben verglich
// damit zwei Modelle miteinander. Der Defekt wäre also kein Fehler, sondern
// eine Zahl, die plausibel aussieht — die teuerste Sorte in diesem Projekt.
//
// Drei Zusagen, und die dritte ist die, an die niemand denkt:
//
//   1. **Der Server nennt sein Modell** (`/health` → `weather_model`), und
//      `services/weather.py` schickt es wirklich als `models=` mit. Ein
//      Konstantenname allein beweist nichts — geprüft wird die ANFRAGE.
//   2. **Die Oberfläche sagt, was die Zahl ist**, und zwar dort, wo man sie
//      liest: an der Tageszeile, unter den Wetter-Ranglisten und im
//      Verwaltungs-Abschnitt.
//   3. **Der Modellname steht NICHT im Frontend.** Er kommt aus `/health`.
//      Eine fest eingetragene Zeichenkette wäre beim nächsten Quellenwechsel
//      eine Herkunftsangabe, die das Falsche behauptet — schlimmer als keine.
//      Deshalb prüft dieser Wächter mit einem ERFUNDENEN Modellnamen: taucht
//      er in der Anzeige auf, liest die Oberfläche wirklich den Server.
//
// Aufruf aus dem Repo-Wurzelverzeichnis:
//   node tools/check-weather-source.js [frontend/index.html] [backend/app/services/weather.py]
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const py = fs.readFileSync(process.argv[3] || 'backend/app/services/weather.py', 'utf8');

// Unverwechselbar: „xq5" kann aus keinem echten Modellnamen und keiner
// Zeichenkette der Oberfläche stammen.
const FAKE_MODEL = 'xq5test';

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

// --- 1. Der Server: Konstante UND Anfrage --------------------------------- //
const m = py.match(/^WEATHER_MODEL\s*=\s*"([^"]+)"/m);
ok('services/weather.py legt ein Modell fest', !!m,
   'ohne `models=` waehlt Open-Meteo selbst — und zwar je nach Alter des Tages '
   + 'verschieden');
ok('…und schickt es als `models` mit',
   /"models":\s*WEATHER_MODEL/.test(py),
   'die Konstante allein beweist nichts: sie muss in der ANFRAGE stehen, sonst '
   + 'ist sie Dokumentation ueber etwas, das nicht passiert');
ok('…und es ist ERA5', m && m[1] === 'era5',
   `${m && m[1]} — ERA5 ist die einzige Quelle, die 1940 bis heute, weltweit, `
   + 'Land UND Wasser abdeckt (ERA5-Land liefert ueber See und selbst fuer '
   + 'Paxos nichts, ICON-D2 gibt es erst ab 2021 und nur fuer Deutschland)');

// --- 2. Die Oberfläche liest den Server ----------------------------------- //
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    const base = new Proxy(function () { return base; }, {
      get: (_t, k) => (k === 'getZoom' ? () => 6 : base), apply: () => base,
    });
    w.L = base;
    w.fetch = (u) => {
      const p = String(u);
      let body = [];
      if (/\/health/.test(p)) {
        body = { version: '0.39.0', display_version: '0.39.0-dev',
                 ai_provider: 'mock', weather_model: FAKE_MODEL };
      } else if (/events\/index/.test(p)) {
        body = { total: 0, dated: 0, undated: 0, unconfirmed: 0, fuzzy: 0,
                 visits: 0, photo_events: 0, machine_proposals: 0, years: [] };
      } else if (/auth\/config/.test(p)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
      else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(p)) body = [];
      else if (/\/api\/jobs/.test(p)) body = [];
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
  },
});

const wait = ms => new Promise(r => setTimeout(r, ms));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  await wait(400);

  ok('Die Oberflaeche uebernimmt das Modell aus /health',
     w.eval('WX_MODEL') === FAKE_MODEL,
     `„${w.eval('WX_MODEL')}" — stuende hier der echte Name, waere er im `
     + 'Frontend fest eingetragen und ginge beim naechsten Wechsel schweigend '
     + 'daneben');

  const note = w.eval('wxSourceNote()');
  ok('…und nennt ihn im Herkunftssatz',
     typeof note === 'string' && note.toLowerCase().includes(FAKE_MODEL),
     `„${note}"`);
  ok('…der auch sagt, dass es KEINE Messung ist',
     /Messung|station|Thermometer|thermometer/i.test(note || ''),
     `„${note}" — „Modellwert" allein beantwortet die Frage nicht, die sich `
     + 'jemand vor einer Rekord-Kachel stellt');
  ok('Ohne Antwort vom Server bleibt der Satz WEG',
     w.eval('(function () { const keep = WX_MODEL; WX_MODEL = ""; '
            + 'const r = wxSourceNote(); WX_MODEL = keep; return r; })()') === '',
     'eine Quelle zu behaupten, die man nicht kennt, ist schlimmer als zu '
     + 'schweigen');

  // Der Verwaltungs-Abschnitt: dort wird der Lauf ausgeloest.
  ok('Der Wetter-Abschnitt zeigt die Herkunft',
     (d.getElementById('wx-source') || {}).textContent
       ?.toLowerCase().includes(FAKE_MODEL),
     `„${(d.getElementById('wx-source') || {}).textContent}"`);

  // Die Rekord-Listen: dort steht „waermster Tag" mit einer Zahl.
  w.eval(`renderStatsTops({ weather: { hot: [{ date_start: '2026-06-27', value: 37.6,
            place: 'Hamburg', title: 'Tag' }] }, streaks: {}, cities: [], countries: [],
            places: [], years: [], categories: [] })`);
  const tops = d.getElementById('stats-tops');
  ok('…und die Wetter-Ranglisten ebenfalls',
     tops && tops.textContent.toLowerCase().includes(FAKE_MODEL),
     'A40: „38,4 °C" liest sich wie ein Thermometerwert, und genau dort wird '
     + 'die Frage gestellt');

  // Und der Knopf, der einen Bestand umstellt.
  const btn = d.getElementById('btn-weather-refetch');
  ok('Es gibt einen Weg, Altbestand umzustellen', !!btn,
     '`_add_weather` ueberschreibt nie — ohne diesen Knopf bliebe ein Bestand '
     + 'fuer immer aus der alten, gemischten Quelle');

  console.log(fail ? `\nWetterquelle: ${fail} Pruefung(en) fehlgeschlagen`
                   : '\nWetterquelle: alles gruen');
  process.exit(fail ? 1 : 0);
}, 60);
