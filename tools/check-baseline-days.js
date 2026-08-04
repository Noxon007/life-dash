// F20 / Anmerkung 144 — der Grundort erreicht den Zeitstrahl.
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
//   3. **Der Deckel schneidet nicht ab, er verteilt** — und SAGT, dass er
//      deckelt. `all.slice(0, 300)` war der Defekt aus Anmerkung 110 und noch
//      einmal aus Anmerkung 160; hier wäre er zum dritten Mal möglich.
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
    // der Tag mit einem Eintrag fehlt — der Grundort füllt nur Lücken
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
      const base = new Proxy(function () { return base; }, {
        get: (_t, k) => (k === 'getZoom' ? () => 6 : base), apply: () => base,
      });
      w.L = base;
      w.fetch = (u, opt) => {
        const p = String(u);
        state.calls.push([(opt && opt.method) || 'GET', p]);
        if (opt && opt.method === 'POST') (state.posts || []).push({ url: p, opt });
        let body = [];
        if (/\/api\/baselines$/.test(p) && opt && opt.method === 'POST') {
          return Promise.resolve({ ok: true, status: 201,
                                   json: () => Promise.resolve({ id: 'b9', day_count: 2192 }) });
        }
        if (/\/api\/baselines$/.test(p)) {
          return Promise.resolve({ ok: true, status: 200,
                                   json: () => Promise.resolve([]) });
        }
        if (/days\/baseline/.test(p)) {
          const [from, to] = span(p);
          const days = state.noBaseline ? {} : daysOfYear(from, to);
          body = { periods: (state.noBaseline || !Object.keys(days).length) ? []
                     : [{ id: 'b1', label: LABEL, place: PLACE,
                          city: 'Bad Segeberg', country: 'Deutschland' }],
                   days };
        } else if (/days\/weather/.test(p)) {
          // Das Wetter liegt an einem Tag, den NUR die Grundort-Spanne
          // umfasst — die Seite kennt genau einen Tag, und das ist ein anderer.
          const [from, to] = span(p);
          const day = state.wxDay || '1990-03-07';
          body = (day >= from && day <= to)
            ? { [day]: { values: { temp_min_c: TEMP, temp_max_c: TEMP }, regions: 1 } }
            : {};
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

    // (3) Der Deckel verteilt und sagt es.
    const shown = inPage(w, 'TL_BASELINE_SHOWN');
    const total = inPage(w, 'TL_BASELINE_TOTAL');
    ok('Der Deckel greift', shown === inPage(w, 'TL_BASELINE_CAP') && total > shown,
       `${shown} von ${total}`);
    const picked = inPage(w,
      "tlBaselineRows().map(r => r.day).sort()");
    ok('…und schneidet nicht vorne ab', Array.isArray(picked)
       && picked[0] < '1990-02-01' && picked[picked.length - 1] > '1990-11-30',
       `${Array.isArray(picked) ? picked[0] + ' … ' + picked[picked.length - 1] : picked}`
       + ' — `slice(0, N)` nähme die ersten N chronologisch, und der Rest des '
       + 'Jahres fehlte, während die Ansicht vollständig aussieht');
    ok('…und die Fußzeile sagt, dass gedeckelt wird',
       /364/.test(list.textContent) && /300/.test(list.textContent),
       'A40: was eine Ansicht nicht alles zeigen kann, muss sie dort sagen, '
       + 'wo hingeschaut wird');

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

  // --- 2. Ohne Grundort ändert sich nichts --------------------------------
  {
    const state = { calls: [], noBaseline: true };
    const w = makeDom(state).window, d = w.document;
    await wait(200);
    await w.loadTimeline();
    await wait(150);
    const list = d.getElementById('timeline-list');
    ok('Ohne Grundort steht keine abgeleitete Zeile da',
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
    // Und die Tage stehen trotzdem da — sie sind die führende Zahl.
    ok('…während die Tage weiter zählen',
       /^[1-9]/.test(chips.find(c => /days|Tage/.test(c)) || ''),
       JSON.stringify(chips));
    w.close();
  }

  console.log(fail ? `\nGrundort-Tage: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nGrundort-Tage: alles grün');
  process.exit(fail ? 1 : 0);
}, 60);
