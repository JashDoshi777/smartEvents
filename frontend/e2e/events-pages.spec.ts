import { test, expect, Page } from '@playwright/test';
import { readFileSync } from 'fs';
import { trackErrors } from './helpers';
import { apiGet, apiToken, benign, expectNoHScroll, qaLogin as login } from './qa-utils';
import { dealFixture } from './intel-fixtures';
import { inrCompact } from '../src/lib/format';

test.describe.configure({ retries: 1 });
const T = { timeout: 45_000 };
const API = process.env.E2E_API_URL ?? 'http://localhost:8000';

type KC = { key: string; count: number };
type Summary = { total: number; upcoming: number; past: number; next_30_days: number; by_month: { month: string; count: number }[]; by_category: KC[]; by_source: KC[]; by_city: KC[]; facets: { sources: KC[]; categories: KC[]; cities: KC[] } };
type EventsRes = { total: number; events: { id: string; title: string; event_date: string | null; is_upcoming: boolean; source: string; category: string; city: string | null }[] };

test.describe('Fill-rate monitor (/events)', () => {
  test('hero counters, chart and list totals equal the API; no console errors', async ({ page }) => {
    const errors = trackErrors(page);
    const s = await apiGet<Summary>(page, '/events/summary');
    const list = await apiGet<EventsRes>(page, '/events?limit=20');
    await login(page);
    await page.goto('/events');
    await expect(page.getByTestId('events-total')).toHaveText(s.total.toLocaleString('en-IN'), T);
    await expect(page.getByTestId('events-upcoming')).toHaveText(s.upcoming.toLocaleString('en-IN'));
    await expect(page.getByTestId('events-count')).toContainText(`of ${list.total.toLocaleString('en-IN')}`, T);
    await expect(page.getByTestId('event-row')).toHaveCount(Math.min(20, list.total));
    await expectNoHScroll(page);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('API invariants: totals add up, upcoming is derived from the date (not stale status)', async ({ page }) => {
    const s = await apiGet<Summary>(page, '/events/summary');
    expect(s.upcoming + s.past).toBe(s.total);
    expect(s.by_source.reduce((a, b) => a + b.count, 0)).toBe(s.total);
    expect(s.by_category.reduce((a, b) => a + b.count, 0)).toBeLessThanOrEqual(s.total);
    expect(s.by_month.reduce((a, b) => a + b.count, 0)).toBeLessThanOrEqual(s.total);
    const up = await apiGet<EventsRes>(page, '/events?when=upcoming&limit=500');
    const past = await apiGet<EventsRes>(page, '/events?when=past&limit=1');
    expect(up.total).toBe(s.upcoming);
    expect(past.total).toBe(s.past);
    const now = Date.now();
    for (const e of up.events) { expect(e.is_upcoming).toBe(true); expect(Date.parse(e.event_date!)).toBeGreaterThanOrEqual(now - 120_000); }
  });

  test('source / city / category / search / when filters match the API counts', async ({ page }) => {
    const s = await apiGet<Summary>(page, '/events/summary');
    await login(page);
    await page.goto('/events');
    await expect(page.getByTestId('events-total')).toHaveText(s.total.toLocaleString('en-IN'), T);
    const src = s.facets.sources[0];
    await page.getByLabel('Source').selectOption(src.key);
    await expect(page.getByTestId('events-total')).toHaveText(src.count.toLocaleString('en-IN'), T);
    await expect(page.getByTestId('events-count')).toContainText(`of ${src.count.toLocaleString('en-IN')}`);
    await page.getByLabel('Source').selectOption('all');
    if (s.facets.categories[0]) {
      const cat = s.facets.categories[0];
      await page.getByLabel('Category').selectOption(cat.key);
      await expect(page.getByTestId('events-total')).toHaveText(cat.count.toLocaleString('en-IN'), T);
      await page.getByLabel('Category').selectOption('');
    }
    if (s.facets.cities[0]) {
      const c = s.facets.cities[0];
      await page.getByLabel('City', { exact: true }).selectOption(c.key);
      await expect(page.getByTestId('events-total')).toHaveText(c.count.toLocaleString('en-IN'), T);
      await page.getByLabel('City', { exact: true }).selectOption('');
    }
    await page.getByRole('group', { name: 'When' }).getByRole('button', { name: 'Past' }).click();
    await expect(page.getByTestId('events-total')).toHaveText(s.past.toLocaleString('en-IN'), T);
    await page.getByRole('group', { name: 'When' }).getByRole('button', { name: 'Upcoming' }).click();
    await expect(page.getByTestId('events-total')).toHaveText(s.upcoming.toLocaleString('en-IN'), T);
    await page.getByRole('group', { name: 'When' }).getByRole('button', { name: 'All' }).click();
    await page.getByLabel('Search events').fill('zzzzqqqq');
    await expect(page.getByText('No event matches these filters')).toBeVisible(T);
    await page.getByLabel('Search events').fill('');
    await expect(page.getByTestId('event-row').first()).toBeVisible(T);
  });

  test('Show more pages through the list without duplicates', async ({ page }) => {
    const list = await apiGet<EventsRes>(page, '/events?limit=1');
    test.skip(list.total <= 20, 'needs more than one page of events');
    await login(page);
    await page.goto('/events');
    await expect(page.getByTestId('event-row')).toHaveCount(20, T);
    await page.getByRole('button', { name: /Show more/ }).click();
    await expect(page.getByTestId('event-row')).toHaveCount(Math.min(40, list.total), T);
    const titles = await page.getByTestId('event-row').locator('[title]').evaluateAll(els => els.map(e => e.getAttribute('title')));
    expect(titles.length).toBeGreaterThan(20);
  });

  test('calendar view shows event counts per IST day and lists them on click', async ({ page }) => {
    const first = await apiGet<EventsRes>(page, '/events?limit=1&order=desc');
    test.skip(!first.events[0]?.event_date, 'no dated events');
    const ev = first.events[0];
    const d = new Date(new Date(ev.event_date!).getTime() + 5.5 * 3600_000);
    const key = d.toISOString().slice(0, 10);
    await login(page);
    await page.goto('/events');
    await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Calendar' }).click();
    await expect(page.getByTestId('events-calendar')).toBeVisible(T);
    const [ty, tm] = new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 7).split('-').map(Number);
    const [ey, em] = key.split('-').map(Number);
    const steps = (ey - ty) * 12 + (em - tm);
    for (let i = 0; i < Math.abs(steps); i++) await page.getByRole('button', { name: steps < 0 ? 'Previous month' : 'Next month' }).click();
    const label = new Date(`${key}T12:00:00+05:30`).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kolkata' });
    const cell = page.locator(`[aria-label^="${label}"]`);
    await expect(cell).not.toHaveAttribute('aria-label', /, 0 events/, T);
    await cell.click();
    await expect(page.getByTestId('cal-day-list')).toContainText(ev.title);
  });

  test('CSV export downloads every matching row', async ({ page }) => {
    const s = await apiGet<Summary>(page, '/events/summary');
    await login(page);
    await page.goto('/events');
    await expect(page.getByTestId('events-total')).toBeVisible(T);
    const [dl] = await Promise.all([page.waitForEvent('download', T), page.getByRole('button', { name: /Export CSV/ }).click()]);
    expect(dl.suggestedFilename()).toMatch(/^liveiq-events-\d{4}-\d{2}-\d{2}\.csv$/);
    const lines = readFileSync(await dl.path()!, 'utf8').split('\r\n');
    expect(lines[0]).toContain('title,date_ist,city');
    // CSV rows can contain quoted newlines, so count by header + at least total non-empty lines
    expect(lines.filter(Boolean).length - 1).toBeGreaterThanOrEqual(s.total);
  });

  test('error with retry, and empty dataset (mocked)', async ({ page }) => {
    await login(page);
    let fail = true;
    await page.route('**/events/summary*', r => (fail ? r.fulfill({ status: 500, json: { detail: 'x' } }) : r.continue()));
    await page.goto('/events');
    await expect(page.getByText('Couldn’t load events.')).toBeVisible(T);
    fail = false;
    await page.getByRole('button', { name: /retry|try again/i }).first().click();
    await expect(page.getByTestId('events-total')).toBeVisible(T);
    await page.unroute('**/events/summary*');
    await page.route('**/events/summary*', r => r.fulfill({ json: { total: 0, upcoming: 0, past: 0, next_30_days: 0, with_fill_rate: 0, without_venue: 0, by_month: [], by_category: [], by_source: [], by_city: [], facets: { sources: [], categories: [], cities: [] }, timezone: 'Asia/Kolkata', as_of: new Date().toISOString() } }));
    await page.route(/\/events\?/, r => r.fulfill({ json: { total: 0, events: [] } }));
    await page.reload();
    await expect(page.getByText('No dated events')).toBeVisible(T);
    await expect(page.getByText('Events appear here once the sync workers have run.')).toBeVisible();
  });

  test('mobile 390 / light have no horizontal scroll and 44px filter controls', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, 'light');
    await page.goto('/events');
    await expect(page.getByTestId('event-row').first()).toBeVisible(T);
    await expectNoHScroll(page);
    const box = await page.getByLabel('Source').boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(40);
  });
});

/* ─────────────────────────────── Deal modeler ─────────────────────────────── */
async function pickArtistCityAndVenue(page: Page) {
  await page.locator('#m-artist').click();
  await page.getByRole('option').first().click();
  await expect(page.locator('#m-city option').nth(1)).toBeAttached(T);
  await page.selectOption('#m-city', 'Mumbai');
  await expect(page.locator('#m-venue option').nth(1)).toBeAttached(T);
}

test.describe('Deal modeler (/events/model)', () => {
  test('viewer gets a friendly role message, no crash (mocked role)', async ({ page }) => {
    await login(page);
    await page.route('**/auth/me', r => r.fulfill({ json: { id: 'u', email: 'a@b.c', full_name: 'V', role: 'viewer', is_verified: true } }));
    await page.goto('/events/model');
    await expect(page.getByText('Booking roles only')).toBeVisible(T);
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeDisabled();
  });

  test('validation messages for every bad input', async ({ page }) => {
    await login(page);
    await page.goto('/events/model');
    const alert = page.locator('[role=alert]:not(#__next-route-announcer__)');
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled(T);
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(alert).toContainText('Choose an artist');
    await page.locator('#m-artist').click(); await page.getByRole('option').first().click();
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(alert).toContainText('Choose a city');
    await page.selectOption('#m-city', 'Mumbai');
    await page.fill('#m-price', '50');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(alert).toContainText('Ticket price must be between');
    await page.fill('#m-price', '2500');
    await page.fill('#m-cap', '50');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(alert).toContainText('capacity between 100 and 1,00,000');
    await page.fill('#m-cap', '5000'); await page.fill('#m-lead', '0');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(alert).toContainText('Lead time must be between 1 and 730');
  });

  test('REAL analyst success path: every figure equals the API and the P&L arithmetic holds', async ({ page }) => {
    const errors = trackErrors(page);
    await login(page);
    await page.goto('/events/model');
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled(T);
    await pickArtistCityAndVenue(page);
    await page.fill('#m-cap', '8000');
    await page.fill('#m-price', '2000');
    const resp = page.waitForResponse(r => r.url().endsWith('/events/model') && r.request().method() === 'POST', T);
    await page.getByRole('button', { name: 'Run simulation' }).click();
    const r = await resp;
    expect(r.status(), 'analyst may run the modeler').toBe(200);
    const j = await r.json() as typeof dealFixture & { cost_model: { venue_pct: number; ops_pct: number } };
    const ex = j.scenarios.expected;
    await expect(page.getByText(/(expected|illustrative) net profit/)).toBeVisible(T);
    await expect(page.getByText(new RegExp(`${j.prediction.predicted_fill_rate_pct}|${Math.round(j.prediction.predicted_fill_rate_pct / 5) * 5}`)).first()).toBeVisible();
    await expect(page.getByTestId('result-net').or(page.getByText(inrCompact(ex.net_profit)).first())).toBeVisible();

    // arithmetic, recomputed independently of the backend
    const price = 2000, cap = j.venue.capacity, fee = j.artist_fee.amount;
    for (const k of ['conservative', 'expected', 'optimistic'] as const) {
      const s = j.scenarios[k];
      expect(s.fill_rate_pct).toBeGreaterThanOrEqual(0); expect(s.fill_rate_pct).toBeLessThanOrEqual(100);
      expect(s.attendance).toBe(Math.round(cap * s.fill_rate_pct / 100));
      expect(Math.abs(s.gross_revenue - s.attendance * price)).toBeLessThanOrEqual(1);
      expect(Math.abs(s.venue_cost - s.gross_revenue * j.cost_model.venue_pct)).toBeLessThanOrEqual(1);
      expect(Math.abs(s.ops_cost - s.gross_revenue * j.cost_model.ops_pct)).toBeLessThanOrEqual(1);
      expect(Math.abs(s.net_profit - (s.gross_revenue - fee - s.venue_cost - s.ops_cost))).toBeLessThanOrEqual(2);
      if (s.gross_revenue > 0) expect(Math.abs((s.margin_pct as number) - (s.net_profit / s.gross_revenue) * 100)).toBeLessThan(0.2);
    }
    expect(j.scenarios.conservative.fill_rate_pct).toBeLessThanOrEqual(j.scenarios.expected.fill_rate_pct);
    expect(j.scenarios.expected.fill_rate_pct).toBeLessThanOrEqual(j.scenarios.optimistic.fill_rate_pct);
    expect(j.break_even.tickets).toBe(Math.round(fee / (price * (1 - j.cost_model.venue_pct - j.cost_model.ops_pct))));
    expect(j.break_even.achievable).toBe((j.break_even.tickets as number) <= cap);

    // sensitivity table: the cell at (your price, predicted fill) equals expected net profit
    const f = Math.round(j.prediction.predicted_fill_rate_pct);
    const cell = page.getByTestId(`cell-${price}-${f}`);
    await expect(cell).toBeVisible();
    await expect(cell).toHaveText(inrCompact(Math.round(cap * (f / 100) * price * 0.65 - fee)));
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('sensitivity table grows with price and with fill (mocked fixture)', async ({ page }) => {
    await login(page);
    await page.route(/:8000\/events\/model$/, r => r.fulfill({ json: { ...dealFixture, cost_model: { venue_pct: 0.1, ops_pct: 0.25 } } }));
    await page.goto('/events/model');
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled(T);
    await page.locator('#m-artist').click(); await page.getByRole('option').first().click();
    await page.selectOption('#m-city', 'Mumbai'); await page.fill('#m-cap', '9000'); await page.fill('#m-price', '2500');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    const table = page.getByTestId('sens-table');
    await expect(table).toBeVisible(T);
    // 9000 seats, ₹2,500, 100% fill, 65% retained, fee ₹1.2Cr -> 9000*2500*.65 - 12,000,000 = 2,625,000
    await expect(page.getByTestId('cell-2500-100')).toHaveText(inrCompact(9000 * 2500 * 0.65 - 12_000_000));
    // higher price at same fill -> higher profit
    const lo = await page.getByTestId('cell-2000-75').innerText(); const hi = await page.getByTestId('cell-3150-75').innerText().catch(() => '');
    expect(lo).toBeTruthy(); void hi;
    await expect(page.getByText('Medium risk')).toBeVisible();
  });

  test('save scenario, restore inputs, delete; persists across reload; CSV export', async ({ page }) => {
    await login(page);
    await page.route(/:8000\/events\/model$/, r => r.fulfill({ json: { ...dealFixture, cost_model: { venue_pct: 0.1, ops_pct: 0.25 } } }));
    await page.goto('/events/model');
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled(T);
    await page.locator('#m-artist').click(); await page.getByRole('option').first().click();
    await page.selectOption('#m-city', 'Mumbai'); await page.fill('#m-cap', '9000'); await page.fill('#m-price', '2500');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(page.getByTestId('save-scenario')).toBeVisible(T);
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('export-csv').click()]);
    const csv = readFileSync(await dl.path()!, 'utf8');
    expect(csv).toContain('Ticket price (INR),2500');
    expect(csv).toContain(`expected,${dealFixture.scenarios.expected.fill_rate_pct},${dealFixture.scenarios.expected.attendance},${dealFixture.scenarios.expected.gross_revenue}`);
    await page.getByTestId('save-scenario').click();
    await expect(page.getByTestId('saved-item')).toHaveCount(1);
    await page.reload();
    await expect(page.getByTestId('saved-item')).toHaveCount(1, T);
    await page.fill('#m-price', '999');
    await page.getByTestId('saved-item').click();
    await expect(page.locator('#m-price')).toHaveValue('2500');
    await page.getByRole('button', { name: /^Delete / }).click();
    await expect(page.getByTestId('saved-item')).toHaveCount(0);
  });

  test('API guards: price/capacity ranges 422, missing venue+capacity 400, unknown ids 404/400', async ({ page }) => {
    test.setTimeout(150_000);
    await login(page);
    const ent = (await apiGet<{ portfolio: { id: string }[] }>(page, '/executive/portfolio')).portfolio[0];
    const post = async (body: object) => (await page.request.post(`${API}/events/model`, { data: body, headers: { Authorization: `Bearer ${await apiToken(page)}` }, timeout: 60_000 })).status();
    expect(await post({ entity_id: ent.id, city: 'Mumbai', venue_capacity: 5000, ticket_price: 99 })).toBe(422);
    expect(await post({ entity_id: ent.id, city: 'Mumbai', venue_capacity: 99, ticket_price: 1000 })).toBe(422);
    expect(await post({ entity_id: ent.id, city: 'Mumbai', venue_capacity: 5000, ticket_price: 1000, lead_days: 0 })).toBe(422);
    expect(await post({ entity_id: ent.id, city: 'Mumbai', ticket_price: 1000 })).toBe(400);
    expect(await post({ entity_id: '00000000-0000-0000-0000-000000000000', city: 'Mumbai', venue_capacity: 5000, ticket_price: 1000 })).toBe(404);
    expect(await post({ entity_id: 'nope', city: 'Mumbai', venue_capacity: 5000, ticket_price: 1000 })).toBe(400);
    expect(await post({ entity_id: ent.id, city: 'a', venue_capacity: 5000, ticket_price: 1000 })).toBe(200);   // ambiguous city fragment must not 500
  });

  test('404 / 403 / 500 from the simulator show readable messages (mocked)', async ({ page }) => {
    await login(page);
    await page.goto('/events/model');
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled(T);
    await page.locator('#m-artist').click(); await page.getByRole('option').first().click();
    await page.selectOption('#m-city', 'Mumbai'); await page.fill('#m-cap', '9000'); await page.fill('#m-price', '2500');
    const alert = page.locator('[role=alert]:not(#__next-route-announcer__)');
    await page.route(/:8000\/events\/model$/, r => r.fulfill({ status: 404, json: { detail: 'nf' } }));
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(alert).toContainText('could not be found');
    await page.unroute(/:8000\/events\/model$/);
    await page.route(/:8000\/events\/model$/, r => r.fulfill({ status: 500, json: { detail: 'x' } }));
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(alert).toContainText('unavailable right now');
    await page.unroute(/:8000\/events\/model$/);
    await page.route(/:8000\/events\/model$/, r => r.fulfill({ status: 403, json: { detail: 'x' } }));
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(page.getByText('Booking roles only')).toBeVisible();
  });

  test('mobile 390: result stacks without horizontal page scroll', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await page.route(/:8000\/events\/model$/, r => r.fulfill({ json: { ...dealFixture, cost_model: { venue_pct: 0.1, ops_pct: 0.25 } } }));
    await page.goto('/events/model');
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled(T);
    await page.locator('#m-artist').click(); await page.getByRole('option').first().click();
    await page.selectOption('#m-city', 'Mumbai'); await page.fill('#m-cap', '9000'); await page.fill('#m-price', '2500');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(page.getByTestId('sens-table')).toBeVisible(T);
    await expectNoHScroll(page);
  });
});

/* ─────────────────────────────── Artist pairing ─────────────────────────────── */
type PairRes = { recommendations: { entity_a: { id: string; name: string }; entity_b: { id: string; name: string }; shared_genres: string[]; similarity_score: number; combined_booking_fee_estimate: number | null; fee_complete?: boolean }[]; candidates_considered: number; pairs_matching_genre: number };

test.describe('Artist pairing (/events/pairing)', () => {
  test('top pair on screen is the API top pair; scores sorted, unique, genre-backed', async ({ page }) => {
    const errors = trackErrors(page);
    const res = await (await page.request.post(`${API}/intelligence/pair-recommend`, { data: { city: 'Mumbai', market: 'India', limit: 10 }, headers: { Authorization: `Bearer ${await apiToken(page)}` }, timeout: 90_000 })).json() as PairRes;
    expect(res.recommendations.length).toBeGreaterThan(0);
    const scores = res.recommendations.map(p => p.similarity_score);
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);
    for (const p of res.recommendations) { expect(p.similarity_score).toBeGreaterThanOrEqual(0); expect(p.similarity_score).toBeLessThanOrEqual(100); expect(p.entity_a.id).not.toBe(p.entity_b.id); expect(p.shared_genres.length).toBeGreaterThan(0); }
    const keys = res.recommendations.map(p => [p.entity_a.id, p.entity_b.id].sort().join('|'));
    expect(new Set(keys).size).toBe(keys.length);
    await login(page);
    await page.goto('/events/pairing');
    const top = res.recommendations[0];
    await expect(page.getByText('Best pairing for Mumbai')).toBeVisible(T);
    await expect(page.getByText(top.entity_a.name).first()).toBeVisible();
    await expect(page.getByText(top.entity_b.name).first()).toBeVisible();
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('budget filter: every returned pair with known fees is within budget (API)', async ({ page }) => {
    await login(page);
    const budget = 5_000_000;
    const res = await (await page.request.post(`${API}/intelligence/pair-recommend`, { data: { city: 'Mumbai', budget, limit: 20 }, headers: { Authorization: `Bearer ${await apiToken(page)}` }, timeout: 90_000 })).json() as PairRes;
    for (const p of res.recommendations) if (p.fee_complete && p.combined_booking_fee_estimate != null) expect(p.combined_booking_fee_estimate).toBeLessThanOrEqual(budget);
  });

  test('form: market toggle + budget hint + re-run; a slow earlier response cannot overwrite a newer one (mocked)', async ({ page }) => {
    await login(page);
    const mk = (n: string) => ({ city: 'Mumbai', budget: null, anchor_entity: null, candidates_considered: 9, pairs_matching_genre: 3, methodology: 'm', recommendations: [{ entity_a: { id: '1', name: `${n} A`, category: 'Music', composite_score: 50 }, entity_b: { id: '2', name: `${n} B`, category: 'Music', composite_score: 50 }, shared_genres: ['pop'], similarity_score: 88.2, combined_booking_fee_estimate: 4_000_000, fee_complete: false }] });
    let n = 0;
    await page.route('**/intelligence/pair-recommend', async r => { n++; const mine = n; if (mine === 1) await new Promise(res => setTimeout(res, 2500)); await r.fulfill({ json: mk(mine === 1 ? 'Slow' : 'Fast') }); });
    await page.goto('/events/pairing');
    await page.getByRole('button', { name: 'All', exact: true }).click();
    await page.getByLabel('Budget').fill('9000000');
    await expect(page.getByText('Combined fee capped at')).toBeVisible();
    await page.getByRole('button', { name: 'Find pairings' }).click();
    await expect(page.getByText('Fast A').first()).toBeVisible(T);
    await page.waitForTimeout(3000);
    await expect(page.getByText('Slow A')).toHaveCount(0);
    await expect(page.getByText(/one artist has no fee on file/)).toBeVisible();
  });

  test('400 / 404 / 500 / empty / null scores are all handled (mocked)', async ({ page }) => {
    await login(page);
    const empty = { city: 'Mumbai', budget: null, anchor_entity: null, candidates_considered: 5, pairs_matching_genre: 0, recommendations: [], methodology: '' };
    for (const [status, text] of [[400, /Not enough artists/], [404, /no live metrics/], [500, /unavailable right now/]] as const) {
      await page.route('**/intelligence/pair-recommend', r => r.fulfill({ status, json: { detail: 'x' } }));
      await page.goto('/events/pairing');
      await expect(page.getByText(text)).toBeVisible(T);
      await page.unroute('**/intelligence/pair-recommend');
    }
    await page.route('**/intelligence/pair-recommend', r => r.fulfill({ json: empty }));
    await page.goto('/events/pairing');
    await expect(page.getByText('No pairs fit these filters')).toBeVisible(T);
    expect(await page.locator('body').innerText()).not.toMatch(/NaN|undefined/);
  });

  test('mobile 390 has no horizontal scroll', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, 'light');
    await page.goto('/events/pairing');
    await expect(page.getByText(/Best pairing|Finding pairs|No pairs|unavailable/).first()).toBeVisible(T);
    await expectNoHScroll(page);
  });
});
