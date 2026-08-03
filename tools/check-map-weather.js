// Anmerkung 157 — das Wetter kommt auf der Karte an, und der zweite Abruf
// weiß, wonach er fragt.
//
// **Der Defekt, den es hier zu verhindern gilt, war unsichtbar und lief mit.**
// `/api/events/map` antwortete bis Anmerkung 110/139 mit einer LISTE; seither
// mit `{total, shown, events}`. Der Nachlade-Aufruf für das Wetter las weiter
// `wx.map(…)` — auf einem Objekt keine Funktion, also eine Ausnahme, also das
// `catch`, das für „ohne Netz kein Wetter" gedacht war. Ergebnis: im
// Marker-Popup und in der Stopp-Liste stand nie wieder ein Wetter, und weil
// der Zeitraum in `MP_WX` schon als geladen vermerkt war, kam es auch beim
// nächsten Blick nicht wieder.
//
// Vier Zusagen, die man dem Bildschirm nicht ansieht, solange er nur „kein
// Wetter" zeigt — was ein völlig plausibler Zustand ist:
//
//   1. Die Punkte kommen OHNE Wetter (A37: es ist der größte Einzelposten der
//      Antwort), das Wetter kommt je angezeigtem Zeitraum nach.
//   2. Der Nachlade-Aufruf lässt die Fotos weg — er fragt nach Wetter für die
//      Pins, und ein Foto-Popup zeigt keins (Anmerkung 157).
//   3. Was ankommt, landet an den geladenen Punkten und wird ANGEZEIGT.
//   4. Ein FEHLGESCHLAGENER Abruf gilt nicht als beantwortet — sonst ist ein
//      einmaliger Netzfehler ein dauerhaft wetterloser Zeitraum (die
//      Endlos-Falle in ihrer Umkehrung, wie in `mpLoadPoints`).
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-map-weather.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// Unverwechselbare Zahl (Regel aus check-a46-visit-split.js): „21,5 °C" kann
// aus keinem Datum und keiner Zählung stammen.
const TEMP = 21.5;
const PIN = {
  id: 'he1', title: 'Konzert', category: 'concert',
  date_start: '2024-07-12T20:00:00', date_precision: 'exact',
  confirmed: 'confirmed', source: 'manual',
  location: { id: 'lh', name: 'Köln', lat: 50.94, lng: 6.96 },
};

function makeDom(state) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.__zoom = 6;
      const popups = state.popups;
      const shape = () => {
        const self = {
          addTo: () => self,
          bindPopup: (c) => { popups.push(String(c)); return self; },
          bindTooltip: () => self, setRadius: () => self, on: () => self,
        };
        return self;
      };
      const base = new Proxy(function () { return base; }, {
        get: (_t, k) => {
          if (k === 'getZoom') return () => w.__zoom;
          if (k === 'marker' || k === 'circleMarker') return shape;
          if (k === 'canvas') return () => ({ _n: 'canvas' });
          return base;
        },
        apply: () => base,
      });
      w.L = base;
      w.fetch = (u, opt) => {
        const p = String(u);
        state.calls.push([(opt && opt.method) || 'GET', p]);
        let body = [];
        if (/events\/map/.test(p)) {
          const wantsWeather = /[?&]weather=1/.test(p);
          if (wantsWeather && state.weatherFails) {
            return Promise.reject(new TypeError('Failed to fetch'));
          }
          const pin = wantsWeather
            ? { ...PIN, weather: { temperature_c: TEMP } } : { ...PIN };
          body = { total: 2, shown: 2, events: [pin],
                   photos: { places: ['Detmold'], cats: ['event'],
                             points: [[51.93, 8.87, '2024-07-12T10:00:00',
                                       'asset-77713', 0, 0]] } };
        } else if (/events\/index/.test(p)) {
          body = { total: 2, dated: 2, undated: 0, unconfirmed: 0, fuzzy: 0,
                   years: [{ year: 2024, count: 2 }], visits: 1,
                   photo_events: 1, machine_proposals: 0, revision: 'r1' };
        } else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/api\/tracks/.test(p)) body = { total: 0, shown: 0, tracks: [] };
        else if (/api\/events\?/.test(p)) body = [];
        else if (/immich\/day-clusters/.test(p)) body = { total: 0, sample: [] };
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
  // --- 1. Der Normalfall: das Wetter kommt nach und wird gezeigt ----------- //
  {
    const state = { calls: [], popups: [], weatherFails: false };
    const w = makeDom(state).window, d = w.document;
    await wait(160);
    await w.openMapView();
    await wait(80);
    state.calls.length = 0; state.popups.length = 0;
    w.eval("mp.mode = 'all'; mp.density = 'point'; rebuildPeriods(); renderPeriod();");
    await wait(200);

    const wxCalls = state.calls.filter(([, p]) => /events\/map/.test(p) && /weather=1/.test(p))
      .map(c => c[1]);
    ok('Das Wetter wird in einem ZWEITEN Aufruf geholt', wxCalls.length === 1,
       `${wxCalls.length} Aufrufe — die Punkte kommen ohne, sonst ist das Wetter `
       + 'der größte Posten der Antwort (A37)');
    ok('…und der lässt die Fotos weg', wxCalls.every(p => /photos=0/.test(p)),
       `${JSON.stringify(wxCalls)} — gefragt ist Wetter für die Pins, ein `
       + 'Foto-Popup zeigt keins');

    // **Die Kernzusage.** Sie fiel um, als der Endpunkt von einer Liste auf ein
    // Objekt umgestellt wurde — und niemand merkte es, weil „kein Wetter" wie
    // ein normaler Zustand aussieht.
    ok('Das geholte Wetter landet am Punkt',
       inPage(w, "(mp.located.find(e => e.id === 'he1') || {}).weather ? "
                 + "mp.located.find(e => e.id === 'he1').weather.temperature_c : null") === TEMP,
       `${inPage(w, "JSON.stringify((mp.located.find(e => e.id === 'he1') || {}).weather)")} `
       + '— ein `catch`, das Netzfehler und Formfehler gleich behandelt, trägt '
       + 'den Defekt statt ihn zu melden');

    const stops = d.getElementById('mp-stops');
    ok('…und steht in der Stopp-Liste', /21[.,]5/.test(stops.textContent),
       stops.textContent.slice(0, 200));
    ok('…und im Marker-Popup', state.popups.some(c => /21[.,]5/.test(c)),
       JSON.stringify(state.popups.slice(0, 2)));
    w.close();
  }

  // --- 2. Ein Fehlschlag darf nicht als beantwortet gelten ---------------- //
  {
    const state = { calls: [], popups: [], weatherFails: true };
    const w = makeDom(state).window;
    await wait(160);
    await w.openMapView();
    await wait(80);
    w.eval("mp.mode = 'all'; mp.density = 'point'; rebuildPeriods(); renderPeriod();");
    await wait(200);
    ok('Nach einem Fehlschlag steht die Karte trotzdem',
       inPage(w, 'mp.located.length') === 2,
       'ohne Wetter bleibt die Karte vollständig — das war nie die Frage');
    ok('…und der Zeitraum gilt NICHT als beantwortet',
       inPage(w, 'MP_WX.size') === 0,
       `${inPage(w, 'MP_WX.size')} vermerkte Zeiträume — sonst ist ein einmaliger `
       + 'Netzfehler ein dauerhaft wetterloser Zeitraum');
    w.close();
  }

  console.log(fail ? `\nKarten-Wetter: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nKarten-Wetter: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
