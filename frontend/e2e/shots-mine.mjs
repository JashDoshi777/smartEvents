import { chromium } from '@playwright/test';
import fs from 'fs';
const SC='/private/tmp/claude-501/-Users-jash-doshi-zomato-com-Desktop-event/9552e9da-2773-47bc-b57e-03c883fcc8dc/scratchpad/jash';
const tok = JSON.parse(fs.readFileSync(`${SC}/tok.json`)).tokens;
const only = process.argv[2];
const dealFixture = JSON.parse(fs.readFileSync(`${SC}/deal.json`));
const fc = JSON.parse(fs.readFileSync(`${SC}/fc.json`));
const pages = [
 ['events','/events',null],
 ['model','/events/model','model'],
 ['pairing','/events/pairing',null],
 ['forecast','/intelligence/forecast','forecast'],
 ['copilot','/copilot','copilot'],
];
const b = await chromium.launch();
for (const [name,path,mock] of pages) {
 if (only && only!==name) continue;
 for (const [theme,w,h] of [['dark',1440,900],['light',1440,900],['dark',390,844]]) {
  const ctx = await b.newContext({ viewport:{width:w,height:h}, colorScheme: theme });
  await ctx.addInitScript(([t,th])=>{localStorage.setItem('liveiq_access_token',t.access_token);localStorage.setItem('liveiq_refresh_token',t.refresh_token);localStorage.setItem('liveiq-theme',th);},[tok,theme]);
  const page = await ctx.newPage(); const errs=[];
  page.on('pageerror',e=>errs.push(e.message.slice(0,150)));
  if (mock==='model') { await page.route('**/auth/me', r=>r.fulfill({json:{id:'u',email:'a@b.c',full_name:'B',role:'booker',is_verified:true}})); await page.route('http://localhost:8000/events/model', r=>r.fulfill({json:dealFixture})); }
  if (mock==='forecast') await page.route('**/intelligence/*/forecast*', r=>r.fulfill({json:fc}));
  if (mock==='copilot') await page.route('**/copilot/stream', r=>r.fulfill({contentType:'text/event-stream',body:['**Nagpur** is my pick: strong student base, low venue costs and almost no competition.\n\n','Why it works:\n- Tier-2 city with ~₹45,000 avg monthly income\n- Comedy and indie demand growing\n- Venues under ₹6 L per night\n\n','Start with a **1,200-seat** comedy night at about ₹799.'].map(c=>`data: ${JSON.stringify({chunk:c})}\n\n`).join('')+'data: [DONE]\n\n'}));
  await page.goto('http://localhost:3000'+path,{waitUntil:'networkidle'}).catch(()=>{});
  await page.waitForTimeout(1500);
  if (mock==='model') { await page.locator('#m-artist').click(); await page.getByRole('option').first().click(); await page.selectOption('#m-city',{index:1}); await page.fill('#m-cap','9000'); await page.fill('#m-price','2500'); await page.getByRole('button',{name:'Run simulation'}).click(); await page.waitForTimeout(1800); }
  if (mock==='forecast') { await page.locator('[aria-label="Quick picks"] .chip').first().click(); await page.waitForTimeout(2000); }
  if (mock==='copilot') { await page.getByRole('button',{name:/Tier-2 city/}).click(); await page.waitForTimeout(1500); }
  await page.screenshot({path:`${SC}/${name}-${theme}-${w}.png`});
  console.log(name,theme,w,JSON.stringify(errs),'hscroll',await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
  await ctx.close();
 }
}
await b.close();
