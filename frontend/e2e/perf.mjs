// Scroll-smoothness harness. Usage:
//   node e2e/perf.mjs [baseUrl] [apiUrl] [label]
// Logs in via the API, visits each page, then drives a trackpad-like wheel scroll on the page and on the
// biggest inner scroller, sampling requestAnimationFrame intervals + long tasks + CDP timing metrics.
// NOTE: headless Chromium rasterises on the CPU, so absolute fps is pessimistic; compare runs to each other.
import { chromium } from '@playwright/test';

const BASE = process.argv[2] ?? 'http://localhost:3000';
const API = process.argv[3] ?? 'http://localhost:8000';
const LABEL = process.argv[4] ?? 'run';
const PAGES = ['/', '/intelligence', '/trends', '/markets', '/competitors', '/events', '/pricing', '/copilot', '/executive', '/venues/calendar', '/data'];

const res = await fetch(`${API}/auth/login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: 'qa@liveiq.dev', password: 'QaTest#2026' }) });
const { tokens } = await res.json();

const browser = await chromium.launch({ args: ['--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--disable-frame-rate-limit'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await ctx.addInitScript(([t]) => {
  localStorage.setItem('liveiq_access_token', t.access_token);
  localStorage.setItem('liveiq_refresh_token', t.refresh_token);
  localStorage.setItem('liveiq-theme', 'dark');
}, [tokens]);

const out = [];
for (const path of PAGES) {
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Performance.enable');
  const t0 = Date.now();
  await page.goto(BASE + path, { waitUntil: 'networkidle' }).catch(() => {});
  const loadMs = Date.now() - t0;
  await page.waitForTimeout(1800);

  // JS transferred + LCP
  const nav = await page.evaluate(() => {
    const js = performance.getEntriesByType('resource').filter(r => r.name.includes('.js')).reduce((a, r) => a + (r.transferSize || r.encodedBodySize || 0), 0);
    return { jsKB: Math.round(js / 1024), nodes: document.getElementsByTagName('*').length };
  });

  async function measure(name, target) {
    await page.evaluate(() => {
      window.__f = []; window.__lt = 0;
      let last = performance.now();
      const tick = t => { window.__f.push(t - last); last = t; window.__raf = requestAnimationFrame(tick); };
      window.__raf = requestAnimationFrame(tick);
      try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt += e.duration; }).observe({ type: 'longtask', buffered: false }); } catch {}
    });
    const m0 = await cdp.send('Performance.getMetrics');
    await page.mouse.move(target.x, target.y);
    for (let i = 0; i < 70; i++) { await page.mouse.wheel(0, i < 35 ? 90 : -90); await page.waitForTimeout(16); }
    await page.waitForTimeout(250);
    const m1 = await cdp.send('Performance.getMetrics');
    const f = await page.evaluate(() => { cancelAnimationFrame(window.__raf); return { f: window.__f.slice(2), lt: window.__lt }; });
    const g = (m, k) => m.metrics.find(x => x.name === k)?.value ?? 0;
    const d = k => Math.round((g(m1, k) - g(m0, k)) * 1000);
    const s = [...f.f].sort((a, b) => a - b);
    const avg = f.f.reduce((a, b) => a + b, 0) / Math.max(1, f.f.length);
    return {
      name, frames: f.f.length, fps: +(1000 / avg).toFixed(1), p95ms: +(s[Math.floor(s.length * 0.95)] ?? 0).toFixed(1),
      over17: f.f.filter(x => x > 17.5).length, over34: f.f.filter(x => x > 34).length, longTaskMs: Math.round(f.lt),
      scriptMs: d('ScriptDuration'), layoutMs: d('LayoutDuration'), styleMs: d('RecalcStyleDuration'),
    };
  }

  // biggest scrollable element (inner scroller) vs. the page itself
  const inner = await page.evaluate(() => {
    let best = null, area = 0;
    for (const el of document.querySelectorAll('*')) {
      const cs = getComputedStyle(el);
      if (!/(auto|scroll)/.test(cs.overflowY) || el.scrollHeight <= el.clientHeight + 40) continue;
      const r = el.getBoundingClientRect(); const a = r.width * r.height;
      if (a > area && r.width > 250) { area = a; best = { x: r.x + r.width / 2, y: r.y + r.height / 2, sh: el.scrollHeight }; }
    }
    return best;
  });
  const results = [];
  results.push(await measure('page', { x: 760, y: 500 }));
  if (inner) results.push(await measure('inner', inner));
  out.push({ path, loadMs, ...nav, results });
  await page.close();
}
await browser.close();

console.log(`\n=== ${LABEL}  (${BASE}) ===`);
console.log('page'.padEnd(18), 'load', 'jsKB', 'dom ', '| scroller  fps  p95  >17ms >34ms  longTask  script layout style');
for (const o of out) {
  o.results.forEach((r, i) => console.log(
    (i === 0 ? o.path : '').padEnd(18), String(i === 0 ? o.loadMs : '').padEnd(4), String(i === 0 ? o.jsKB : '').padEnd(4), String(i === 0 ? o.nodes : '').padEnd(5),
    '|', r.name.padEnd(8), String(r.fps).padEnd(5), String(r.p95ms).padEnd(5), String(r.over17).padEnd(5), String(r.over34).padEnd(5), String(r.longTaskMs).padEnd(9), String(r.scriptMs).padEnd(6), String(r.layoutMs).padEnd(6), r.styleMs));
}
const all = out.flatMap(o => o.results);
const score = { avgFps: +(all.reduce((a, r) => a + r.fps, 0) / all.length).toFixed(1), jankFrames: all.reduce((a, r) => a + r.over34, 0), totalLongTaskMs: all.reduce((a, r) => a + r.longTaskMs, 0), totalScriptMs: all.reduce((a, r) => a + r.scriptMs, 0) };
console.log('SUMMARY', JSON.stringify(score));
