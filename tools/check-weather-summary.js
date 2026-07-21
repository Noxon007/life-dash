// A31/Anmerkung 64 — Wetter gehört einem TAG, nicht einem Eintrag.
//
// Bis v0.31 rechnete `renderWeatherSummary` diese Bilanz selbst, und dieser
// Wächter fütterte sie mit importierten Besuchen. Mit A37 (v0.32) rechnet der
// Server (`services/stats_overview.py`), und die Regel selbst wird dort
// geprüft: tests/test_a37_window.py — „zwölf Besuche sind EIN Regentag".
//
// Damit verschiebt sich das Risiko, und dieser Wächter mit ihm: Die Anzeige
// darf die Server-Zahlen nur noch DARSTELLEN. Würde jemand hier wieder über
// Einträge rechnen (oder die Werte „korrigieren"), kämen andere Zahlen heraus
// als der Server geliefert hat — genau das fällt hier auf.
const fs = require('fs'); const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('x'));
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
  }
});
setTimeout(() => {
  const w = dom.window, d = dom.window.document; let fail = 0;
  const ok = (n, c) => { console.log((c ? '  ok   ' : '  FAIL ') + n); if (!c) fail++; };
  const tiles = () => d.getElementById('weather-tiles').textContent.replace(/\s+/g, ' ');

  // Ein Jahr importierter Besuche, wie der Server sie verdichtet zurückgibt:
  // 300 Kalendertage aus 3.600 Einträgen.
  w.renderWeatherSummary({
    weather: {
      days: 300, sun_hours: 600, rain_days: 120, rain_share: 40,
      warmest_trip: { avg: 25.0, title: 'Andalusien' },
      rain_days_per_year: [[2023, 60], [2024, 60]],
    }
  });
  const shown = tiles();
  ok('Tage mit Wetter = die Zahl des Servers (300)', /(^| )300 /.test(shown));
  ok('Sonnenstunden unverändert übernommen (600 h)', /600 h/.test(shown));
  ok('Regentage unverändert übernommen (120)', /(^| )120 /.test(shown));
  ok('Anteil kommt vom Server (40 %)', /40%/.test(shown));
  ok('Wärmste Reise unverändert (25.0 °C)', /25\.0 °C/.test(shown));
  const vals = [...d.querySelectorAll('#chart-raindays *')]
    .map(x => parseInt(x.textContent, 10)).filter(n => Number.isFinite(n) && n < 1900);
  ok('Regentage je Jahr gezeichnet und unter 366 (' + vals.join(', ') + ')',
     vals.length > 0 && vals.every(n => n <= 366));

  // Ohne Wetterdaten bleibt der Block unsichtbar — eine Bilanz aus null Tagen
  // wäre nur eine Reihe Striche.
  w.renderWeatherSummary({ weather: { days: 0 } });
  ok('ohne Wetterdaten bleibt der Block verborgen',
     d.getElementById('weather-summary').style.display === 'none');

  // Die Bilanz darf nicht mehr selbst über Ereignisse rechnen: die Funktion
  // nimmt genau EIN Argument (die Server-Antwort).
  ok('renderWeatherSummary nimmt die Server-Antwort, keine Ereignisliste',
     w.renderWeatherSummary.length === 1);

  console.log(fail ? `\n${fail} FEHLER` : '\nA31/A37: alle Prüfungen bestanden');
  process.exit(fail ? 1 : 0);
}, 2500);
