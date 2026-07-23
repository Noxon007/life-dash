// A48 — die Vektorkarte fällt nie stumm aus.
//
// Sie kann aus drei Gründen nicht gehen, und **alle drei sehen auf der Karte
// gleich aus: grau**. Keine Stil-URL hinterlegt; die Bibliothek nicht geladen
// (sie kommt vom CDN); kein WebGL (ältere Geräte, abgesicherte Umgebungen).
// Genau deshalb prüft dieser Wächter nicht, ob die Karte gezeichnet wird —
// das kann jsdom gar nicht —, sondern ob die App den Unterschied KENNT und
// ihn dort ausspricht, wo jemand ihn beheben kann.
//
// Die Regel dahinter ist A40, eine Ebene tiefer: ein Bedienelement, das gerade
// nichts bewirken kann, darf nicht angeboten werden — und der Grund gehört in
// die Einstellungen, nicht auf die Karte.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-vector-basemap.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const STYLE = 'https://tiles.example.org/v1/style/dark.json';

// `withGL` stellt beide Voraussetzungen her bzw. entzieht sie: die Brücke
// (`L.maplibreGL`) und einen WebGL-Kontext. Beides muss HERGESTELLT werden —
// den Auslieferungszustand zu lesen prüfte einen Zustand, in dem niemand ist
// (Regel aus check-a41-cities.js).
function makeDom(withGL) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.fetch = () => Promise.reject(new Error('offline'));
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      const L = new Proxy(function () { return L; }, {
        get: (_t, prop) => (prop === 'maplibreGL' && !withGL ? undefined : L),
        apply: () => L,
      });
      w.L = L;
      w.HTMLCanvasElement.prototype.getContext = function (kind) {
        if (kind === 'webgl' || kind === 'webgl2') return withGL ? {} : null;
        return null;
      };
    },
  });
}

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

setTimeout(() => {
  // --- 1. Alles vorhanden ------------------------------------------------ //
  {
    const w = makeDom(true).window, ls = w.localStorage;
    // `BASEMAPS` ist ein `const` auf oberster Ebene und landet damit NICHT auf
    // `window` — der Zugriff läuft über `eval` im Fenster (wie in
    // check-photo-layer.js).
    const bm = k => w.eval(`BASEMAPS.vector.${k}`);
    ok('Es gibt einen Vektor-Eintrag', w.eval('!!BASEMAPS.vector'));
    ok('…und er ist als Vektor gekennzeichnet', bm('vector') === true,
       'daran hängt der zweite Zeichenweg — eine Kachel-URL hat er nicht');

    ls.setItem('lifedash_basemap', 'vector');
    ok('Ohne Stil-URL fällt die Wahl auf auto zurück', w.basemapSetting() === 'auto',
       'sonst stünde man vor einer grauen Fläche');
    ok('…und der Grund steht als SATZ da',
       /Stil-URL|style URL/i.test(w.basemapProblem('vector') || ''),
       String(w.basemapProblem('vector')));

    ls.setItem('lifedash_vectorstyle', STYLE);
    ok('Mit Stil-URL greift die Vektorkarte', w.basemapSetting() === 'vector',
       w.basemapSetting());
    ok('…und meldet kein Problem mehr', !w.basemapProblem('vector'),
       String(w.basemapProblem('vector')));
    ok('Der Stil wird durchgereicht', w.eval('BASEMAPS.vector.style()') === STYLE);

    // Attribution ist Lizenzbedingung, nicht Schmuck — dieselbe Zusage wie
    // bei den Rasterquellen (check-basemaps.js).
    ls.setItem('lifedash_vectorattr', '© Beispielanbieter');
    ok('Die Attribution wird durchgereicht',
       w.eval('BASEMAPS.vector.attribution()') === '© Beispielanbieter');

    // Kein Anbieter darf voreingestellt sein (A27).
    ls.removeItem('lifedash_vectorstyle');
    ok('Ohne Eintrag ist KEIN Anbieter voreingestellt',
       w.eval('BASEMAPS.vector.style()') === '',
       'welche Karte die Daten sieht, entscheidet der Betreiber');
    ok('…und die Auswahl bietet sie dann nicht an',
       !!w.basemapProblem('vector'));

    // `url()` muss existieren, auch wenn es nichts liefert: jeder Aufrufer,
    // der eine Kachel-URL erwartet, bekäme sonst `undefined()` an den Kopf.
    ok('Ein url()-Aufruf stürzt nicht ab',
       w.eval("typeof BASEMAPS.vector.url === 'function' && BASEMAPS.vector.url() === ''"));
    w.close();
  }

  // --- 2. Kein WebGL / keine Bibliothek ---------------------------------- //
  {
    const w = makeDom(false).window, ls = w.localStorage;
    ls.setItem('lifedash_vectorstyle', STYLE);
    ls.setItem('lifedash_basemap', 'vector');
    ok('Ohne WebGL meldet die App das', w.vectorSupported() === false);
    ok('…fällt still auf auto zurück', w.basemapSetting() === 'auto',
       'eine graue Fläche wäre die schlechtere Antwort');
    ok('…aber sagt den Grund, wo man ihn beheben kann',
       /WebGL/i.test(w.basemapProblem('vector') || ''),
       String(w.basemapProblem('vector')));

    // Und die Einstellungsseite zeigt ihn auch wirklich an.
    const d = w.document;
    const box = d.getElementById('vector-state');
    ok('Die Einstellungen haben ein Feld für den Stil', !!d.getElementById('vector-url'));
    w.loadVectorSettings();
    ok('Der Warnhinweis steht in den Einstellungen',
       box && box.style.display !== 'none' && /WebGL/i.test(box.textContent),
       box ? box.textContent : 'kein Feld');
    w.close();
  }

  console.log(fail ? `\nA48-Vektorkarte: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nA48-Vektorkarte: alles grün');
  process.exit(fail ? 1 : 0);
}, 120);
