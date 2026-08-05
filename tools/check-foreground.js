// F23 — jeder Lauf, den der BROWSER taktet, geht durch dasselbe Bauteil.
//
// Der gemeldete Zustand war nicht „kaputt", sondern uneinheitlich: manche
// Knöpfe zeigten einen Balken, manche einen Kreisel, manche gar nichts, und
// „Heute" lud sichtbar noch nach, nachdem die Ansicht schon stand. Die Ursache
// war kein Fehler an einer Stelle, sondern **zwei Wege, dasselbe Overlay zu
// füllen** (`showLoading`/`showProgress` neben dem Rest) plus sieben Aufrufe
// ohne `await` beim Ansichtswechsel.
//
// Ein Wächter für so etwas muss zwei Dinge tun, sonst prüft er nichts:
//   1. den ALTEN Weg verbieten — sonst kommt er beim nächsten Knopf zurück,
//      und zwar völlig unauffällig;
//   2. das Bauteil AUSFÜHREN und dabei den Zustand HERSTELLEN — ein Wächter,
//      der nur nachsieht, ob es die Funktion GIBT, ist grün, weil sie
//      existiert, nicht weil sie funktioniert.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-foreground.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

// ---- 1. Der alte Weg darf nicht zurückkommen ------------------------------
// Kommentarzeilen zählen nicht mit: der Quelltext ERKLÄRT, warum es die beiden
// Funktionen nicht mehr gibt, und eine Prüfung, die ihre eigene Begründung als
// Verstoß liest, verbietet das Aufschreiben statt die Sache.
const code = html.split('\n').filter(l => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n');
for (const gone of ['showLoading', 'showProgress']) {
  const uses = code.match(new RegExp(`\\b${gone}\\s*\\(`, 'g')) || [];
  ok(`„${gone}" gibt es nicht mehr`, uses.length === 0,
     `${uses.length} Vorkommen — der zweite Weg ins selbe Overlay ist wieder da; `
     + 'runForeground() benutzen (Titel, Rest-Schätzung, Abbrechen, Aufräumen inklusive)');
}

// ---- 2. Der Ansichtswechsel lädt über die Tabelle, nicht über if-Ketten ----
const goto = (html.match(/function gotoView\(v\)[\s\S]{0,3000}?\n\}/) || [''])[0];
// Nicht nur „kommt vor", sondern „der Lader läuft DARIN": ein `runForeground`
// irgendwo im Rumpf wäre grün, während der eigentliche Aufruf daneben steht.
ok('Der Ansichtswechsel benutzt das Bauteil',
   /runForeground\([\s\S]{0,400}?\bload\(/.test(goto),
   'gotoView() lädt wieder an der Fortschrittsanzeige vorbei');
ok('Der Ansichtswechsel kennt keine if-Kette mehr',
   !/if \(v === '\w+'\) load/.test(goto) && /VIEW_LOADERS\[v\]/.test(goto),
   'eine neue Ansicht ohne Eintrag fällt in einer Tabelle auf, in einer if-Kette nicht');

// ---- 1b. Jeder aufgerufene Pfad muss es im Backend geben ------------------
// Gefunden beim Rauchtest, nicht beim Lesen: die Oberfläche rief
// `/api/tracks/places/unresolved`, der Router trägt aber das Präfix `/api` —
// der Knopf hätte still 404 bekommen. Ein jsdom-Wächter kann die Antwort nicht
// prüfen, den PFAD aber schon, und zwar gegen die Datei, die ihn definiert.
// Genau die Naht zwischen zwei Dateien, die niemand zusammen liest.
const routerFile = process.argv[3] || 'backend/app/routers/tracks.py';
if (fs.existsSync(routerFile)) {
  const py = fs.readFileSync(routerFile, 'utf8');
  const prefix = (py.match(/APIRouter\(prefix="([^"]*)"/) || [])[1] || '';
  const routes = [...py.matchAll(/@router\.\w+\("([^"]+)"/g)]
    .map(m => prefix + m[1]);
  // Bewusst nach dem WORT gesucht und nicht nach dem erwarteten Präfix: der
  // Fehler bestand ja gerade darin, dass das Präfix falsch war. Ein Muster,
  // das das richtige Präfix voraussetzt, findet genau diesen Fall nie.
  const calls = [...code.matchAll(/['"`](\/api\/[a-z/]*places[^'"`?]*)/g)].map(m => m[1]);
  ok('Es werden überhaupt Orts-Pfade gerufen', calls.length >= 2,
     'Regex und Quelltext passen nicht mehr zusammen');
  for (const called of calls) {
    // Platzhalter (`${id}`) auf das Muster der Route abbilden.
    const norm = called.replace(/\$\{[^}]*\}/g, '{x}').replace(/\/$/, '');
    const known = routes.some(r => r.replace(/\{[^}]*\}/g, '{x}') === norm);
    ok(`Der Pfad „${called}" existiert im Backend`, known,
       `bekannt sind: ${routes.filter(r => r.includes('places')).join(', ') || '(keine)'}`);
  }
}

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  },
});

setTimeout(async () => {
  const w = dom.window;
  const d = w.document;
  const ov = d.getElementById('loading-overlay');
  ok('Das Overlay ist im Markup', !!ov);
  for (const id of ['loading-text', 'loading-note', 'loading-bar', 'loading-bar-fill',
                    'loading-meta', 'loading-cancel']) {
    ok(`… mit „${id}"`, !!d.getElementById(id),
       'ohne dieses Teil zeigt der Lauf weniger, als er weiß');
  }

  let run = null;
  try { run = w.eval('runForeground'); } catch (_) { /* nächste Prüfung */ }
  ok('runForeground ist erreichbar', typeof run === 'function');
  if (typeof run !== 'function') { finish(); return; }

  // ---- 3. Den Zustand HERSTELLEN: einen echten Lauf fahren ---------------
  // Das Overlay erscheint absichtlich erst nach FG_DELAY. Ein Wächter, der
  // sofort nachsieht, prüfte also die Verzögerung und nicht die Anzeige.
  const delay = w.eval('FG_DELAY');
  ok('Es gibt eine Anzeige-Verzögerung', typeof delay === 'number' && delay > 0,
     'ohne sie blitzt der Vollbild-Overlay bei jedem 100-ms-Wechsel auf');

  let seen = null;
  await run('Testlauf', async op => {
    await new Promise(r => w.setTimeout(r, delay + 60));
    op.step(30, 120, 'dritter Schritt');
    seen = {
      shown: ov.classList.contains('show'),
      title: d.getElementById('loading-text').textContent,
      note: d.getElementById('loading-note').textContent,
      width: d.getElementById('loading-bar-fill').style.width,
      meta: d.getElementById('loading-meta').textContent,
      cancelHidden: d.getElementById('loading-cancel').hidden,
    };
  }, { unit: 'Zeilen' });

  ok('Der Overlay erscheint, wenn es dauert', seen && seen.shown);
  ok('Er nennt den Vorgang', seen && seen.title === 'Testlauf');
  ok('Er sagt, was er gerade tut', seen && seen.note === 'dritter Schritt',
     'ein Balken ohne Satz ist eine Sanduhr');
  ok('Der Balken steht auf dem Anteil', seen && seen.width === '25%',
     `steht: ${seen && seen.width}`);
  ok('Die Zahlen stehen darunter', seen && /30/.test(seen.meta) && /120/.test(seen.meta),
     `steht: ${seen && seen.meta}`);
  ok('Abbrechen ist anklickbar', seen && seen.cancelHidden === false,
     'ein Lauf ohne Ausweg ist der Grund, warum Leute den Tab schließen');

  // ---- 4. Danach ist AUFGERÄUMT — auch das war vorher Handarbeit --------
  ok('Nach dem Lauf ist der Overlay weg', !ov.classList.contains('show'),
     'jeder Aufrufer musste bisher selbst an showLoading(false) denken');
  ok('… und der Balken zurückgesetzt',
     d.getElementById('loading-bar').style.display === 'none');
  ok('… und der Satz gelöscht', d.getElementById('loading-note').textContent === '');

  // ---- 5. Abbrechen bricht wirklich ab -----------------------------------
  let ran = 0, aborted = false;
  await run('Abbruch', async op => {
    for (let i = 0; i < 10; i++) {
      if (op.aborted) { aborted = true; return; }
      ran++;
      if (i === 2) d.getElementById('loading-cancel').click();
      await new Promise(r => w.setTimeout(r, 1));
    }
  }, { total: 10 });
  ok('Ein Klick auf Abbrechen hält den Lauf an', aborted && ran < 10,
     `es liefen ${ran} von 10 Etappen weiter — der Knopf tut nichts`);

  // ---- 6. Verschachtelung erzeugt kein zweites Overlay -------------------
  let innerSawSame = false;
  await run('Außen', async outer => {
    await run('Innen', inner => { innerSawSame = inner === outer; });
  });
  ok('Ein Lauf im Lauf benutzt denselben Vorgang', innerSawSame,
     'refreshAll() ruft fünf Lader — fünf Overlays wären fünfmal dasselbe Flackern');

  // ---- 7. Anmerkung 193: der Balken zählt ANFRAGEN, keine Abschnitte -----
  //
  // Gemeldet: „bei der Statistik kommt das Ladefenster, steht die ganze Zeit
  // auf 0/2 und ist dann direkt fertig, ohne auf einen Fortschritt zu
  // springen." Der Zähler war nicht falsch, er war unbeweglich: ein Schritt
  // umfasste vier gleichzeitige Anfragen, also stand er über die gesamte
  // Wartezeit auf 0.
  //
  // **Deshalb prüft der Wächter nicht, DASS eine Zahl dasteht, sondern dass
  // sie sich WÄHREND des Wartens ÄNDERT.** Das ist der Unterschied zwischen
  // „es gibt einen Balken" und „der Balken sagt etwas" — und einer
  // `step()`-Zeile sieht man ihn nicht an.
  const marks = [];
  const slow = ms => new Promise(r => w.setTimeout(r, ms));
  await run('Zähler', async op => {
    const timer = w.setInterval(() => marks.push(op.done), 10);
    await op.all([slow(40), slow(80), slow(120)], 'drei Anfragen');
    w.clearInterval(timer);
  });
  const stands = [...new Set(marks)];
  ok('Der Zähler bewegt sich WÄHREND des Wartens', stands.length >= 3,
     `gesehene Stände: ${stands.join(', ') || '(keine)'} — ein Zähler, der nur `
     + 'am Anfang und am Ende einen Wert hat, behauptet Stillstand');

  // Und die Stelle, aus der die Beschwerde kam: benutzt sie es auch? Ein
  // Doppel statt eines echten Laufs, weil die Zahlen dahinter hier niemanden
  // interessieren — nur, WIE der Fortschritt gemeldet wird.
  let bundle = 0, steps = 0;
  const spy = { note() {}, step() { steps++; }, check() {},
                all(list) { bundle = list.length; return Promise.all(list); } };
  try { await w.loadStats(spy); } catch (_) { /* die Zahlen fehlen, egal */ }
  ok('Die Statistik meldet jede ihrer Anfragen einzeln', bundle >= 4,
     `${bundle} gemeldete Anfragen bei ${steps} Abschnitten — vier Endpunkte `
     + 'auf einmal sind vier zählbare Dinge, nur ohne Reihenfolge');

  finish();

  function finish() {
    console.log(fail ? `\nVordergrund-Läufe: ${fail} Prüfung(en) fehlgeschlagen`
                     : '\nVordergrund-Läufe: alles grün');
    process.exit(fail ? 1 : 0);
  }
}, 300);
