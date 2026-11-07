import { chromium } from '@playwright/test';
import fs from 'fs';
const SC = process.argv[2];
const tok = JSON.parse(fs.readFileSync(`${SC}/tok.json`)).tokens;
const pages = ['/','/intelligence','/intelligence/forecast','/trends','/markets','/competitors','/events','/events/model','/events/pairing','/pricing','/executive','/copilot','/listening','/psychology','/recommendations','/venues/calendar','/watchlist','/settings','/login'];
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addInitScript(t => { localStorage.setItem('liveiq_access_token', t.access_token); localStorage.setItem('liveiq_refresh_token', t.refresh_token); }, tok);
for (const p of pages) {
  const page = await ctx.newPage(); const errs = []; const bad = [];
  page.on('console', m => { if (m.type()==='error') errs.push(m.text().slice(0,140)); });
  page.on('pageerror', e => errs.push('PAGEERR '+e.message.slice(0,140)));
  page.on('response', r => { if (r.status()>=400) bad.push(r.status()+' '+r.url().slice(0,90)); });
  const t = Date.now();
  await page.goto('http://localhost:3000'+p, { waitUntil: 'load' }).catch(e=>errs.push('NAV '+e.message));
  await page.waitForTimeout(6000);
  await page.screenshot({ path: `${SC}/shots/${p.replace(/\//g,'_')||'_'}.png` });
  console.log(p, Date.now()-t+'ms', 'errs:', JSON.stringify(errs.slice(0,3)), 'bad:', JSON.stringify(bad.slice(0,4)));
  await page.close();
}
await b.close();
