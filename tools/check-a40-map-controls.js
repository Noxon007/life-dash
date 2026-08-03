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
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
  },
});

setTimeout(async () => {
  const w = dom.window, d = w.document;
  // Die Karte muss aufgebaut sein, sonst gibt es die Ebenen nicht, die
  // `renderPeriod()` leert — und die Prüfungen unten liefen an einer Ausnahme
  // vorbei statt an der Sache.
  try { await w.openMapView(); } catch (_) { /* offline: die Punkte fehlen, die Karte steht */ }
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

  // **Anmerkung 154 (b): derselbe Satz, der dritte Schalter.**
  // `drawTracks` kehrt oberhalb der Monats-Ansicht sofort zurück — richtig
  // (zehntausende Polylinien, Anmerkung 141), aber der Schalter leuchtete
  // weiter. Der Wächter aus 0.33.0 kannte nur seinen eigenen Auslöser und war
  // deshalb grün: **ein Wächter, der nur seinen Auslöser kennt, ist einer für
  // die Vergangenheit** (Anmerkung 114). Geprüft wird die REGEL — kein
  // Schalter darf still wirkungslos sein —, nicht der eine Fall.
  //
  // **Und zwar über `renderPeriod()`, nicht über `mpSyncTrackChip()`.** Im
  // ersten Anlauf rief diese Prüfung die Sync-Funktion selbst auf — dann ist
  // sie grün, sobald es die Funktion GIBT, auch wenn niemand sie ruft. Genau
  // so bestand `check-a41-cities.js` ein Jahr lang (Anmerkung 102): wer eine
  // Eigenschaft der Oberfläche absichert, muss den Zustand HERSTELLEN, in dem
  // ein Nutzer sie sieht. Nachgewiesen am kaputten Stand: mit dem
  // herausgenommenen Aufruf fällt diese Prüfung um, mit dem Direktaufruf nicht.
  //
  // **Mit PUNKTEN auf der Karte**, denn die leere Karte hat einen eigenen
  // Zweig. Im zweiten Anlauf war die Prüfung noch grün, obwohl der Aufruf aus
  // dem normalen Weg entfernt war — sie lief durch den Leer-Zweig, der ihn
  // ebenfalls macht. Ein Wächter muss den Weg gehen, den die Beschwerde ging:
  // eine Karte mit Inhalt, an der jemand die Zoomstufe wechselt.
  const trackChip = d.getElementById('mp-tracks-toggle');
  if (typeof w.renderPeriod === 'function' && trackChip) {
    w.eval(`mp.located = [{ id: 'e1', title: 'Konzert', category: 'concert',
      date_start: '2024-07-12T20:00:00', date_precision: 'exact',
      source: 'manual', location: { id: 'l1', name: 'Köln', lat: 50.9, lng: 6.9 } }];`);
    const state = zoom =>
      w.eval(`mp.mode = '${zoom}'; rebuildPeriods(); renderPeriod();`);
    state('year');
    check('…und die Karte hat für diese Prüfung wirklich Punkte',
          w.eval('mp.periods.length') > 0,
          'sonst läuft alles unten durch den Leer-Zweig');
    check('Wege-Schalter zeigt sich außer Kraft, wo nicht gezeichnet wird',
          trackChip.classList.contains('inert'),
          'in Jahr/Jahrzehnt/Alles zeichnet drawTracks nichts');
    const blocked = trackChip.title;
    check('…und nennt den Grund', /Monat|month/i.test(blocked), blocked);
    state('all');
    check('…auch in „Alles"', trackChip.classList.contains('inert'));
    state('month');
    check('Bis Monat ist er normal', !trackChip.classList.contains('inert'));
    check('…mit anderer Begründung', blocked && blocked !== trackChip.title,
          'derselbe Titel in beiden Zuständen');
    // Die Wahl überlebt die Zoomstufe: außer Kraft ist die ANSICHT, nicht der
    // Wunsch. Ohne diese Prüfung wäre `.inert` auch dann grün, wenn es den
    // Schalter einfach abschaltete — und das ist ausdrücklich `.off`.
    w.eval('mp.showTracks = false'); state('month');
    check('Ausgeschaltet bleibt ausgeschaltet, nicht außer Kraft',
          trackChip.classList.contains('off')
          && !trackChip.classList.contains('inert'));
    state('year');
    check('…und in der Jahresansicht gilt wieder außer Kraft',
          trackChip.classList.contains('inert')
          && !trackChip.classList.contains('off'),
          'zwei verschiedene Aussagen dürfen nicht gleich aussehen (A40)');
    // Und der Leer-Zweig ebenfalls: ob Wege gezeichnet werden können, hängt an
    // der Zoomstufe, nicht am Inhalt — sonst bliebe der Schalter dort auf dem
    // Stand von vorhin stehen.
    w.eval("mp.located = []; mp.mode = 'year'; rebuildPeriods(); renderPeriod();");
    check('Auch auf der leeren Karte gilt die Zoomstufe',
          trackChip.classList.contains('inert'));
    w.eval("mp.showTracks = true; mp.mode = 'day'; renderPeriod();");
  } else {
    check('renderPeriod vorhanden', false, 'Funktion oder Chip fehlt');
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
