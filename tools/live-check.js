// Integrationslauf gegen einen LAUFENDEN Server — das echte Frontend, echte
// Antworten. Die übrigen Prüfskripte arbeiten mit Attrappen; sie prüfen, was
// die App anfragt, nicht ob sie mit dem umgehen kann, was zurückkommt.
//
// Aufruf (Smoke-Server, nie die echte Datenbank):
//   cd backend
//   $env:DATABASE_URL="sqlite:///./_smoke.db"; $env:AUTH_MODE="dev"
//   <python> -m uvicorn app.main:app --port 8123
//   node tools/live-check.js http://127.0.0.1:8123
//
// Bewusst unabhängig davon, WIE VIEL in der Datenbank liegt: geprüft werden
// die Zusagen von A37, die immer gelten müssen — leer wie mit 200.000
// Einträgen. Nicht in `npm run check` verdrahtet, weil ein Server laufen muss.
process.env.TZ = 'Europe/Berlin';
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ORIGIN = (process.argv[2] || 'http://127.0.0.1:8123').replace(/\/$/, '');
const FILE = process.argv[3] || path.join(__dirname, '..', 'frontend', 'index.html');
const html = fs.readFileSync(FILE, 'utf8');
const errors = [];
const requests = [];

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: ORIGIN + '/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    // Leaflet kommt sonst vom CDN — hier eine Attrappe, die alles schluckt
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.fetch = (url, opts) => {
      const abs = String(url).startsWith('http') ? String(url) : ORIGIN + String(url);
      requests.push(abs.replace(ORIGIN, ''));
      return fetch(abs, opts);
    };
    w.addEventListener('error', e =>
      errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
    w.addEventListener('unhandledrejection', e =>
      errors.push('REJECT: ' + (e.reason && (e.reason.stack || e.reason.message) || e.reason)));
  },
});

const w = dom.window, d = w.document;
let fail = 0;
const ok = (n, c, extra = '') => {
  console.log((c ? '  ok   ' : '  FAIL ') + n + (extra ? '   [' + extra + ']' : ''));
  if (!c) fail++;
};
const txt = id => ((d.getElementById(id) || {}).textContent || '').trim();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const evCalls = () => requests.filter(u => u.startsWith('/api/events?'));

// **Auf die BEDINGUNG warten, nicht auf eine Zeitspanne.** Hier standen feste
// `sleep(600)` nach jedem Aufruf, und das ist auf dem eigenen Rechner immer
// genug gewesen. In der CI war es das nicht: der Zeitstrahl hatte seine
// Anfrage noch nicht abgeschickt, `evCalls()` war leer — und die beiden
// Prüfungen daneben meldeten trotzdem „bestanden", weil `.every()` über eine
// leere Liste wahr ist und „höchstens sechs Anfragen" bei null erst recht.
// Von drei Prüfungen über denselben Vorgang schlug genau die eine an, die
// `.some()` benutzt.
//
// Dieselbe Regel wie in `tools/pg-test.ps1`: es wird gewartet, bis die Lage
// eingetreten ist, mit einer großzügigen Obergrenze — eine Wartezeit, die
// knapp reicht, ist eine, die auf fremder Hardware nicht reicht.
const until = async (cond, ms = 10000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (cond()) return true;
    await sleep(50);
  }
  return false;
};

// **Läuft der Startaufbau noch?** `loadTimeline()` beginnt mit
// `if (tl.loading) return;` — wer sie ruft, während der Aufbau der Seite noch
// unterwegs ist, bekommt einen stillen Rückläufer und keine einzige Anfrage.
//
// Genau daran ist dieser Lauf in der CI hängengeblieben: das feste `sleep`
// oben reichte auf dem eigenen Rechner, um den Startaufbau abzuwarten, und auf
// dem Runner nicht. Der Wächter leerte dann die Anfrageliste (die Ereignis-
// Anfrage des Starts war da schon draußen und wurde mit weggeworfen), rief
// `loadTimeline()` ins Leere und sah nur noch die drei Nachlader des
// LAUFENDEN Aufbaus vorbeikommen — drei Anfragen, keine davon an
// `/api/events?`.
//
// `tl` ist ein `const` auf oberster Skriptebene und damit **keine
// Fenster-Eigenschaft** (CLAUDE.md führt dieselbe Falle für `OVERLAYS` und
// `LANG`): `w.tl` wäre stumm `undefined`, und die Wartebedingung wäre sofort
// wahr — der Wächter hätte sich seinen eigenen Fehler bestätigt. Über
// `w.eval` sieht man die Bindung so, wie die Seite sie sieht.
const tlIdle = () => {
  try { return w.eval('tl.loading') === false; } catch (_) { return false; }
};

(async () => {
  await sleep(500);                        // dem Startskript einen Anlauf geben
  const idx = await fetch(ORIGIN + '/api/events/index').then(r => r.json());
  console.log(`Server ${ORIGIN} — ${idx.total} Einträge, davon ${idx.visits} Besuche\n`);

  // Erst wenn der Startaufbau durch ist, ist ein eigener Aufruf überhaupt einer.
  const idle = await until(tlIdle, 30000);
  ok('der Startaufbau der Seite kommt zum Ende', idle,
     idle ? '' : 'tl.loading blieb wahr — loadTimeline() täte hier gar nichts');

  requests.length = 0;
  await w.loadTimeline();
  await until(() => evCalls().length > 0);

  // --- Die Zusage von A37: nie wieder alles auf einmal --------------------
  // Zuerst, dass es überhaupt etwas zu beurteilen GIBT. Ohne diese Zeile sind
  // die beiden `every`-Prüfungen darunter über einer leeren Liste wahr, und
  // ein Zeitstrahl, der gar nichts lädt, käme als „alles bestanden" durch.
  ok('der Zeitstrahl fragt den Server überhaupt', evCalls().length > 0,
     requests.length + ' Anfragen insgesamt');
  ok('kein Abruf ohne Grenze (nie die ganze Geschichte)',
     evCalls().length > 0 &&
     evCalls().every(u => /limit=\d+/.test(u) || /(vague|parent|category|from|to)=/.test(u)),
     evCalls().join(' '));
  ok('Besuche filtert der Server, nicht der Browser',
     evCalls().some(u => /visits=0/.test(u)));
  ok('höchstens eine Handvoll Anfragen für den ersten Bildschirm',
     evCalls().length > 0 && evCalls().length <= 6, evCalls().length + ' Anfragen');

  // --- Zahlen über den Gesamtbestand kommen aus dem Server ----------------
  await w.loadToday();
  await until(() => /\d/.test(txt('today-events')));
  const shown = parseInt(txt('today-events').replace(/[^\d]/g, ''), 10) || 0;
  ok('„Heute" zeigt den Gesamtbestand, nicht das geladene Fenster',
     shown === idx.total, `${txt('today-events')} vs. Index ${idx.total}`);

  await w.loadStats();
  await until(() => /\d/.test(txt('stat-events')));
  const statEvents = parseInt(txt('stat-events').replace(/[^\d]/g, ''), 10) || 0;
  ok('Statistik zählt den Gesamtbestand',
     statEvents === idx.total, `${txt('stat-events')} vs. ${idx.total}`);
  ok('Statistik holt KEINE Ereignisliste (rechnet der Server)',
     !requests.some(u => /^\/api\/events\?(?!.*(limit|from|to|vague|parent)).*$/.test(u)));
  ok('Wetter-Kachel zeigt Wert oder Strich, nie NaN/undefined',
     !/NaN|undefined/.test(txt('stat-hot')), txt('stat-hot'));

  // --- Anmerkung 220: der Reiter muss auch ANKOMMEN ----------------------
  // Bis hierher prüfte dieser Lauf, was die Statistik ANFRAGT, und nie, wie
  // lange sie dazu braucht. Genau darin lag Anmerkung 220: die Zahlen waren
  // richtig, die Anfragen waren richtig, und der Reiter brauchte neunundzwanzig
  // Sekunden. Alle Prüfungen des Projekts waren dabei grün.
  //
  // **Eine Zeitmessung über einen leeren Bestand sagt nichts** — deshalb wird
  // erst ab einer Größe geurteilt, bei der der Unterschied nicht mehr im
  // Rauschen liegt. Darunter wird die Zahl nur berichtet: eine Prüfung, die
  // beim Fehlen ihrer Voraussetzung stillschweigend „bestanden" meldet, ist
  // die Sorte, die dieses Projekt teuer bezahlt hat.
  const BUDGET = parseInt(process.env.LIVE_BUDGET_MS || '8000', 10);
  const MIN_ROWS = 1000;
  for (const path of ['/api/stats/overview', '/api/stats/toplists']) {
    const t0 = Date.now();
    await fetch(ORIGIN + path).then(r => r.json());
    const ms = Date.now() - t0;
    if (idx.total >= MIN_ROWS) {
      ok(`${path} bleibt im Zeitbudget`, ms <= BUDGET,
         `${ms} ms von ${BUDGET} ms bei ${idx.total} Einträgen`);
    } else {
      console.log(`  --   ${path}: ${ms} ms bei nur ${idx.total} Einträgen ` +
                  `— zu wenig für ein Urteil (ab ${MIN_ROWS} wird geprüft)`);
    }
  }

  // --- Die Karte hat ihren eigenen Endpunkt ------------------------------
  requests.length = 0;
  await w.openMapView();
  await until(() => requests.some(u => u.startsWith('/api/events/map')));
  ok('Karte nutzt /api/events/map', requests.some(u => u.startsWith('/api/events/map')));
  ok('Karten-Grundabruf ohne Wetter',
     requests.filter(u => u.startsWith('/api/events/map') && !/weather=1/.test(u)).length > 0);

  // --- Und nichts davon wirft im Vorbeigehen Fehler ----------------------
  const fatal = errors.filter(e => !/Not implemented|CSS|stylesheet|leaflet|geolocation/i.test(e));
  ok('keine unbehandelten Fehler', fatal.length === 0, fatal.slice(0, 2).join(' | '));

  console.log(fail ? `\n${fail} FEHLER` : '\nLive-Lauf: alles bestanden');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('ABBRUCH:', e); process.exit(1); });
