// F20 / Anmerkung 144 — der Wohnort erreicht den Zeitstrahl.
//
// **Was hier schiefgehen kann, sieht man dem Bildschirm nicht an.** Ein
// Zeitstrahl ohne abgeleitete Tage sieht aus wie ein Zeitstrahl, in dem es
// eben keine gibt — und genau die Jahre, um die es geht, sind ja die, in denen
// nichts erfasst wurde. Der Defekt wäre also eine leere Seite, die vollständig
// wirkt: die Sorte Stille, die in diesem Projekt der wiederkehrende Fehler ist
// (A40, Anmerkungen 92/110/158).
//
// Fünf Zusagen:
//
//   1. **Ein Zeitraum ganz ohne Einträge bekommt trotzdem Zeilen.** Die
//      Gruppen des Zeitstrahls entstehen aus Ereignissen; treten die
//      abgeleiteten Tage erst NACH dem Gruppieren ein, bleibt ein solches Jahr
//      leer — obwohl jede Statistik es zählt.
//   2. **Eine abgeleitete Zeile ist keine Ereigniskarte.** Sie trägt keine
//      Kennung, führt in keinen Bearbeiten-Dialog und ist als abgeleitet
//      markiert. Sähe sie aus wie ein Eintrag, wäre die Unterscheidung genau
//      dort verloren, wo sie zählt.
//   3. **Es gibt einen Weg zu ALLEN abgeleiteten Tagen** (Anmerkung 182). Das
//      Fenster fasst einen Schritt, zeigt die jüngsten Tage zusammenhängend,
//      sagt beide Zahlen und trägt einen Knopf, der es erweitert — bis der
//      erste Tag des Zeitraums dasteht. Vorher waren es 300 gleichmäßig über
//      den Zeitraum gegriffene Tage OHNE jeden Weg zu den übrigen, und der Fuß
//      meldete darunter „das ist der Anfang deiner Geschichte".
//   4. **Ein Tag mit Eintrag bekommt keine abgeleitete Zeile daneben.** Das
//      ist die Eigenschaft, auf der im Backend jede Addition beruht — sie muss
//      auch in der Anzeige gelten, sonst steht der Tag zweimal da.
//   5. **Das Wetter der abgeleiteten Tage wird geholt.** `loadDayWeather`
//      fragt die Spanne der geladenen SEITE ab; die abgeleiteten Tage liegen
//      gerade außerhalb davon. Ohne den zweiten Abruf hätten sie Wetter in der
//      Datenbank und zeigten keins (Anmerkung 158, gleiche Form).
//
// **Geprüft wird die ANZEIGE, nicht der deutsche Quelltext.** Unter jsdom
// startet die Seite englisch, der Katalog überschreibt das Markup, und ein ins
// Markup gebauter Defekt erreichte die Zusicherung nie (Anmerkung 116/160).
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-baseline-days.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// Unverwechselbare Werte (Regel aus check-a46-visit-split.js): „17,7 °C" kann
// aus keinem Datum und keiner Zählung stammen.
const TEMP = 17.7;
const PLACE = 'Musterweg 1, Bad Segeberg';
const LABEL = 'Elternhaus';

// Ein Zeitraum von 1990-01-01 bis 1990-12-31 — 365 Tage, also mehr als der
// Deckel. Daneben ein einziger echter Eintrag mitten darin.
const ENTRY_DAY = '1990-06-15';

// **Das Doppel hält sich an `from`/`to`.** Beim ersten Bau tat es das nicht —
// es gab immer das ganze Jahr zurück, egal was gefragt war. Damit waren zwei
// injizierte Defekte GRÜN: „die Spanne bleibt die geladene Seite" und „es gibt
// keinen eigenen Wetter-Abruf" ändern beide nur die FRAGE, und ein Doppel, das
// die Frage nicht liest, kann den Unterschied nicht zeigen. Anmerkung 116/150,
// wörtlich: *ein Doppel, das ein Feld auslässt, ist keine Vereinfachung,
// sondern eine andere Funktion.*
function span(url) {
  const q = new URL(url, 'http://localhost:8000/').searchParams;
  return [q.get('from') || '0000-00-00', q.get('to') || '9999-99-99'];
}
function daysOfYear(from, to) {
  const out = {};
  const d = new Date(Date.UTC(1990, 0, 1));
  while (d.getUTCFullYear() === 1990) {
    const iso = d.toISOString().slice(0, 10);
    // der Tag mit einem Eintrag fehlt — der Wohnort füllt nur Lücken
    if (iso !== ENTRY_DAY && iso >= from && iso <= to) out[iso] = 0;
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

function makeDom(state) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      // **Das Leaflet-Doppel muss `layerGroup` wirklich können.** Ein
      // Auffang-Proxy gibt für JEDE Eigenschaft sich selbst zurück — auch für
      // `getLayers().length`, und dann ist „wie viele Objekte hat die Ebene?"
      // keine Zahl, sondern der Proxy. Eine Zusicherung darüber prüfte nichts
      // (dieselbe Falle wie beim `getZoom()`-Doppel, Anmerkung 120).
      const group = () => {
        const layers = [];
        const g = {
          addTo: () => g, clearLayers: () => { layers.length = 0; return g; },
          getLayers: () => layers, addLayer: (x) => { layers.push(x); return g; },
          _push: (x) => layers.push(x),
        };
        return g;
      };
      // **Das Doppel muss das ZEICHEN behalten, nicht nur seine Zahl.** Seit
      // der Wohnort ein Tropfen mit eigener Farbe ist statt eines grauen
      // Rings, ist „wie sieht es aus?" eine prüfbare Aussage — und ein Doppel,
      // das `marker(ll, opt)` die Argumente wegwirft, kann sie nicht zeigen
      // (Anmerkung 116/150: ein Doppel, das ein Feld auslässt, ist eine andere
      // Funktion). Deshalb hält jede Form ihre Koordinate und ihre Optionen.
      const shape = (kind) => (ll, opt) => {
        const s = {
          kind, ll, opt,
          addTo: (g) => { if (g && g._push) g._push(s); return s; },
          bindPopup: (h) => { s.popup = h; return s; },
          bindTooltip: () => s, setRadius: () => s, on: () => s,
        };
        return s;
      };
      // `latLngBounds(...).pad(...)` muss die Koordinaten BEHALTEN — sonst
      // steht in `state.fits` der Auffang-Proxy, und „springt der Ausschnitt
      // auf den Wohnort?" ist keine Frage mehr, die eine Antwort hat.
      const bounds = (ll) => { const b = { ll, pad: () => b }; return b; };
      const base = new Proxy(function () { return base; }, {
        get: (_t, k) => {
          if (k === 'getZoom') return () => 6;
          if (k === 'layerGroup' || k === 'featureGroup') return group;
          if (k === 'circleMarker' || k === 'marker') return shape(k);
          if (k === 'divIcon') return (o) => o;      // das Symbol selbst lesen
          if (k === 'latLngBounds') return bounds;
          if (k === 'fitBounds') return (b) => {
            (state.fits || (state.fits = [])).push(b); return base;
          };
          return base;
        },
        apply: () => base,
      });
      w.L = base;
      w.fetch = (u, opt) => {
        const p = String(u);
        state.calls.push([(opt && opt.method) || 'GET', p]);
        if (opt && opt.method === 'POST') (state.posts || []).push({ url: p, opt });
        // Anmerkung 184: das Ändern ist ein PATCH und muss deshalb eigens
        // mitgeschrieben werden. In `state.posts` mitzuzählen hieße, dass
        // „schickt das Formular einen POST?" auch dann grün wäre, wenn es
        // beides tut — und ein zweiter, ungewollter Neu-Eintrag ist genau der
        // Defekt, den die Prüfung finden soll.
        if (opt && opt.method === 'PATCH') (state.patches || []).push({ url: p, opt });
        let body = [];
        if (/\/api\/baselines\/[^/]+$/.test(p) && opt && opt.method === 'PATCH') {
          return Promise.resolve({ ok: true, status: 200,
                                   json: () => Promise.resolve({ id: 'b1', day_count: 2190 }) });
        }
        if (/\/api\/baselines$/.test(p) && opt && opt.method === 'POST') {
          return Promise.resolve({ ok: true, status: 201,
                                   json: () => Promise.resolve({ id: 'b9', day_count: 2192 }) });
        }
        if (/\/api\/baselines$/.test(p)) {
          return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(state.noBaseline ? [] : [{
              id: 'b1', label: LABEL, place: PLACE, city: 'Bad Segeberg',
              country: 'Deutschland', lat: 53.93, lng: 10.31,
              date_start: '1986-04-02', date_end: '1992-08-31',
              day_count: 2190 }]) });
        }
        if (/days\/baseline/.test(p)) {
          const [from, to] = span(p);
          const days = state.noBaseline ? {} : daysOfYear(from, to);
          body = { periods: (state.noBaseline || !Object.keys(days).length) ? []
                     : [{ id: 'b1', label: LABEL, place: PLACE,
                          city: 'Bad Segeberg', country: 'Deutschland' }],
                   days };
        } else if (/days\/weather/.test(p)) {
          // Das Wetter liegt an einem Tag, den NUR die Wohnort-Spanne
          // umfasst — die Seite kennt genau einen Tag, und das ist ein anderer.
          const [from, to] = span(p);
          const day = state.wxDay || '1990-03-07';
          body = (day >= from && day <= to)
            ? { [day]: { values: { temp_min_c: TEMP, temp_max_c: TEMP }, regions: 1 } }
            : {};
        } else if (/events\/map/.test(p)) {
          body = { total: 1, shown: 1, photos: { places: [], cats: [], points: [] },
                   events: [{ id: 'm1', title: 'Einschulung', category: 'milestone',
                              date_start: `${ENTRY_DAY}T09:00:00`,
                              date_precision: 'day', source: 'manual',
                              location: { id: 'l1', name: 'Schule',
                                          lat: 53.9, lng: 10.3 } }] };
        } else if (/days\/media/.test(p)) body = {};
        else if (/events\/index/.test(p)) {
          body = { total: 1, dated: 1, undated: 0, unconfirmed: 0, fuzzy: 0,
                   years: [{ year: 1990, count: 1 }], visits: 0, photo_events: 0,
                   machine_proposals: 0, revision: 'r1',
                   baseline_days: state.noBaseline ? 0 : 364,
                   baseline_years: state.noBaseline ? []
                                                    : [{ year: 1990, count: 364 }] };
        } else if (/api\/events\?/.test(p)) {
          body = [{ id: 'e1', title: 'Einschulung', category: 'milestone',
                    date_start: `${ENTRY_DAY}T09:00:00`, date_precision: 'day',
                    confidence: 1, confirmed: 'confirmed', source: 'manual',
                    location: { id: 'l1', name: 'Schule', lat: 53.9, lng: 10.3 },
                    entities: [], metrics: [], media: [] }];
        } else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
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
const inPage = (w, code) => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };

setTimeout(async () => {
  // --- 1. Der Normalfall ---------------------------------------------------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    w.eval("tl.zoom = 'day';");
    await w.loadTimeline();
    await wait(150);

    const list = d.getElementById('timeline-list');
    const cards = [...list.querySelectorAll('.baseline-day')];

    // (1) Ein Zeitraum ohne Einträge bekommt Zeilen — und zwar VOR dem
    //     Gruppieren, sonst gäbe es die Gruppen gar nicht.
    ok('Abgeleitete Tage stehen im Zeitstrahl', cards.length > 0,
       `${cards.length} Zeilen — treten sie erst nach dem Gruppieren ein, `
       + 'bleibt ein Jahr ohne Einträge leer, obwohl die Statistik es zählt');

    // (2) Sie ist keine Ereigniskarte.
    ok('…und keine davon führt in den Bearbeiten-Dialog',
       cards.every(c => !c.dataset.id),
       'eine abgeleitete Zeile mit `data-id` sähe aus wie ein Eintrag und '
       + 'öffnete den Editor für etwas, das niemand erfasst hat');
    ok('…und sie ist als abgeleitet markiert',
       cards.every(c => c.querySelector('.badge-baseline')),
       'ohne Marke ist eine Folgerung von einer Erfassung nicht zu '
       + 'unterscheiden — geprüft an der ANZEIGE, nicht am deutschen Quelltext');

    // (4) Der Tag mit dem echten Eintrag steht genau EINMAL da.
    const entryGroup = [...list.querySelectorAll('.tl-group, .group, .tl-day')]
      .map(g => g.textContent).join(' ');
    ok('Der Tag mit einem Eintrag bekommt keine abgeleitete Zeile',
       !cards.some(c => (c.closest('[data-day]') || {}).dataset?.day === ENTRY_DAY)
       && inPage(w, `TL_BASELINE.has('${ENTRY_DAY}')`) === false,
       'auf der Disjunktheit beruht im Server jede Addition — steht der Tag '
       + 'hier zweimal, zählt er dort auch zweimal');

    // (3) Anmerkung 182: Das Fenster zeigt die JÜNGSTEN Tage zusammenhängend —
    //     und lässt sich erweitern, bis alle da sind.
    const shown = inPage(w, 'TL_BASELINE_SHOWN');
    const total = inPage(w, 'TL_BASELINE_TOTAL');
    ok('Das Fenster fasst einen Schritt',
       shown === inPage(w, 'TL_BASELINE_STEP') && total > shown,
       `${shown} von ${total}`);
    const picked = inPage(w, "tlBaselineRows().map(r => r.day).sort()");
    ok('…und es ist ein Fenster, keine Stichprobe', Array.isArray(picked)
       && picked[picked.length - 1] === '1990-12-31' && picked[0] > '1990-02-28',
       `${Array.isArray(picked) ? picked[0] + ' … ' + picked[picked.length - 1] : picked}`
       + ' — gegriffen wird zusammenhängend ab dem jüngsten Tag; eine über das '
       + 'Jahr verteilte Auswahl ließe sich nicht erweitern, ohne dass beim '
       + 'nächsten Schritt jede Zeile an eine andere Stelle springt');
    ok('…und die Fußzeile nennt beide Zahlen',
       /364/.test(list.textContent) && /300/.test(list.textContent),
       'A40: was eine Ansicht nicht alles zeigen kann, muss sie dort sagen, '
       + 'wo hingeschaut wird');
    // **Der Kern von Anmerkung 182.** Bis hierher gab es keinen Weg zu den
    // übrigen 64 Tagen — die Ereignisse waren zu Ende, also sagte der Fuß „das
    // ist der Anfang deiner Geschichte" über eine Liste, der zwei Monate
    // fehlten. Ein Fenster ohne Griff ist ein Deckel mit besserem Namen.
    const moreBtn = list.querySelector('#tl-more-baseline');
    ok('…und der Fuß bietet den Weg weiter zurück', !!moreBtn,
       'ohne Knopf wäre das Fenster ein Deckel — und der Fuß behauptete '
       + 'gleichzeitig, die Geschichte sei zu Ende');
    ok('…statt „Das ist der Anfang deiner Geschichte"',
       !/Anfang|beginning/i.test(list.textContent),
       list.textContent.slice(-200));
    if (moreBtn) moreBtn.dispatchEvent(new w.Event('click', { bubbles: true }));
    await wait(50);
    const after = inPage(w, 'TL_BASELINE_SHOWN');
    ok('…ein Klick holt die nächsten', after === total,
       `${shown} → ${after} von ${total} — ein Schritt sind ${
         inPage(w, 'TL_BASELINE_STEP')} Tage, und mehr als alle gibt es nicht`);
    const all = inPage(w, "tlBaselineRows().map(r => r.day).sort()");
    ok('…und dann steht der erste Tag des Zeitraums da',
       Array.isArray(all) && all[0] === '1990-01-01',
       Array.isArray(all) ? all[0] : all);
    const foot = d.getElementById('timeline-list').textContent;
    ok('…und erst jetzt ist die Geschichte zu Ende',
       /Anfang|beginning/i.test(foot)
       && !d.getElementById('timeline-list').querySelector('#tl-more-baseline'),
       foot.slice(-200));

    // (5) Das Wetter der abgeleiteten Tage wird geholt und gezeigt.
    //
    // **Nicht „irgendein Wetter-Abruf".** `loadDayWeather` fragt ohnehin die
    // Spanne der geladenen SEITE ab — im ersten Anlauf war diese Zusicherung
    // deshalb grün, auch mit herausgenommenem zweiten Abruf (Anmerkung 108).
    // Geprüft wird die SPANNE: sie muss die abgeleiteten Tage umfassen, und
    // die liegen gerade dort, wo keine Ereignisse sind.
    const wxSpans = state.calls.filter(([, p]) => /days\/weather/.test(p))
      .map(([, p]) => new URL(p, 'http://x/').searchParams.get('from'));
    ok('Ein Wetter-Abruf umfasst die abgeleitete Spanne',
       wxSpans.some(f => f && f <= '1990-01-01'),
       `${JSON.stringify(wxSpans)} — die Seite kennt nur ${ENTRY_DAY}; ohne `
       + 'eigenen Abruf hätten die abgeleiteten Tage Wetter und zeigten keins');
    ok('…und steht auf der Zeile', /17[.,]7/.test(list.textContent),
       list.textContent.slice(0, 240));
    w.close();
  }

  // --- 2. Ohne Wohnort ändert sich nichts --------------------------------
  {
    const state = { calls: [], noBaseline: true };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    await w.loadTimeline();
    await wait(150);
    const list = d.getElementById('timeline-list');
    ok('Ohne Wohnort steht keine abgeleitete Zeile da',
       list.querySelectorAll('.baseline-day').length === 0);
    ok('…und keine Fußzeile behauptet einen Deckel',
       !/300/.test(list.textContent),
       list.textContent.slice(0, 200));
    w.close();
  }

  // --- 2b. Das Formular schickt einen JSON-Body, der auch als solcher ankommt
  //
  // **Gemeldet als „422 beim Zeitraum eintragen".** `api()` setzt den
  // Content-Type NICHT — jeder JSON-Aufruf in dieser Datei setzt ihn selbst,
  // und dieser eine tat es nicht. Ohne ihn schickt der Browser `text/plain`,
  // FastAPI sieht keinen Body und antwortet 422: eine Meldung, die auf das
  // Formular zeigt, obwohl am Formular nichts falsch ist.
  //
  // Kein Test konnte das sehen, weil keiner das Formular je ABGESCHICKT hat —
  // die Backend-Tests rufen den Endpunkt direkt, und der bekommt seinen Body
  // vom TestClient korrekt gesetzt. Der Defekt saß genau in der Naht dazwischen.
  {
    const state = { calls: [], posts: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    d.getElementById('bl-place').value = 'Bad Segeberg';
    d.getElementById('bl-from').value = '1986-04-02';
    d.getElementById('bl-to').value = '1992-08-31';
    d.getElementById('bl-add').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(150);

    const post = state.posts.find(p => /\/api\/baselines$/.test(p.url));
    ok('Das Formular schickt den Zeitraum ab', !!post,
       `Aufrufe: ${JSON.stringify(state.posts.map(p => p.url))}`);
    const ct = post && post.opt && post.opt.headers
      && (post.opt.headers['Content-Type'] || post.opt.headers['content-type']);
    ok('…als JSON, mit dem Content-Type dazu', ct === 'application/json',
       `Content-Type: ${ct} — ohne ihn antwortet FastAPI mit 422, und der `
       + 'Fehler zeigt auf das Formular statt auf den Aufruf');
    let body = null;
    try { body = JSON.parse(post.opt.body); } catch (_) {}
    ok('…und der Rumpf trägt Ort und Anfang',
       body && body.place === 'Bad Segeberg' && body.date_start === '1986-04-02'
       && body.date_end === '1992-08-31',
       JSON.stringify(body));
    w.close();
  }

  // --- 2c. Anmerkung 184 — einen Wohnort nachträglich ändern ---------------
  //
  // Zwei der Zusagen hier sind gegen STILLE Defekte gerichtet, und beide sähe
  // man dem Bildschirm nicht an:
  //
  //   * **Der unveränderte Ort darf nicht mitgeschickt werden.** Tut er es,
  //     geocodiert der Server den Namen neu — und ein auf der Karte gewählter
  //     Punkt („das Elternhaus") wird beim Ändern der BEZEICHNUNG durch den
  //     Ortsmittelpunkt ersetzt. Das Formular sieht danach richtig aus.
  //   * **Ein geleertes „Bis" muss `clear_end` schicken.** In JSON heißt ein
  //     fehlendes Feld „unverändert"; ohne das eigene Feld behielte der
  //     Zeitraum sein altes Ende, während das Formular „bis heute" zeigt.
  {
    const state = { calls: [], posts: [], patches: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    await w.loadBaselines();
    await wait(60);

    const editBtn = d.querySelector('[data-bl-edit]');
    ok('Die Liste bietet einen Ändern-Knopf', !!editBtn,
       'bis 0.39 war ein Wohnort nur eintragbar und entfernbar — eine '
       + 'vertippte Bezeichnung bedeutete: löschen und neu anlegen');
    editBtn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(60);
    ok('…und der Klick füllt DASSELBE Formular',
       d.getElementById('bl-label').value === LABEL
       && d.getElementById('bl-place').value === PLACE
       && d.getElementById('bl-from').value === '1986-04-02'
       && d.getElementById('bl-to').value === '1992-08-31',
       [d.getElementById('bl-label').value, d.getElementById('bl-place').value,
        d.getElementById('bl-from').value, d.getElementById('bl-to').value].join(' | '));
    // Geprüft an der ANZEIGE: unter jsdom startet die Seite englisch, ein ins
    // deutsche Markup gebauter Defekt erreichte die Zusicherung nie.
    ok('…und sagt, welcher Zeitraum gemeint ist',
       d.getElementById('bl-editing').style.display !== 'none'
       && d.getElementById('bl-editing').textContent.includes(LABEL),
       `„${d.getElementById('bl-editing').textContent}" — ein gefülltes `
       + 'Formular ohne diesen Satz sieht aus wie ein neuer Eintrag');
    ok('…und der Knopf heißt nicht mehr „eintragen"',
       /Save|speichern/i.test(d.getElementById('bl-add').textContent),
       `„${d.getElementById('bl-add').textContent}" — A40: ein Knopf muss `
       + 'sagen, was er tut');

    // Nur die Bezeichnung ändern — der Ort bleibt, wie er geladen wurde.
    d.getElementById('bl-label').value = 'Elternhaus (neu)';
    d.getElementById('bl-add').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(150);
    const patch = (state.patches || [])[0];
    ok('Speichern schickt einen PATCH auf DIESEN Zeitraum',
       !!patch && /\/api\/baselines\/b1$/.test(patch.url),
       `${JSON.stringify((state.patches || []).map(x => x.url))}`);
    ok('…und legt keinen zweiten an',
       !state.posts.some(p => /\/api\/baselines$/.test(p.url)),
       'ein POST daneben hieße: der geänderte Zeitraum steht danach zweimal da, '
       + 'und der Server meldete eine Überschneidung statt einer Erklärung');
    let pb = null;
    try { pb = JSON.parse(patch.opt.body); } catch (_) {}
    ok('…mit der neuen Bezeichnung', pb && pb.label === 'Elternhaus (neu)',
       JSON.stringify(pb));
    ok('…und OHNE den unveränderten Ort', pb && pb.place === undefined
       && pb.lat === undefined && pb.lng === undefined,
       `${JSON.stringify(pb)} — mitgeschickt geocodiert der Server ihn neu, und `
       + 'ein gewählter Punkt wird still durch den Ortsmittelpunkt ersetzt');
    ok('…das Ende bleibt, wie es war', pb && pb.date_end === '1992-08-31'
       && !pb.clear_end, JSON.stringify(pb));
    ok('…und danach steht das Formular wieder auf „eintragen"',
       d.getElementById('bl-editing').style.display === 'none'
       && !d.getElementById('bl-label').value,
       'bliebe es im Ändern-Modus, ginge der nächste neue Zeitraum als '
       + 'Änderung an den alten');

    // Zweite Runde: Ort ÄNDERN und das Ende leeren.
    state.patches.length = 0;
    d.querySelector('[data-bl-edit]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(60);
    d.getElementById('bl-place').value = 'Detmold';
    d.getElementById('bl-to').value = '';
    d.getElementById('bl-add').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(150);
    let pb2 = null;
    try { pb2 = JSON.parse(state.patches[0].opt.body); } catch (_) {}
    ok('Ein GEÄNDERTER Ort geht mit', pb2 && pb2.place === 'Detmold',
       JSON.stringify(pb2));
    ok('…und ein geleertes „Bis" sagt ausdrücklich `clear_end`',
       pb2 && pb2.clear_end === true && pb2.date_end === undefined,
       `${JSON.stringify(pb2)} — ohne das Feld heißt „nicht mitgeschickt" `
       + 'unverändert, und der Zeitraum behielte sein altes Ende, während das '
       + 'Formular „bis heute" zeigt');

    // Abbrechen führt zurück ins Eintragen — und eine Lücke aus der Statistik
    // ebenfalls, sonst überschriebe sie den gerade bearbeiteten Zeitraum.
    d.querySelector('[data-bl-edit]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(60);
    d.getElementById('bl-cancel').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(60);
    ok('Abbrechen räumt das Formular', !d.getElementById('bl-label').value
       && d.getElementById('bl-editing').style.display === 'none'
       && !/Save|speichern/i.test(d.getElementById('bl-add').textContent),
       [d.getElementById('bl-label').value,
        d.getElementById('bl-add').textContent].join(' | '));
    d.querySelector('[data-bl-edit]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(60);
    w.openBaselineFor('2001-01-01', '2001-12-31');
    await wait(60);
    ok('Eine übernommene Lücke bricht das Ändern ab',
       d.getElementById('bl-editing').style.display === 'none'
       && d.getElementById('bl-from').value === '2001-01-01',
       'sonst ginge der nächste Klick auf „speichern" an den bearbeiteten '
       + 'Wohnort — mit den Daten der Lücke, und wortlos');
    w.close();
  }

  // --- 2c. Auf der Karte: EIN Zeichen je Zeitraum ---------------------------
  //
  // Sechs Jahre Elternhaus sind 2 190 abgeleitete Tage an EINER Koordinate.
  // Sie einzeln zu zeichnen ergäbe zweitausend deckungsgleiche Punkte — keine
  // Karte, sondern ein Punkt mit Gewicht. Die Zahl gehört ins Popup.
  //
  // Und: der Zeitraum muss ÜBERSCHNEIDEN, nicht enthalten sein. 1986–1992
  // gehört in jede Jahresansicht dazwischen, nicht nur in seine Ränder — das
  // ist der Fehler, den ein `>=`/`<=` an der falschen Seite macht.
  {
    const state = { calls: [], posts: [] };
    const w = makeDom(state).window;
    await wait(200);
    await w.openMapView();
    await wait(120);

    const drawn = k => {
      w.eval(`mpDrawBaselines(${k === null ? 'null' : JSON.stringify(k)})`);
      return w.eval('mapBaseline.getLayers().length');
    };
    ok('Ein Zeichen je Zeitraum, nicht je Tag', drawn('1989') === 1,
       `${drawn('1989')} Objekte für 2 190 abgeleitete Tage`);
    ok('…auch mitten im Zeitraum (Überschneidung, nicht Enthaltensein)',
       drawn('1990-06') === 1, 'ein Jahr innerhalb der Spanne muss ihn zeigen');
    ok('…und außerhalb steht keins', drawn('2020') === 0);
    // **Nicht `mpDrawBaselines` selbst aufrufen.** Im ersten Anlauf stand hier
    // `drawn(null) >= 0` — trivial wahr, und geprüft wurde die Funktion statt
    // ihres Aufrufs: nimmt man den Aufruf aus dem leeren Zweig heraus, bleibt
    // die Zusicherung grün (Anmerkung 108, und der `check-a41-cities.js`-Fall
    // in seiner reinsten Form). Geprüft wird deshalb über `renderPeriod` mit
    // LEERER Karte — und das ist gerade der Normalfall für einen Wohnort:
    // ein Zeitraum, in dem nichts erfasst wurde, hat keine verorteten
    // Ereignisse und trotzdem einen Ort.
    w.eval('mp.located = []; rebuildPeriods(); renderPeriod();');
    await wait(60);
    ok('Ohne verortete Ereignisse zeichnet die Ansicht die Ebene trotzdem',
       w.eval('mapBaseline.getLayers().length') === 1,
       `${w.eval('mapBaseline.getLayers().length')} — ein Zeichenaufruf hinter `
       + 'einem `return` ist die Sorte Ebene, die in einer der Ansichten still fehlt');

    // Und derselbe Weg mit PUNKTEN auf der Karte: der Normalzweig von
    // `renderPeriod` muss die Ebene ebenso zeichnen. Ohne diesen Fall prüfen
    // die Zusicherungen oben nur, dass es `mpDrawBaselines` GIBT — nimmt man
    // den Aufruf dort heraus, bleiben sie grün (Anmerkung 108, drittes Mal in
    // dieser Datei).
    await w.mpLoadPoints(true);   // die Prüfung davor hat sie geleert
    // **Die Ebene VORHER leeren.** Sonst steht das Zeichen aus dem vorigen
    // Aufruf noch da, und die Zusicherung ist auch dann grün, wenn
    // `renderPeriod` gar nichts zeichnet — genau der Fall, den sie prüfen soll.
    w.eval('mapBaseline.clearLayers();');
    w.eval("mp.mode = 'all'; mp.density = 'point'; rebuildPeriods(); renderPeriod();");
    await wait(80);
    ok('…und mit Punkten auf der Karte ebenso',
       w.eval('mp.located.length') > 0
       && w.eval('mapBaseline.getLayers().length') === 1,
       `Punkte: ${w.eval('mp.located.length')}, Wohnort-Zeichen: `
       + `${w.eval('mapBaseline.getLayers().length')}`);

    w.eval('mp.showBaseline = false;');
    ok('Der Schalter blendet sie aus', drawn('1989') === 0);
    w.close();
  }

  // --- 2d. Ein Zeitraum, in dem NUR der Wohnort steht ----------------------
  //
  // **Gemeldet als „auf 1993 kann ich gar nicht gehen".** Die Zeiträume der
  // Karte entstanden aus den EREIGNISSEN — und genau die Jahre, für die der
  // Wohnort gemacht ist, haben keine. Die Ebene war gebaut, gezeichnet und
  // geprüft, nur nicht erreichbar: dieselbe Falle wie bei den Fototagen (A45),
  // und ebenso unsichtbar, weil eine Ansicht ohne diesen Zeitraum aussieht wie
  // eine Ansicht, in der es ihn nicht gibt.
  //
  // Vier Zusagen, und jede davon gegen den kaputten Stand gefahren:
  //   1. der Zeitraum steht in der Leiste — in JEDER Stufe,
  //   2. das Zeichen ist der TROPFEN in eigener Farbe (kein grauer Ring, der
  //      auf der Leinwand unter allem liegt, was nach ihm kommt),
  //   3. der Ausschnitt springt darauf (sonst liegt es außerhalb des Bildes,
  //      und sichtbar ist eine leere Karte),
  //   4. die Liste daneben sagt es (nicht „0 Stopps" und sonst Stille).
  {
    const state = { calls: [], fits: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    await w.openMapView();
    await wait(120);

    // Der einzige verortete Eintrag liegt 1990-06-15; der Wohnort läuft von
    // 1986-04-02 bis 1992-08-31. 1989 hat also keinen einzigen Eintrag.
    // (1989-03-07 liegt in KW 10 — der 2. Januar 1989 war ein Montag.)
    [['year', '1989'], ['month', '1989-03'], ['week', '1989-W10'],
     ['day', '1989-03-07']].forEach(([mode, key]) => {
      w.eval(`mp.mode = ${JSON.stringify(mode)}; rebuildPeriods();`);
      const has = w.eval(`mp.periods.includes(${JSON.stringify(key)})`);
      ok(`Nur-Wohnort-Zeitraum ist ansteuerbar (${mode})`, has === true,
         `${key} fehlt in ${w.eval('mp.periods.length')} Zeiträumen — die `
         + 'Ebene ist dann gebaut und gezeichnet, aber nicht erreichbar');
    });

    // Und derselbe Weg mit dem Schalter AUS: die Zeiträume dürfen dann nicht
    // stehen bleiben. Ohne diese Gegenrichtung prüfte die Zusicherung oben nur,
    // dass es die Schlüssel GIBT — nicht, dass sie vom Wohnort kommen.
    w.eval("mp.mode = 'year'; mp.showBaseline = false; rebuildPeriods();");
    ok('…und mit ausgeschalteter Ebene nicht mehr',
       w.eval("mp.periods.includes('1989')") === false,
       `${JSON.stringify(w.eval('mp.periods'))}`);
    w.eval('mp.showBaseline = true; rebuildPeriods();');

    // Jetzt wirklich hingehen.
    w.eval("mp.index = mp.periods.indexOf('1989');");
    state.fits.length = 0;
    w.eval('renderPeriod();');
    await wait(80);

    const marks = w.eval('mapBaseline.getLayers()');
    ok('Auf 1989 steht das Wohnort-Zeichen', marks.length === 1,
       `${marks.length} Zeichen`);

    // (2) Der Tropfen — dieselbe Zeichnung wie überall, nur in eigener Farbe.
    // Geprüft am SYMBOL, nicht an der Funktion: ein `circleMarker` in der
    // gedämpften Textfarbe war der gemeldete Zustand („der graue Ring geht
    // unter"), und beides ist hier zu sehen.
    const mark = marks[0] || {};
    const html = (mark.opt && mark.opt.icon && mark.opt.icon.html) || '';
    ok('…als Tropfen, nicht als Ring', mark.kind === 'marker'
       && /<path d="M12 32/.test(html),
       `${mark.kind} / ${String(html).slice(0, 80)} — ein Kreis auf der `
       + 'Leinwand liegt unter allem, was nach ihm gezeichnet wird');
    ok('…in einer eigenen Farbe, nicht in der Textfarbe',
       /fill="[^"]+"/.test(html) && !/8a95ad/i.test(html),
       String(html).slice(0, 120));
    ok('…und ohne Ziffer darin', !/<b[ >]/.test(html),
       'die Größe eines Tropfens sagt „so viele Einträge" — die Tageszahl '
       + 'eines Wohnorts ist gerade keine Zahl über Einträge');

    // (3) Der Ausschnitt. Ohne Ereignisse gibt es sonst nichts, worauf die
    // Karte springen könnte, und das Bild bleibt beim vorigen Zeitraum stehen.
    const fitLL = state.fits.map(b => JSON.stringify(b && b.ll)).join(' ');
    ok('…und der Ausschnitt springt darauf', /53\.93/.test(fitLL),
       `${fitLL || '(kein fitBounds)'} — sonst liegt das Zeichen außerhalb `
       + 'des Bildes, und sichtbar ist eine leere Karte');

    // (4) Die Liste daneben.
    const stops = d.getElementById('mp-stops').textContent;
    ok('…und die Liste daneben nennt ihn', /Elternhaus/.test(stops)
       && /(abgeleitet|derived)/i.test(stops),
       `${stops.slice(0, 160)} — „0 Stopps" über einem Jahr, für das es sehr `
       + 'wohl eine Auskunft gibt, ist die Stille aus A40');
    w.close();
  }

  // --- 3. Ein gewählter Tag ist eine Auswahl über EINTRÄGE ------------------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    // **Der Tages-Zoom gehört dazu.** Im ersten Anlauf stand hier keiner, und
    // die Zusicherung war grün, weil die Jahresansicht ihre Zeilen ohnehin zu
    // Sammelzeilen faltet — sie prüfte also die ZOOMSTUFE, nicht den Filter
    // (Anmerkung 108, und derselbe Fall wie in Anmerkung 159).
    w.eval("tl.zoom = 'day'; tl.day = '1990-03-07';");
    await w.loadTimeline();
    await wait(150);
    ok('Ein gewählter Tag zeigt keine abgeleiteten Zeilen',
       d.getElementById('timeline-list').querySelectorAll('.baseline-day').length === 0,
       'wer auf „kältester Tag" klickt, fragt nach den EINTRÄGEN dieses Tages');
    w.close();
  }

  // --- 4. Die Jahres-Sammelzeile sagt, was eine Zahl bedeutet --------------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    w.eval("tl.zoom = 'year';");
    await w.loadTimeline();
    await wait(150);
    // Die erste Sammelzeile ist der Dezember 1990 — ein Monat, in dem
    // ausschließlich abgeleitete Tage liegen. Genau dort muss die Zahl der
    // Ereignisse NULL sein.
    const agg = d.querySelector('[data-agg-group]');
    const chips = agg ? [...agg.querySelectorAll('.ev-meta .chip')]
      .map(c => c.textContent.trim()) : [];
    const evChip = chips.find(c => /events|Ereignisse/.test(c)) || '';
    const dvChip = chips.find(c => /derived|abgeleitet/.test(c)) || '';
    ok('Die Sammelzeile zählt abgeleitete Tage NICHT als Ereignisse',
       /^0\b/.test(evChip) && /^[1-9]/.test(dvChip),
       `${JSON.stringify(chips)} — „26 Ereignisse" über einen Monat, in dem `
       + 'niemand etwas erfasst hat, ist die Vermischung aus Anmerkung 143');
    ok('…und weist sie als abgeleitet aus',
       agg && agg.querySelector('.badge-baseline'),
       'eine Zahl, die mitzählt, muss sagen, woher sie kommt (A40)');
    // **Anmerkung 182 — hier war der Deckel nicht eine Auslassung, sondern
    // eine FALSCHE ZAHL.** Der Dezember 1990 hat 31 abgeleitete Tage; die
    // Stichprobe von 300 aus 364 machte daraus 26, und das stand als
    // gerundete Tatsache in einer Sammelzeile, der man die Auswahl nicht
    // ansieht. Deshalb hat Jahr/Jahrzehnt gar kein Fenster mehr — gemessen
    // kostet das nichts (`tools/measure-timeline.js`), weil `TL_GROUP_CAP`
    // die Zeilen je Gruppe ohnehin begrenzt.
    ok('…und zählt sie VOLLSTÄNDIG', /^31\b/.test(dvChip),
       `${JSON.stringify(dvChip)} — der Dezember 1990 hat 31 abgeleitete Tage; `
       + 'jede kleinere Zahl ist die Größe einer Stichprobe, die als Aussage '
       + 'über den Monat auftritt');
    // Und die Tage stehen trotzdem da — sie sind die führende Zahl.
    ok('…während die Tage weiter zählen',
       /^[1-9]/.test(chips.find(c => /days|Tage/.test(c)) || ''),
       JSON.stringify(chips));
    w.close();
  }

  console.log(fail ? `\nWohnort-Tage: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nWohnort-Tage: alles grün');
  process.exit(fail ? 1 : 0);
}, 60);
