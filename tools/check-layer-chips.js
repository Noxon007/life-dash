// Anmerkung 178 — die Ebenen-Schalter, ihre Zahlen und ihre Voreinstellungen.
//
// Vier Zusagen, die man dem Ergebnis nicht ansieht:
//
//   1. **Die Karte zeigt zuerst alles.** „Jeder Punkt", alle Ebenen an, alle
//      Kategorien an — und die Reihenfolge-Linie AUS. Vorher war es umgekehrt
//      („je Ort" mit Linie, Fotos aus): eine Deutung, bevor jemand danach
//      gefragt hat.
//   2. **Jeder Ebenen-Schalter nennt die Zahl DIESES Zeitraums**, nicht den
//      Gesamtbestand. Das ist die eigentliche Falle: beide Zahlen sind
//      richtig, sie beantworten nur verschiedene Fragen — und die falsche
//      steht auf einem Schalter, den man beim Ansehen der Karte liest. Der
//      Wächter prüft deshalb nicht „da steht eine Zahl", sondern **dass sie
//      sich beim Blättern ÄNDERT** und dem Bestand widerspricht.
//   3. **Der Grundort steht bei den Kategorien**, in beiden Ansichten — nicht
//      bei den Ebenen, wo er bis 0.39 lag.
//   4. **Der Grundort ist im Zeitstrahl abschaltbar**, und das Abschalten
//      räumt auch die Fußnote weg („300 von 7.300 gezeigt" unter einer Liste
//      ohne eine einzige davon wäre eine Auskunft über etwas, das nicht da
//      ist).
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-layer-chips.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// Unverwechselbare Mengen (Regel aus check-a46-visit-split.js): keine Zahl
// darf zufällig aus einem Datum oder einer anderen Menge stammen.
const JULY = '2024-07-12', AUG = '2024-08-01';
const ev = (id, src, cat, day, city) => ({
  id, title: `${src}-${id}`, category: cat, source: src,
  date_start: `${day}T10:00:00`, date_precision: 'exact', confirmed: 'confirmed',
  entities: [], metrics: [], media: [],
  location: { id: 'l' + city, name: city, lat: 51.93, lng: 8.87, city },
});
// Juli: 3 von Hand, 2 automatisch · August: 1 von Hand, 7 automatisch
const EVENTS = [
  ev('m1', 'manual', 'concert', JULY, 'Detmold'),
  ev('m2', 'manual', 'trip', JULY, 'Detmold'),
  ev('m3', 'manual', 'meal', JULY, 'Detmold'),
  ev('m4', 'manual', 'concert', AUG, 'Köln'),
  ...[1, 2].map(i => ev('g' + i, 'google_timeline', 'event', JULY, 'Detmold')),
  ...[1, 2, 3, 4, 5, 6, 7].map(i => ev('h' + i, 'google_timeline', 'event', AUG, 'Köln')),
];
const VISIT_TOTAL = 9631;   // Bestand — absichtlich weit weg von 2 und 7
// Anmerkung 181: der BESTAND je Kategorie, wie ihn der Index liefert. Die
// Zahlen sind mit Absicht keine, die in der geladenen Seite vorkommen — und
// `event` ist zusätzlich in „von Hand" und „automatisch erfasst" geteilt,
// damit sich prüfen lässt, dass der Chip mitgeht, wenn eine Ebene ausgeht.
const CAT_INDEX = [
  { category: 'concert', count: 4711, manual: 4711, visits: 0, photos: 0 },
  { category: 'trip', count: 1234, manual: 1234, visits: 0, photos: 0 },
  { category: 'meal', count: 88, manual: 88, visits: 0, photos: 0 },
  { category: 'event', count: 5100, manual: 100, visits: 5000, photos: 0 },
];
const BASELINE = [{
  id: 'b1', place: 'Detmold', label: 'Zuhause', lat: 51.93, lng: 8.87,
  date_start: '2024-01-01', date_end: '2024-12-31', day_count: 366,
}];

function makeDom() {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.__zoom = 6;
      // Ein Doppel, das für jede Eigenschaft sich selbst zurückgibt, macht aus
      // `getZoom()` etwas, das keine Zahl ist (Anm. 116) — deshalb steht die
      // Zahl hier ausdrücklich drin.
      const shape = () => {
        const self = {
          addTo: () => self, bindPopup: () => self, bindTooltip: () => self,
          setRadius: () => self, on: () => self, clearLayers: () => self,
          getBounds: () => ({ isValid: () => false }),
        };
        return self;
      };
      const base = new Proxy(function () { return base; }, {
        get: (_t, k) => {
          if (k === 'getZoom') return () => w.__zoom;
          if (k === 'marker' || k === 'circleMarker' || k === 'polyline'
              || k === 'layerGroup' || k === 'popup') return shape;
          if (k === 'canvas') return () => ({ _n: 'canvas' });
          return base;
        },
        apply: () => base,
      });
      w.L = base;
      w.fetch = u => {
        const p = String(u);
        let body = [];
        if (/events\/map/.test(p)) {
          body = { total: EVENTS.length, shown: EVENTS.length, events: EVENTS,
                   photos: { places: [], cats: [], points: [] } };
        } else if (/events\/index/.test(p)) {
          body = { total: EVENTS.length, dated: EVENTS.length, undated: 0,
                   unconfirmed: 0, fuzzy: 0, visits: VISIT_TOTAL, photo_events: 0,
                   machine_proposals: 0, years: [{ year: 2024, count: EVENTS.length }],
                   baseline_days: 366, baseline_years: [{ year: 2024, days: 366 }],
                   // Anmerkung 181: die Kategoriezahlen des Zeitstrahls kommen
                   // von hier. Unverwechselbar weit weg von den geladenen
                   // Mengen (2 Konzerte, 9 Sonstige) — steht auf dem Chip eine
                   // davon, zählt er die Seite statt den Bestand (A37).
                   categories: CAT_INDEX };
        } else if (/\/api\/baselines/.test(p)) body = BASELINE;
        else if (/days\/baseline/.test(p)) {
          // Zwei abgeleitete Tage — beide an Tagen OHNE Ereignis, sonst wären
          // sie gar keine Lückenfüller.
          body = { periods: [{ place: 'Detmold', city: 'Detmold', label: 'Zuhause' }],
                   days: { '2024-03-04': 0, '2024-03-05': 0 } };
        }
        else if (/days\/weather/.test(p)) body = {};
        else if (/days\/media/.test(p)) body = {};
        else if (/api\/events\?/.test(p)) body = EVENTS;
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/api\/tracks/.test(p)) body = { total: 0, shown: 0, tracks: [] };
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
const num = s => (String(s).match(/[\d.,]+/) || [''])[0].replace(/[.,]/g, '');

setTimeout(async () => {
  const dom = makeDom(), w = dom.window, d = w.document;
  await wait(200);

  // --- 1. Die Voreinstellungen ------------------------------------------- //
  // Gelesen wird der ZUSTAND, nicht das Markup: `mp` entscheidet, was gezeichnet
  // wird, und ein Chip mit der richtigen Klasse über einem falschen Zustand
  // wäre genau die halbe Wahrheit, die man beim Lesen übersieht.
  ok('Voreingestellt ist „jeder Punkt"', w.eval('mp.density') === 'point',
     `${w.eval('mp.density')} — „je Ort" ist eine Verdichtung, bevor jemand danach fragt`);
  ok('Alle Ebenen sind an',
     w.eval('mp.showManual && mp.showVisits && mp.showPhotos && mp.showTracks && mp.showBaseline'),
     'die Karte soll zuerst zeigen, was da IST');
  ok('Die Reihenfolge-Linie ist aus', w.eval('mp.showRoute') === false,
     'eine Linie über tausend Punkte ist ein Knäuel');
  ok('Alle Kategorien sind an',
     w.eval('mp.catFilter.size === FILTER_CATS.length'),
     `${w.eval('mp.catFilter.size')} von ${w.eval('FILTER_CATS.length')}`);
  const route = d.getElementById('mp-route-toggle');
  ok('…und der Chip zeigt es', route.classList.contains('off'),
     'ein Schalter, dessen Aussehen nicht zu seinem Zustand passt, ist die '
     + 'stillste Sorte Falschaussage');

  // --- 2. Der Grundort steht bei den KATEGORIEN --------------------------- //
  // Über die gemeinsame Gruppe geprüft und nicht über die Reihenfolge im
  // Markup: „steht daneben" wäre auch dann grün, wenn beide in „Ebenen" lägen.
  const sameGroup = (a, b) => {
    const ga = d.getElementById(a), gb = d.getElementById(b);
    return !!ga && !!gb && ga.closest('.filter-group') === gb.closest('.filter-group');
  };
  ok('Karte: der Grundort steht bei den Kategorien',
     sameGroup('mp-baseline-toggle', 'mp-filters'),
     'er lag in „Ebenen" — beim Benutzen ist er aber eine SORTE Eintrag');
  ok('Zeitstrahl: ebenso', sameGroup('tl-baseline-toggle', 'tl-filters'),
     'zwei Ansichten, dieselbe Frage, dieselbe Stelle');
  ok('Karte: er steht NICHT mehr bei den Ebenen',
     !sameGroup('mp-baseline-toggle', 'mp-visits-toggle'));

  // --- 3. Die Zahlen meinen den gezeigten Zeitraum ------------------------ //
  await w.openMapView();
  w.eval("mp.mode = 'month'; rebuildPeriods(); renderPeriod();");
  await wait(120);
  const man = d.getElementById('mp-manual-toggle');
  const vis = d.getElementById('mp-visits-toggle');
  const label = () => d.getElementById('mp-period-label').textContent;

  // Angesteuert wird ausdrücklich, nicht „der letzte": seit Anmerkung 167
  // bringt der Grundort seine eigenen Zeiträume mit, die Liste endet also im
  // Dezember. Genau das soll sie auch — ein Wächter, der stillschweigend den
  // letzten Eintrag nimmt, prüft die Zeiträume statt die Zahlen.
  w.eval("mp.index = mp.periods.indexOf('2024-08'); renderPeriod();");
  await wait(120);
  ok('Es wird ein Monat angezeigt', /8|Aug/i.test(label()), label());
  const augMan = num(man.textContent), augVis = num(vis.textContent);
  ok('August: 1 von Hand', augMan === '1', `${man.textContent}`);
  ok('August: 7 automatisch erfasst', augVis === '7', `${vis.textContent}`);
  ok('…und das ist NICHT der Bestand', augVis !== String(VISIT_TOTAL),
     `${vis.textContent} — der Bestand (${VISIT_TOTAL}) beantwortet eine andere Frage`);
  ok('Der Bestand steht im Titel', vis.title.includes('9.631') || vis.title.includes('9,631'),
     `${vis.title} — verschwiegen werden darf er nicht`);

  // **Die eigentliche Prüfung: die Zahl ÄNDERT sich beim Blättern.** Eine
  // feste Zahl wäre bei einem einzigen Zeitraum ebenso grün gewesen.
  d.getElementById('mp-prev').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(120);
  ok('Zurückblättern zeigt den Vormonat', /7|Jul/i.test(label()), label());
  ok('Juli: 3 von Hand', num(man.textContent) === '3', `${man.textContent}`);
  ok('Juli: 2 automatisch erfasst', num(vis.textContent) === '2', `${vis.textContent}`);
  ok('…die Zahlen sind also wirklich zeitraumbezogen',
     num(man.textContent) !== augMan && num(vis.textContent) !== augVis,
     'stünde überall dasselbe, wäre es weiterhin der Bestand');

  // Gegenprobe: ausgeschaltet liegt nichts von dieser Ebene auf der Karte,
  // also ist die Zahl null. Sie soll nicht auf dem letzten Stand stehen
  // bleiben — das wäre eine Auskunft über etwas, das gerade nicht gezeigt wird.
  w.eval('mp.showVisits = false; mpSyncSourceChips();');
  ok('Ausgeschaltet steht dort 0', num(vis.textContent) === '0', vis.textContent);
  w.eval('mp.showVisits = true; mpSyncSourceChips();');

  // --- 3b. Anmerkung 181: die KATEGORIE-Chips nennen ihre Zahl ebenfalls --- //
  //
  // Gemeldet: „bei den Kategorien wird nur beim Grundort eine Anzahl
  // angegeben, bei den anderen nicht — das ist nicht konsequent." Seit
  // Anmerkung 178 stehen sie in derselben Reihe; eine Reihe, in der ein Chip
  // eine Zahl trägt und sieben nicht, liest sich als Fehler in den sieben.
  const catChip = (box, c) => d.querySelector(`#${box} [data-cat="${c}"]`);
  ok('Karte: jeder Kategorie-Chip trägt eine Zahl',
     w.eval('FILTER_CATS').every(c => /\d/.test((catChip('mp-filters', c) || {}).textContent || '')),
     w.eval('FILTER_CATS').map(c => (catChip('mp-filters', c) || {}).textContent).join(' | '));
  // Wir stehen im Juli: 3 von Hand (Konzert, Reise, Essen) und 2 automatisch
  // erfasste, die als „Sonstiges" laufen.
  ok('Juli: 1 Konzert', num(catChip('mp-filters', 'concert').textContent) === '1',
     catChip('mp-filters', 'concert').textContent);
  ok('Juli: 2 Sonstiges', num(catChip('mp-filters', 'event').textContent) === '2',
     catChip('mp-filters', 'event').textContent);
  ok('…und wo nichts liegt, steht 0',
     num(catChip('mp-filters', 'sport').textContent) === '0',
     catChip('mp-filters', 'sport').textContent);

  // **Der Kern der Regel: die Zahl hängt NICHT am eigenen Schalter.** Bei den
  // Ebenen daneben tut sie das (dort heißt sie „was zeichne ich gerade"). Auf
  // einem Kategorie-Chip wäre „0 Konzerte" die Wiederholung der Ausgrauung —
  // und sie nähme genau die Zahl weg, wegen der man ihn anklickt.
  catChip('mp-filters', 'concert')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(120);
  ok('…und ein ausgeschalteter Chip behält sie',
     num(catChip('mp-filters', 'concert').textContent) === '1'
     && catChip('mp-filters', 'concert').classList.contains('off'),
     `${catChip('mp-filters', 'concert').textContent} — ausgeschaltet ist er `
     + 'schon an der Ausgrauung zu erkennen');
  catChip('mp-filters', 'concert')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(120);
  ok('…und die Farbmarke überlebt das Schreiben',
     !!catChip('mp-filters', 'concert').querySelector('.fdot'),
     'Anmerkung 160: `chip.textContent = …` räumt sie weg — deshalb steht die '
     + 'Beschriftung in einem eigenen Element');

  // --- 4. Der Grundort lässt sich im Zeitstrahl abschalten ---------------- //
  w.eval("tl.zoom = 'year';");
  await w.loadTimeline();
  await wait(200);
  const list = d.getElementById('timeline-list');
  const blChip = d.getElementById('tl-baseline-toggle');
  ok('Der Zeitstrahl hat einen Grundort-Schalter', !!blChip);
  ok('…und er ist benutzbar', !blChip.classList.contains('inert'),
     'ohne Grundort wäre er außer Kraft — hier gibt es einen');
  const withRows = w.eval('tlBaselineRows().length');
  ok('Abgeleitete Tage sind da', withRows === 2, `${withRows} Zeilen`);
  // Anmerkung 181: die Zahl des BESTANDES (366 aus dem Index), nicht die der
  // gerade gezeichneten zwei Zeilen — wie „🛰️ 9.631 automatisch erfasst"
  // darüber und wie die Kategorie-Chips daneben. Wie weit die Liste
  // zurückreicht, ist die Frage des Fußes, nicht die des Chips.
  ok('…und der Schalter nennt die Zahl des Bestandes',
     num(blChip.textContent) === '366', blChip.textContent);

  // Und die Kategorie-Chips des Zeitstrahls: hier ist die richtige Zahl die
  // des BESTANDES, weil der Zeitstrahl nur ein Fenster kennt — aus der
  // geladenen Seite wäre sie eine beliebige Teilmenge (A37).
  ok('Zeitstrahl: der Kategorie-Chip nennt den Bestand',
     num(catChip('tl-filters', 'concert').textContent) === '4711',
     `${catChip('tl-filters', 'concert').textContent} — in der geladenen Seite `
     + 'stehen 2 Konzerte; steht die 2 auf dem Chip, zählt er das Fenster');
  // **Und er geht mit, wenn eine Ebene ausgeht.** 5.100 „Sonstiges" bestehen
  // aus 100 von Hand und 5.000 automatisch erfassten; wer die ausblendet,
  // bekäme sonst ein Versprechen über 5.100 Einträge und beim Anklicken 100
  // (Anmerkung 92 / A40, eine Ebene höher).
  // Voreingestellt sind die automatisch erfassten im Zeitstrahl AUS — also
  // stehen dort die 100 von Hand erfassten und nicht die 5.100 des Bestandes.
  ok('…ohne die ausgeblendete Herkunft',
     num(catChip('tl-filters', 'event').textContent) === '100',
     `${catChip('tl-filters', 'event').textContent} — steht hier 5.100, `
     + 'verspricht der Chip Einträge, die beim Anklicken nicht da sind');
  w.eval('tl.showVisits = true; renderTimeline();');
  await wait(60);
  ok('…und mit ihr sind es 5.100',
     num(catChip('tl-filters', 'event').textContent) === '5100',
     `${catChip('tl-filters', 'event').textContent} — bleibt die Zahl stehen, `
     + 'geht der Chip beim Umlegen einer Ebene nicht mit');
  w.eval('tl.showVisits = false; renderTimeline();');
  await wait(60);

  blChip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(140);
  ok('Ausgeschaltet sind sie weg', w.eval('tlBaselineRows().length') === 0,
     'bis 0.39 gab es hier gar keinen Griff — in einem Jahr ohne Einträge '
     + 'bestand der Zeitstrahl ausschließlich aus ihnen');
  ok('…und die Fußnote geht mit', w.eval('TL_BASELINE_SHOWN') === 0
     && !/von .* abgeleiteten/.test(list.textContent),
     '„300 von 7.300 gezeigt" unter einer Liste ohne eine einzige davon');
  blChip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(140);
  ok('Wieder eingeschaltet sind sie zurück', w.eval('tlBaselineRows().length') === 2,
     'ein Schalter, der nur in eine Richtung wirkt, ist ein halber Schalter');

  // --- 5. Anmerkung 177: der Zeiger sagt, was anklickbar ist -------------- //
  //
  // Geprüft wird der SCHIEDSRICHTER, nicht das Zeigen selbst: dass ein Kreis
  // getroffen wird, ist Rechnerei mit drei Zahlen — dass ZWEI Ebenen dieselbe
  // Fläche belegen und sich den Zeiger nicht gegenseitig wegnehmen, ist die
  // Stelle, an der es still kaputtgeht (die Foto-Ebene meldet „kein Treffer"
  // über einem Eintrag, unter dem kein Foto liegt).
  const box = d.getElementById('map');
  w.eval("mapObj = { getContainer: () => document.getElementById('map') }; MP_HOVER.clear();");
  const hover = (who, on) => w.eval(`mpHover(${JSON.stringify(who)}, ${on})`);
  hover('pins', true);
  ok('Über einem Punkt wird der Zeiger zur Hand', box.style.cursor === 'pointer',
     `„${box.style.cursor}" — die Leinwand fängt keine Klicks, also bringt sie `
     + 'auch keinen Zeiger mit');
  hover('fotos', true);
  hover('fotos', false);
  ok('Eine zweite Ebene nimmt ihn nicht weg', box.style.cursor === 'pointer',
     `„${box.style.cursor}" — Fotos und Einträge liegen übereinander`);
  hover('pins', false);
  ok('Daneben ist er wieder der der Karte', box.style.cursor === '',
     `„${box.style.cursor}" — „grab" steht in Leaflets Stilvorlage und gehört `
     + 'nicht ein zweites Mal hierher');

  console.log(fail ? `\nEbenen-Schalter: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nEbenen-Schalter: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
