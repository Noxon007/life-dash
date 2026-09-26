// Was kostet der Zeitstrahl im ECHTEN Browser — und springt er beim Nachladen?
//
// `measure-timeline.js` misst in jsdom: Zeichenketten bauen, HTML parsen,
// Knoten anlegen. Layout und Malen sieht es nicht, und seine Attrappe kennt
// weder Wetter noch Fotoleisten noch Wohnort-Tage. Anmerkung 227 hat gezeigt,
// was das kostet: jsdom meldete für 1.800 Einträge im Tages-Zoom 172 ms und
// 8.253 Knoten, der Demo-Bestand in Chrome hatte 44.500 Knoten und brauchte
// 435 ms bis zum Frame — zwei Drittel davon LAYOUT, also genau der Teil, den
// jsdom nicht misst. Unter vierfacher CPU-Drossel (grob ein Handy): 2,5 s je
// nachgeladener Seite.
//
// **Und der zweite Teil misst etwas, das keine Zeitmessung zeigt: den
// Sprung.** Seit `content-visibility` merkt sich der Browser Höhen am Element;
// ein Neuaufbau, der sie verliert, ist schnell UND unbenutzbar. Der erste
// Entwurf war genau das — die Ansicht sprang beim Nachladen um 205.000
// Pixel, und jede Zeitmessung war dabei grün.
//
// Zuletzt gemessen (2026-09-26, Demo-Bestand, Tages-Zoom, Seite 6 = 1.800
// Einträge), jeweils bis zum Frame; Sprung an einer Gruppe INNERHALB der
// geladenen Einträge:
//
//                         Drossel 1×   Drossel 4×   Knoten   Sprung
//   vor Anmerkung 227       435 ms      2.511 ms    44.500   0 px *
//   content-visibility       94 ms        589 ms    44.500   ~205.000 px
//   + Höhen mitnehmen,
//     Fenster begrenzt       65 ms        363 ms    29.969   0 px
//
//   * Unterhalb der geladenen Einträge sprang schon die alte Fassung, um
//     ~48.000 px: dort standen Wohnort-Tage aus Jahren, deren Einträge noch
//     nicht geladen waren, und die nächste Seite schob sie dazwischen. Das
//     Fenster endet jetzt am ältesten geladenen Eintrag — daher auch die
//     14.500 Knoten weniger.
//
// Was bleibt, ist der JavaScript-Aufbau (50 / 284 ms), der mit jeder Seite
// wächst, weil `renderTimelineList` die GANZE Liste neu baut. Das ist der
// offene Rest aus Anmerkung 179 — und das Layout ist ihm nicht mehr im Weg.
//
// Braucht einen laufenden Server MIT Demo-Bestand (eine leere Datenbank zeigt
// die Größenordnung nicht) und ein installiertes Chrome/Chromium. Kein
// Zusatzpaket: Node 22 bringt WebSocket mit, gesprochen wird das
// DevTools-Protokoll direkt.
//
//   node tools/measure-timeline-chrome.js [URL] [Seiten] [Drossel]
//   CHROME=/pfad/zu/chrome  wenn es nicht am üblichen Ort liegt
//   WIDTH=390               Handybreite statt 1280
const { spawn } = require('child_process');
const os = require('os'), path = require('path'), fs = require('fs');

const URL_ = process.argv[2] || 'http://127.0.0.1:8123/';
const PAGES = Number(process.argv[3] || 6);
const THROTTLE = Number(process.argv[4] || 1);
const WIDTH = Number(process.env.WIDTH || 1280);
const CHROME = process.env.CHROME || [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].find(p => fs.existsSync(p));
if (!CHROME) { console.error('Kein Chrome gefunden — CHROME=/pfad setzen.'); process.exit(2); }

const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'lifedash-cdp-'));
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=0`,
  `--user-data-dir=${prof}`, '--no-first-run', `--window-size=${WIDTH},900`, 'about:blank'],
  { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const done = code => {
  chrome.kill();
  setTimeout(() => { try { fs.rmSync(prof, { recursive: true, force: true }); } catch (_) {} process.exit(code); }, 500);
};

(async () => {
  // Port 0: Chrome wählt selbst und schreibt ihn ins Profil. Ein fester oder
  // zufälliger Port landet auf Windows gern in einem reservierten Bereich
  // (Hyper-V sperrt ganze Blöcke), und dann antwortet schlicht niemand.
  let wsUrl;
  for (let i = 0; i < 75 && !wsUrl; i++) {
    try {
      const port = fs.readFileSync(path.join(prof, 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
      const list = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      wsUrl = (list.find(t => t.type === 'page') || {}).webSocketDebuggerUrl;
    } catch (_) {}
    if (!wsUrl) await sleep(200);
  }
  if (!wsUrl) throw new Error('Chrome antwortet nicht auf dem DevTools-Port');
  const ws = new WebSocket(wsUrl);
  await new Promise(r => ws.addEventListener('open', r));
  let id = 0; const wait = new Map();
  ws.addEventListener('message', m => {
    const d = JSON.parse(m.data);
    if (d.id && wait.has(d.id)) { wait.get(d.id)(d); wait.delete(d.id); }
  });
  const send = (method, params = {}) => new Promise(r => {
    const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params }));
  });
  const ev = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails));
    return r.result.result.value;
  };
  const idle = `new Promise(async r => { while (tl.loading) await new Promise(q => setTimeout(q, 50)); r(); })`;

  await send('Page.enable');
  if (WIDTH < 800) {
    await send('Emulation.setDeviceMetricsOverride',
      { width: WIDTH, height: 844, deviceScaleFactor: 1, mobile: true });
  }
  await send('Page.navigate', { url: URL_ });
  for (let i = 0; i < 100; i++) {
    await sleep(300);
    try { if (await ev(`typeof tl !== 'undefined' && document.readyState === 'complete'`)) break; } catch (_) {}
  }
  await sleep(1500);
  // Ein Willkommensdialog (Modulauswahl) liegt beim ersten Start darüber.
  await ev(`document.querySelectorAll('.modal-overlay.show,.sheet-overlay.show').forEach(o => o.style.display = 'none')`);
  await ev(`document.querySelector('.nav-item[data-view="timeline"]').click()`);
  await sleep(2500);
  await ev(`document.querySelector('#tl-zoom [data-zoom="day"]').click()`);
  await ev(idle);

  // --- 1. Zeit je Seite ----------------------------------------------------
  // Nur `renderTimeline()`, dann erzwungenes Layout, dann zwei Frames — der
  // Median aus drei Läufen. Der Abruf selbst zählt NICHT mit.
  const measure = `new Promise(res => {
    const t0 = performance.now();
    renderTimeline();
    const t1 = performance.now();
    void document.getElementById('timeline-list').getBoundingClientRect().height;
    const t2 = performance.now();
    requestAnimationFrame(() => requestAnimationFrame(() => res({
      events: tl.events.length, js: t1 - t0, layout: t2 - t1, frame: performance.now() - t0,
      nodes: document.getElementById('timeline-list').getElementsByTagName('*').length })));
  })`;
  if (THROTTLE > 1) await send('Emulation.setCPUThrottlingRate', { rate: THROTTLE });
  console.log(`Chrome headless · Tages-Zoom · ${WIDTH}px · CPU-Drossel ${THROTTLE}×`);
  console.log('Seite  Einträge   JS-Aufbau   Layout   bis Frame   Knoten');
  for (let p = 1; p <= PAGES; p++) {
    if (p > 1) { await ev(`loadTimeline(true)`); await ev(idle); }
    const runs = [];
    for (let k = 0; k < 3; k++) runs.push(await ev(measure));
    const m = runs.sort((a, b) => a.frame - b.frame)[1];
    console.log(`${String(p).padStart(5)}  ${String(m.events).padStart(8)}  ${m.js.toFixed(0).padStart(7)} ms  ${
      m.layout.toFixed(0).padStart(4)} ms  ${m.frame.toFixed(0).padStart(7)} ms  ${String(m.nodes).padStart(7)}`);
  }
  await send('Emulation.setCPUThrottlingRate', { rate: 1 });

  // --- 2. Springt die Ansicht beim Nachladen? ------------------------------
  // Lesen wie ein Mensch: in Schritten nach unten, damit jede Gruppe einmal
  // gezeichnet war (sonst gäbe es keine gemerkte Höhe, die verloren gehen
  // könnte). Dann die Gruppe merken, die oben steht, eine Seite nachladen und
  // fragen, wo sie danach steht.
  await ev(`new Promise(async r => { const c = document.querySelector('.content');
    for (let y = 0; y < c.scrollHeight * 0.6; y += 700) {
      c.scrollTop = y; await new Promise(q => requestAnimationFrame(() => requestAnimationFrame(q))); }
    r(); })`);
  await sleep(500);
  const top = key => `(() => { const c = document.querySelector('.content').getBoundingClientRect().top;
    const gs = [...document.querySelectorAll('#timeline-list .tl-year')];
    const g = ${key ? `gs.find(x => x.dataset.tlKey === ${JSON.stringify(key)})`
                    : `gs.find(x => x.getBoundingClientRect().bottom > c + 10)`};
    return g ? { key: g.dataset.tlKey, top: g.getBoundingClientRect().top - c } : null; })()`;
  const before = await ev(top());
  if (!before || !before.key) throw new Error('keine Gruppe mit Schlüssel im Bild');
  await ev(`loadTimeline(true)`); await ev(idle);
  await sleep(800);
  const after = await ev(top(before.key));
  const jump = after ? Math.round(after.top - before.top) : NaN;
  console.log(`\nSprung beim Nachladen: Gruppe ${before.key} von ${Math.round(before.top)} px `
    + `nach ${after ? Math.round(after.top) : '—'} px → ${jump} px`);
  ws.close();
  done(Math.abs(jump) <= 2 ? 0 : 1);
})().catch(e => { console.error(e); done(1); });
