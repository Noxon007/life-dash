// Anmerkung 119 — „Wo steht das Wetter, wenn ein Tag zwei Orte hat?"
//
// Vier Ansichten beantworteten diese Frage verschieden, und die teuerste
// Antwort war die des Zeitstrahls: das Wetter des Verdichtungs-Vertreters
// `min(id)` — bei UUIDs ein zufälliger von fünf Besuchen. Der Kopf des Tages
// sagte gar nichts, die Sammelkarte auch nicht.
//
// Geprüft wird deshalb genau das, was still falsch werden kann:
//   (a) der Tageskopf liest den TAGESWERT und nicht eine Karte darunter,
//   (b) mehrere Wettergegenden werden GESAGT statt verschwiegen,
//   (c) eine Woche bekommt kein „Tageswetter" (sie ist kein Tag),
//   (d) die Sammelkarte trägt Wetter — aber nur, wenn sie einen Tag bündelt.
//
// Sprache: jsdom meldet en-US, die App startet also ENGLISCH (Anmerkung 108).
// Zugesichert wird darum an Struktur und Zahlen, nicht an deutschem Text.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-day-weather.js
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

// Ein Besuch, wie ihn die schlanke Liste liefert. `weather` ist bewusst
// ANDERS als der Tageswert unten: nur so lässt sich zeigen, aus welcher
// Quelle der Kopf liest.
const visit = (id, hour, title, weather) => ({
  id, title, category: 'event', confirmed: 'confirmed', confidence: 1,
  source: 'google_timeline',
  date_start: `2026-07-05T${String(hour).padStart(2, '0')}:00:00`,
  date_precision: 'exact',
  location: { id: 'l' + id, name: title, city: 'Hamburg' },
  entities: [], metrics: [], media: [], weather,
});

setTimeout(() => {
  const w = dom.window, d = w.document;
  check('lädt ohne Fehler',
        errors.filter(e => !/offline|Not implemented|fetch/i.test(e)).length === 0,
        errors.join(' | '));

  for (const fn of ['dayWeatherLine', 'tlGroupWeather', 'renderTimelineList',
                    'visitGroupCard']) {
    if (typeof w[fn] !== 'function') check(`${fn} vorhanden`, false);
  }
  if (typeof w.dayWeatherLine !== 'function') { report(); return; }

  // `tl` und `TL_DAY_WX` sind `const` — die stehen im Skript-Bereich und
  // nicht am Fenster (Funktionsdeklarationen dagegen schon). Der Zustand muss
  // deshalb HERGESTELLT werden, statt ihn von außen zu setzen: derselbe
  // Fallstrick, an dem `check-a41-cities.js` ein Jahr lang grün war, ohne
  // etwas zu prüfen.
  const setDay = (day, obj) =>
    w.eval(`TL_DAY_WX.set(${JSON.stringify(day)}, ${JSON.stringify(obj)})`);
  const setTl = obj => w.eval(`Object.assign(tl, ${JSON.stringify(obj)})`);

  // --- (a) Der Kopf liest den Tageswert, nicht die Karte -------------------
  // Der Tag hat 18 °C, die Karten tragen 31 °C. Käme die Zeile aus einem
  // Ereignis, stünde 31 im Kopf — genau der Defekt vor Anmerkung 119.
  setDay('2026-07-05', {
    values: { temp_min_c: 12, temp_max_c: 18, weather: 'Regen' }, regions: 1 });
  setTl({ zoom: 'day', showVisits: true, query: '', done: true,
          events: [visit('a', 8, 'Besuch: Nord',
                         { temp_min_c: 30, temp_max_c: 31 })] });
  w.renderTimelineList();

  const head = () => d.querySelector('#timeline-list .tl-year-label');
  const wxSpan = () => d.querySelector('#timeline-list .tl-day-wx');
  check('der Tageskopf trägt eine Wetterzeile', !!wxSpan(),
        'kein .tl-day-wx im Kopf des Tages');
  check('sie zeigt den TAGESWERT (12–18), nicht den der Karte (30–31)',
        !!wxSpan() && /12–18/.test(wxSpan().textContent)
        && !/30|31/.test(wxSpan().textContent),
        wxSpan() ? wxSpan().textContent : '—');

  // --- (b) Mehrere Wettergegenden werden gesagt ----------------------------
  setDay('2026-07-05', { values: { temp_min_c: 12, temp_max_c: 18 }, regions: 2 });
  w.renderTimelineList();
  check('bei zwei Wettergegenden steht ein Hinweis',
        !!d.querySelector('#timeline-list .tl-day-wx .wx-regions'),
        'kein .wx-regions — die Mehrdeutigkeit bliebe still');
  check('der Hinweis nennt die Zahl der Gegenden',
        !!wxSpan() && /2/.test(wxSpan().textContent));
  check('bei einer Gegend steht KEIN Hinweis', (() => {
    setDay('2026-07-05', { values: { temp_max_c: 18 }, regions: 1 });
    w.renderTimelineList();
    return !d.querySelector('#timeline-list .wx-regions');
  })(), 'der Warnhinweis stünde an jedem gewöhnlichen Tag');

  // --- (c) Eine Woche ist kein Tag ----------------------------------------
  // **Der Wert wird absichtlich unter dem WOCHEN-Schlüssel hinterlegt.** Ohne
  // das bestünde diese Prüfung auch dann, wenn die Zoom-Abfrage gestrichen
  // würde — sie liefe schlicht ins Leere, weil `TL_DAY_WX` keinen Eintrag
  // „2026-W27" hat. Eine Prüfung, die aus dem falschen Grund grün ist, ist
  // keine (Anmerkung 108): geprüft werden muss, dass der Kopf die Zeile
  // WEGLÄSST, obwohl es etwas zu holen gäbe.
  setTl({ zoom: 'week' });
  const weekKey = w.eval("tlGroup({ date_start: '2026-07-05T08:00:00' }).key");
  setDay(weekKey, { values: { temp_min_c: 12, temp_max_c: 18 }, regions: 1 });
  w.renderTimelineList();
  check('im Wochen-Zoom trägt der Gruppenkopf kein Tageswetter',
        !d.querySelector('#timeline-list .tl-day-wx'),
        'eine Woche hat kein Wetter — die Zeile behauptete es doch');
  setTl({ zoom: 'day' });

  // --- (d) Die Sammelkarte -------------------------------------------------
  // Sie ruft `eventChips` nicht auf; vor Anmerkung 119 verschwand das Wetter
  // damit ausgerechnet dort, wo am meisten zusammengefasst wird.
  setDay('2026-07-05', { values: { temp_min_c: 12, temp_max_c: 18 }, regions: 1 });
  const sameDay = w.visitGroupCard({ visitGroup: true, items: [
    visit('b', 9, 'Besuch: Zuhause', null), visit('c', 17, 'Besuch: Zuhause', null)] });
  check('Sammelkarte eines Tages zeigt das Tageswetter', /12–18/.test(sameDay),
        sameDay.replace(/\s+/g, ' '));

  const across = w.visitGroupCard({ visitGroup: true, items: [
    visit('d', 9, 'Besuch: Zuhause', null),
    { ...visit('e', 9, 'Besuch: Zuhause', null), date_start: '2026-07-06T09:00:00' }] });
  check('über mehrere Tage zeigt sie KEIN Wetter', !/12–18|🌤️/.test(across),
        'ein Tageswert für eine Spanne wäre wieder ein willkürlich gewählter Tag');

  // --- Die Regel wohnt im Server ------------------------------------------
  check('der Zeitstrahl holt das Tageswetter vom Server',
        /\/api\/days\/weather\?from=/.test(html),
        'ohne den Endpunkt rechnete der Browser wieder seine eigene Regel');
  check('die Wetterzeile wird nur dargestellt, nicht neu gerechnet',
        /weatherSummary\(\{\s*weather:\s*wx\.values\s*\}\)/.test(html),
        'dayWeatherLine baut die Zeile selbst — zweite Regel für dieselbe Frage');

  report();

  function report() {
    ok.forEach(n => console.log('  ok  ' + n));
    fails.forEach(n => console.log('  XX  ' + n));
    console.log(fails.length ? `\n${fails.length} Prüfung(en) fehlgeschlagen`
                             : '\nTageswetter: alles grün');
    process.exit(fails.length ? 1 : 0);
  }
}, 2500);
