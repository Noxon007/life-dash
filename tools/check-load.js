const fs = require('fs');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = w.matchMedia || (() => ({ matches:false, addEventListener(){}, addListener(){} }));
    w.L = new Proxy(function(){ return w.L; }, { get: () => w.L, apply: () => w.L });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
    w.addEventListener('unhandledrejection', e => errors.push('REJECT: ' + (e.reason && e.reason.message || e.reason)));
  },
});
setTimeout(() => {
  const w = dom.window;
  const fatal = errors.filter(e => !/offline|Not implemented|fetch/i.test(e));
  console.log(fatal.length ? fatal.join('\n') : 'Laden ohne Fehler');
  console.log('renderOnThisDay:', typeof w.renderOnThisDay);
  console.log('otd-block im DOM:', !!w.document.getElementById('otd-block'));
  console.log('resolve-scope entfernt:', !w.document.getElementById('resolve-scope'));
  console.log('btn-resolve-run da:', !!w.document.getElementById('btn-resolve-run'));
  process.exit(fatal.length ? 1 : 0);
}, 2500);
