// A40 (Anmerkung 92): die Kartenschalter.
//
// Der Auslöser war, dass der Autor selbst nicht mehr sagen konnte, was die
// vier Schalter tun — und die Untersuchung fand den Grund: zwei von ihnen
// taten unter üblichen Umständen gar nichts und sahen dabei eingeschaltet aus.
// Genau das prüft dieses Skript: nicht ob die Schalter da sind, sondern ob
// einer von ihnen wieder still wirkungslos werden kann.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-a40-map-controls.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const fails = [], ok = [];
const check = (name, cond, detail = '') =>
  (cond ? ok : fails).push(name + (cond ? '' : ` — ${detail}`));

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, addListener() {} }));
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
  },
});

setTimeout(() => {
  const w = dom.window, d = w.document;
  check('lädt ohne Fehler',
        errors.filter(e => !/offline|Not implemented|fetch/i.test(e)).length === 0);

  // Ein Schalter für die Verdichtung, nicht zwei plus eine Zahl. Geprüft am
  // Quelltext: `mp` ist ein const im Modulscope und steht deshalb nicht auf
  // window — was für den Rest der Datei gut ist und hier nur heißt, dass die
  // Prüfung eine Zeile weiter unten ansetzt.
  check('mp.condense löst groupPlaces ab',
        /condense:\s*true/.test(html) && !/groupPlaces/.test(html),
        'groupPlaces steckt noch im Quelltext');

  // Die Schwelle ist ein Schutzwert und gehört in die Einstellungen — nicht
  // neben die Schalter, die man beim Kartengucken bedient.
  const cluster = d.getElementById('mp-cluster-min');
  check('Cluster-Schwelle existiert weiterhin', !!cluster);
  check('Cluster-Schwelle nicht mehr in der Kartenansicht',
        cluster && !d.getElementById('view-map').contains(cluster),
        'steckt noch unter #view-map');

  // Der Kern: „Reihenfolge verbinden“ muss sichtbar außer Kraft treten,
  // wenn verdichtet wird — vorher blieb er aktiv und zeichnete nichts.
  const routeChip = d.getElementById('mp-route-toggle');
  if (typeof w.mpSyncChips === 'function' && routeChip) {
    w.mpSyncChips(true);
    check('Reihenfolge-Schalter zeigt sich außer Kraft',
          routeChip.classList.contains('inert'));
    const blockedTitle = routeChip.title;
    w.mpSyncChips(false);
    check('Reihenfolge-Schalter wieder normal',
          !routeChip.classList.contains('inert'));
    check('Begründung unterscheidet sich je Lage',
          blockedTitle && blockedTitle !== routeChip.title,
          'derselbe Titel in beiden Zuständen');
  } else {
    check('mpSyncChips vorhanden', false, 'Funktion oder Chip fehlt');
  }

  // Die beiden Linien dürfen nicht wieder gleich heißen: die eine ist
  // gemessen, die andere gezeichnet.
  const label = id => (d.getElementById(id) || {}).textContent || '';
  check('gemessene und gedachte Linie heißen verschieden',
        !/route/i.test(label('mp-tracks-toggle')) || !/route/i.test(label('mp-route-toggle')),
        `${label('mp-tracks-toggle').trim()} / ${label('mp-route-toggle').trim()}`);

  // Jeder Schalter erklärt sich selbst — das war die eigentliche Beschwerde.
  ['mp-tracks-toggle', 'mp-route-toggle', 'mp-group-toggle'].forEach(id => {
    const el = d.getElementById(id);
    check(`${id} hat eine Erklärung`, el && el.title && el.title.length > 40,
          'kein oder zu knapper Titel');
  });

  ok.forEach(n => console.log('  ok  ' + n));
  fails.forEach(n => console.log('  XX  ' + n));
  console.log(fails.length ? `\n${fails.length} Prüfung(en) fehlgeschlagen` : '\nA40: alles grün');
  process.exit(fails.length ? 1 : 0);
}, 2500);
