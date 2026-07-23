// A36: die Wetterzeile der Ereigniskarte (weatherSummary) muss aus BEIDEN
// Formaten dasselbe erzeugen — der schlanken Liste (e.weather, kompakt) und
// der vollen Liste (e.metrics, Rohzeilen). Sonst zeigt der Zeitstrahl nach der
// slim-Umstellung kein Wetter mehr, obwohl die Statistik es noch tut.
const fs = require('fs');
const { JSDOM } = require('jsdom');
const file = process.argv[2] || 'frontend/index.html';
const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('x'));
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
  },
});
setTimeout(() => {
  const w = dom.window;
  let fail = 0;
  const ok = (n, c) => { console.log((c ? '  ok   ' : '  FAIL ') + n); if (!c) fail++; };

  const m = (key, value, value_text) => ({ key, value, value_text, source: 'weather' });
  const full = { metrics: [
    m('temp_min_c', 12), m('temp_max_c', 23), m('weather', null, 'Regen'),
    m('sunshine_h', 4), m('rain_mm', 5.6), m('sunrise', null, '05:20'),
    m('sunset', null, '21:40'), m('weather_rev', 2),
  ] };
  const slim = { weather: { temp_min_c: 12, temp_max_c: 23, weather: 'Regen',
    sunshine_h: 4, rain_mm: 5.6, sunrise: '05:20', sunset: '21:40' } };

  const fullLine = w.weatherSummary(full);
  const slimLine = w.weatherSummary(slim);
  ok('volle Liste ergibt eine Wetterzeile', /12–23 °C/.test(fullLine) && /Regen/.test(fullLine));
  ok('schlanke Liste ergibt eine Wetterzeile', /12–23 °C/.test(slimLine) && /Regen/.test(slimLine));
  ok('beide Formate ergeben DASSELBE', fullLine === slimLine);
  ok('Sonnenlauf in beiden', /🌅 05:20–21:40/.test(fullLine) && /🌅 05:20–21:40/.test(slimLine));
  ok('interner Marker weather_rev taucht nicht auf', !/weather_rev|· 2 ·/.test(fullLine));
  ok('ohne Wetter keine Zeile', w.weatherSummary({ metrics: [] }) === null && w.weatherSummary({}) === null);

  console.log(fail ? `\n${fail} FEHLER` : '\nWetterzeile: schlank und voll identisch');
  process.exit(fail ? 1 : 0);
}, 2500);
