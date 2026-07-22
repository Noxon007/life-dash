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
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
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

(async () => {
  await sleep(2500);                       // Startskript durchlaufen lassen
  const idx = await fetch(ORIGIN + '/api/events/index').then(r => r.json());
  console.log(`Server ${ORIGIN} — ${idx.total} Einträge, davon ${idx.visits} Besuche\n`);

  requests.length = 0;
  await w.loadTimeline();
  await sleep(600);

  // --- Die Zusage von A37: nie wieder alles auf einmal --------------------
  ok('kein Abruf ohne Grenze (nie die ganze Geschichte)',
     evCalls().every(u => /limit=\d+/.test(u) || /(vague|parent|category|from|to)=/.test(u)),
     evCalls().join(' '));
  ok('Besuche filtert der Server, nicht der Browser',
     evCalls().some(u => /visits=0/.test(u)));
  ok('höchstens eine Handvoll Anfragen für den ersten Bildschirm',
     evCalls().length <= 6, evCalls().length + ' Anfragen');

  // --- Zahlen über den Gesamtbestand kommen aus dem Server ----------------
  await w.loadToday();
  await sleep(600);
  const shown = parseInt(txt('today-events').replace(/[^\d]/g, ''), 10) || 0;
  ok('„Heute" zeigt den Gesamtbestand, nicht das geladene Fenster',
     shown === idx.total, `${txt('today-events')} vs. Index ${idx.total}`);

  await w.loadStats();
  await sleep(900);
  const statEvents = parseInt(txt('stat-events').replace(/[^\d]/g, ''), 10) || 0;
  ok('Statistik zählt den Gesamtbestand',
     statEvents === idx.total, `${txt('stat-events')} vs. ${idx.total}`);
  ok('Statistik holt KEINE Ereignisliste (rechnet der Server)',
     !requests.some(u => /^\/api\/events\?(?!.*(limit|from|to|vague|parent)).*$/.test(u)));
  ok('Wetter-Kachel zeigt Wert oder Strich, nie NaN/undefined',
     !/NaN|undefined/.test(txt('stat-hot')), txt('stat-hot'));

  // --- Die Karte hat ihren eigenen Endpunkt ------------------------------
  requests.length = 0;
  await w.openMapView();
  await sleep(1200);
  ok('Karte nutzt /api/events/map', requests.some(u => u.startsWith('/api/events/map')));
  ok('Karten-Grundabruf ohne Wetter',
     requests.filter(u => u.startsWith('/api/events/map') && !/weather=1/.test(u)).length > 0);

  // --- Und nichts davon wirft im Vorbeigehen Fehler ----------------------
  const fatal = errors.filter(e => !/Not implemented|CSS|stylesheet|leaflet|geolocation/i.test(e));
  ok('keine unbehandelten Fehler', fatal.length === 0, fatal.slice(0, 2).join(' | '));

  console.log(fail ? `\n${fail} FEHLER` : '\nLive-Lauf: alles bestanden');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('ABBRUCH:', e); process.exit(1); });
