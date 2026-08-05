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
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
  }
});
setTimeout(async () => {
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
  // Anmerkung 148: „Tage mit Wetter" ist als Kachel WEG — sie zählte den
  // Fortschritt des Wetter-Laufs, nicht das Leben. Die Zahl bleibt trotzdem im
  // Spiel (Schalter für den Block, Bezugsgröße der Regentage), deshalb steht
  // hier die Gegenprobe: sie darf nicht mehr als eigene Kachel auftauchen.
  ok('„Tage mit Wetter" ist keine Kachel mehr', !/300/.test(shown));
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

  // ---- Anmerkung 194: ein Rekord-Tag ohne Eintrag ------------------------
  //
  // Seit die Rekorde beide Tagesarten kennen, schickt der Server für einen
  // Wohnort-Tag `derived: true` und KEINEN Titel. Zwei Dinge können daran
  // schiefgehen, und beide sind still:
  //
  //   1. Die Anzeige schreibt `x.title` hin — dann steht in der Kachel „null".
  //   2. Sie lässt den leeren Titel einfach weg — dann sieht ein gefolgerter
  //      Tag aus wie ein erfasster, und der Unterschied, um den es in F20
  //      überhaupt geht, ist genau an der Stelle weg, an der er zählt.
  //
  // Geprüft wird deshalb beides: kein „null", UND die Herkunft steht da.
  const derived = { value: 40.0, id: null, title: null, derived: true,
                    date_start: '2000-01-05T00:00:00', date_precision: 'day',
                    place: 'Bad Segeberg' };
  const own = { value: 20.0, id: 'e1', title: 'Sommertag', derived: false,
                date_start: '2024-05-05T12:00:00', date_precision: 'day',
                place: 'Köln' };
  ok('Ein abgeleiteter Tag wird benannt',
     /\S/.test(w.wxWho(derived)) && !/null|undefined/.test(w.wxWho(derived)));
  ok('…und als abgeleitet erkennbar', w.wxWho(derived) !== w.wxWho(own));
  ok('Ein erfasster Tag behält seinen Titel', w.wxWho(own) === 'Sommertag');

  // Dieselbe Zeile in der Rangliste darunter (Anmerkung 156: eine Rechnung,
  // zwei Anzeigen — dann muss auch die zweite es sagen).
  w.renderStatsTops({ weather: { hot: [derived, own] }, places: [], cities: [] });
  const tops = d.getElementById('stats-tops').textContent.replace(/\s+/g, ' ');
  ok('Die Rangliste nennt den Wohnort-Tag als abgeleitet',
     tops.includes('Bad Segeberg') && !/null|undefined/.test(tops)
     && tops.includes(w.wxWho(derived).replace(/^🏠 /, '').split(' — ').pop()));

  // Und der Weg, auf dem es gemeldet wurde: die Kachel. Sie entsteht in
  // `loadStats`, also wird `loadStats` gefahren — ein Wächter, der nur die
  // Hilfsfunktion prüft, wäre grün, weil es sie GIBT, nicht weil die Kachel
  // sie benutzt.
  w.fetch = (u) => {
    const p = String(u);
    let body = [];
    if (/stats\/overview/.test(p)) {
      body = { counts: { events: 1, places: 1, cities: 1, concerts: 0,
                         unconfirmed: 0, milestones: 0, moves: 0, meals: 0 },
               age: null, birth: null, extremes: { hot: derived },
               per_year: [], per_category: [], top_places: [], top_cities: [],
               top_animals: [],
               weather: { days: 4, sun_hours: 12, rain_days: 4, rain_share: 100,
                          warmest_trip: null, rain_days_per_year: [[2000, 3]] } };
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  };
  await w.loadStats();
  const sub = d.getElementById('stat-hot-sub').textContent;
  ok('Die Rekord-Kachel zeigt keinen „null"-Titel', !/null|undefined/.test(sub));
  // Gegen den WORTLAUT aus `wxWho` geprüft und nicht gegen eine zweite Fassung
  // davon: unter jsdom läuft die Oberfläche englisch (Anmerkung 114), ein hier
  // eingetippter deutscher Satz stünde also nie im Ergebnis und die Prüfung
  // wäre immer rot — oder, schlimmer, immer grün, wenn man sie danach
  // aufweicht.
  ok('…und sagt, dass der Tag abgeleitet ist',
     sub.includes('Bad Segeberg') && sub.includes(w.wxWho(derived)), sub);

  console.log(fail ? `\n${fail} FEHLER` : '\nA31/A37: alle Prüfungen bestanden');
  process.exit(fail ? 1 : 0);
}, 2500);
