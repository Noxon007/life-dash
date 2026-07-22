// A41 (Anmerkungen 94/95): Städte, die man aufmachen kann.
//
// Geprüft wird die Fehlerklasse, die A39 hinterlassen hat und die nicht als
// Fehler aussieht: eine Zahl oder ein Balken, der auf etwas verweist, das man
// dann nicht öffnen kann. Ein Balken ohne Klick-Handler sieht genau so aus wie
// einer mit — das ist die stille Sorte Defekt aus Anmerkung 92.
//
// Drei Eigenschaften, jede einzeln still brechbar:
//   1. Die Städte-Kachel führt ins Städte-Kompendium, nicht auf die Karte.
//   2. Die Städte-Balken sind verdrahtet (Schlüssel UND Handler — renderBars
//      verdrahtet nur, was beides hat, und schweigt, wenn eines fehlt).
//   3. Ein gesetzter Stadtfilter blendet die importierten Besuche ein. Ohne das
//      filtert der Server nach der Stadt und der Browser wirft die Treffer
//      gleich wieder weg: eine leere Liste ohne erkennbaren Grund.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-a41-cities.js
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
        errors.filter(e => !/offline|Not implemented|fetch/i.test(e)).length === 0,
        errors[0] || '');

  // --- 1. Die Kachel hat ein Ziel, an dem Städte stehen ------------------- //
  const tile = d.getElementById('stat-cities');
  const card = tile && tile.closest('.stat-card');
  check('Städte-Kachel ist anklickbar', !!(card && card.dataset.go),
        'kein data-go — die Zahl ist eine Sackgasse');
  check('Städte-Kachel führt zu den Städten',
        !!card && card.dataset.go === 'comp:city',
        `führt nach "${card && card.dataset.go}" — dort stehen keine Städte`);
  // A42: Diese Prüfung stand hier von Anfang an — und sah am Defekt vorbei.
  // Sie las die Reiterleiste, WIE SIE IM HTML STEHT; im Betrieb ersetzt
  // applyModules() sie aber vollständig, sobald /api/modules geantwortet hat,
  // und der Städte-Reiter gehört zu keinem Modul. Er existierte also genau bis
  // zur ersten Antwort, was in einer echten Sitzung „nie" heißt. Geprüft wird
  // deshalb jetzt der Zustand NACH dem Laden der Module — der einzige, den
  // jemand zu sehen bekommt.
  const drive = code => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };
  drive(`MODULES = [{ key: 'animal', label: 'Tiere', emoji: '🦅', compendium: true, event_categories: ['animal'] },
                    { key: 'country', label: 'Länder', emoji: '🌍', compendium: true, event_categories: [] }];
         TRACKED = null; applyModules();`);
  check('Städte-Reiter existiert nach dem Laden der Module',
        !!d.querySelector('#comp-tabs [data-type="city"]'),
        'applyModules() ersetzt die Leiste und lässt die Städte weg');
  check('Städte-Reiter überlebt auch ohne Sammel-Module',
        (() => { drive('MODULES = []; TRACKED = null; applyModules();');
                 const has = !!d.querySelector('#comp-tabs [data-type="city"]');
                 drive(`MODULES = [{ key: 'animal', label: 'Tiere', emoji: '🦅', compendium: true, event_categories: ['animal'] }];
                        applyModules();`);
                 return has; })(),
        'ohne getrackte Module verschwinden auch die Städte');

  // Orte bekommen bewusst KEINEN Reiter (Anmerkung 95) — eine Menge ohne
  // Horizont ist eine Karte, keine Sammlung.
  check('Orte bekommen keinen Kompendium-Reiter',
        !d.querySelector('#comp-tabs [data-type="place"], #comp-tabs [data-type="location"]'),
        'Orte als Sammlung widerspricht Anmerkung 95');

  // --- 2. Die Balken sind wirklich verdrahtet ----------------------------- //
  // renderBars hängt nur dort einen Handler ein, wo BEIDES vorliegt: ein
  // Schlüssel als drittes Element der Zeile und eine onClick-Funktion. Deshalb
  // wird hier gerendert und geklickt, statt den Quelltext zu lesen.
  if (typeof w.renderBars !== 'function') {
    check('renderBars vorhanden', false);
  } else {
    d.querySelector('.content').insertAdjacentHTML('beforeend',
      '<div id="a41-probe"></div>');
    let clicked = null;
    w.renderBars('a41-probe', [['Düsseldorf', 12, 'Düsseldorf']], k => { clicked = k; });
    const row = d.querySelector('#a41-probe [data-bar-key]');
    check('Städte-Balken tragen einen Schlüssel', !!row,
          'ohne Schlüssel bleibt der Balken tot, sieht aber klickbar aus');
    if (row) {
      row.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      check('Klick auf einen Städte-Balken kommt an', clicked === 'Düsseldorf');
    }
    // Und: der echte Aufruf muss den Handler mitgeben.
    check('das Städte-Diagramm wird mit Handler gezeichnet',
          /renderBars\('chart-cities'[\s\S]{0,200}?tlFilterCity/.test(html),
          'renderBars(chart-cities, …) ohne onClick — die Balken bleiben tot');
  }

  // --- 3. Der Filter widerspricht sich nicht selbst ----------------------- //
  check('tlFilterCity vorhanden', typeof w.tlFilterCity === 'function');
  // `tl` ist ein top-level `const` und hängt damit NICHT am window — der
  // Zustand ist nur über eval im Skript-Bereich erreichbar. Nicht schön, aber
  // ehrlicher, als die Prüfung wegzulassen: die Verdrahtung von Stadtfilter und
  // Besuchs-Schalter ist genau die Stelle, an der die Liste still leer bleibt.
  const inPage = code => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };
  check('Stadtfilter zeigt importierte Besuche',
        inPage("(() => { const b = tl.city; tl.city = 'Düsseldorf'; "
               + "const r = tlShowsVisits(); tl.city = b; return r; })()") === true,
        'der Server liefert die Besuche der Stadt und der Browser filtert sie weg');
  check('ohne Stadtfilter bleibt der Besuchs-Schalter zuständig',
        inPage("(() => { const b = tl.city; tl.city = null; "
               + "const r = tlShowsVisits() === tl.showVisits; tl.city = b; return r; })()") === true,
        'der Stadtfilter hat den Schalter dauerhaft übersteuert');
  check('der Stadtfilter geht serverseitig',
        /city:\s*tl\.city/.test(html),
        'ohne city-Parameter durchsucht nur das geladene Fenster (A37)');

  // Der Chip ist die Begründung für einen verkürzten Zeitstrahl — ohne ihn
  // steht man vor einer fast leeren Liste und weiß nicht, warum.
  const chip = d.getElementById('tl-city-chip');
  check('Stadtfilter zeigt sich als Chip', !!chip);
  if (chip && typeof w.renderCityChip === 'function') {
    inPage("tl.city = 'Düsseldorf'; renderCityChip();");
    check('Chip nennt die Stadt', chip.textContent.includes('Düsseldorf'));
    check('Chip ist sichtbar, solange gefiltert wird', chip.style.display !== 'none');
    inPage("tl.city = null; renderCityChip();");
    check('Chip verschwindet ohne Filter', chip.style.display === 'none');
  }

  ok.forEach(n => console.log('  ok  ' + n));
  fails.forEach(n => console.log('  XX  ' + n));
  console.log(fails.length ? `\n${fails.length} Prüfung(en) fehlgeschlagen` : '\nA41: alles grün');
  process.exit(fails.length ? 1 : 0);
}, 2500);
