/* Runtime smoke test for a page: runs its inline script against a stub DOM with real fetches to a running local server and reports errors.
   Usage (server up on :8000):  node tools/page_harness.js web/pages/analysis.html "#TCS/3m/fundamental"
   Catches what node --check cannot: handlers bound to elements that no longer exist, bad data paths. Forms and third-party libraries are stubbed. */
const fs = require('fs');
const page = process.argv[2], hash = process.argv[3] || '';
const html = fs.readFileSync(page, 'utf8');
const ids = new Set([...html.matchAll(/id="([A-Za-z0-9_-]+)"/g)].map(m => m[1]));
function el(id) {
  const e = { id, children: [], style: {}, dataset: {}, hidden: false, _html: '', textContent: '', value: '', className: '',
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, setAttribute() {}, getAttribute() { return null; }, removeAttribute() {}, appendChild() {}, insertBefore() {}, remove() {},
    insertAdjacentHTML() {}, scrollIntoView() {}, closest() { return null; }, querySelector() { return el('x'); }, querySelectorAll() { return []; }, focus() {}, click() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 400 }; }, clientWidth: 800, clientHeight: 400, scrollTop: 0, scrollHeight: 0 };
  Object.defineProperty(e, 'innerHTML', { get() { return e._html; }, set(v) { e._html = String(v); e.paint = (e.paint || 0) + 1; } });
  return e;
}
const els = {};
function get(id) { if (!els[id]) els[id] = el(id); return els[id]; }
const document = {
  querySelector(s) { const m = /^#([A-Za-z0-9_-]+)$/.exec(s); if (m) { if (!ids.has(m[1])) { console.log('MISSING id', m[1]); } return get(m[1]); } return el(s); },
  querySelectorAll() { return []; }, getElementById(id) { return ids.has(id) ? get(id) : null; },
  createElement() { return el('new'); }, addEventListener() {}, dispatchEvent() {}, body: el('body'), head: el('head'), documentElement: { dataset: {} }, hidden: false, title: '',
};
const errors = [];
global.window = global; global.addEventListener = () => {}; global.removeEventListener = () => {}; global.document = document; global.location = { hash: hash, pathname: '/analysis', host: '127.0.0.1:8000', protocol: 'http:', href: '', reload() {} };
global.localStorage = { getItem() { return null; }, setItem() {} }; global.sessionStorage = global.localStorage;
global.navigator = {}; global.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o && o.detail; } };
global.getComputedStyle = () => ({ getPropertyValue: () => '#000' });
global.LightweightCharts = null; global.confirm = () => false; global.prompt = () => null; global.alert = () => {};
const realFetch = global.fetch;
global.fetch = (u, o) => realFetch('http://127.0.0.1:8000' + u, o);
process.on('unhandledRejection', e => { errors.push('unhandled: ' + (e && e.stack || e)); });
for (const f of ['web/static/js/common.js', 'web/static/js/ui.js']) { try { new Function(fs.readFileSync(f, 'utf8'))(); } catch (e) { errors.push(f + ': ' + e.stack); } }
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => !s.includes("localStorage.getItem('dd.theme')"));
for (const s of scripts) { try { new Function(s)(); } catch (e) { errors.push('inline: ' + e.stack); } }
setTimeout(() => {
  console.log('errors:', errors.length); errors.forEach(e => console.log(e));
  const painted = Object.values(els).filter(e => e.paint).map(e => e.id + '(' + e._html.length + ')');
  console.log('painted:', painted.join(' '));
  process.exit(0);
}, 9000);
