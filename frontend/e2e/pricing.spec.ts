import { test, expect, Page } from '@playwright/test';
import { trackErrors } from './helpers';
import { apiGet, apiToken, benign, expectNoHScroll, qaLogin as login } from './qa-utils';
import { inr, inrCompact } from '../src/lib/format';

test.describe.configure({ retries: 1 });
const T = { timeout: 45_000 };
const API = process.env.E2E_API_URL ?? 'http://localhost:8000';

type Rec = { recommended_price: number; proposed_price: number; predicted_fill_rate: number; predicted_fill_rate_at_recommended: number; sensitivity_curve: { price: number; attendance_pct: number }[]; price_tier: string };
type Res = { recommendation: Rec; benchmarks: { floor: number; ultra_premium: number; category: string }; model: string; signals: Record<string, number> };

async function pickFirstAct(page: Page) {
  await page.getByTestId('act-picker').click();
  const first = page.locator('button[class*="__pick"]').first();
  await first.waitFor(T);
  const name = (await first.locator('p').first().innerText()).trim();
  await first.click();
  return name;
}
async function firstEntity(page: Page) {
  const p = await apiGet<{ portfolio: { id: string; name: string }[] }>(page, '/executive/portfolio');
  return p.portfolio.find(e => e.name) ?? p.portfolio[0];
}
async function optimizeApi(page: Page, body: object) {
  return page.request.post(`${API}/pricing/optimize`, { data: body, headers: { Authorization: `Bearer ${await apiToken(page)}` }, timeout: 60_000 });
}

const OK = {
  entity: { id: 'x', name: 'Test Act', type: 'artist', category: 'Music', is_international: false },
  recommendation: { proposed_price: 3000, recommended_price: 4200, price_tier: 'Premium', confidence: 'High (ML GBR · 84%)', reasoning: 'Strong signal.', predicted_fill_rate: 60, predicted_fill_rate_at_recommended: 50,
    sensitivity_curve: [1500, 3000, 6000].map((p, i) => ({ price: p, attendance_pct: [95, 60, 30][i] })) },
  signals: { composite_score: 78, google_trend_score: 64, demand_score: 71, city_multiplier: 1.2, capacity_factor: 0.92, season_factor: 1.12, international_factor: 1 },
  benchmarks: { category: 'music', floor: 500, sweet_spot: 2500, premium: 8000, ultra_premium: 25000 }, model: 'ml_gbr',
};

test.describe('Pricing optimizer', () => {
  test('benchmarks in rupees; validation blocks bad input before submit', async ({ page }) => {
    await login(page);
    await page.goto('/pricing');
    await expect(page.getByText('price ladder')).toBeVisible(T);
    await expect(page.getByText(/Floor ₹/)).toBeVisible();
    await page.getByTestId('optimize').click();
    await expect(page.getByText('Choose an act to price.')).toBeVisible();
    await pickFirstAct(page);
    await page.getByLabel('Proposed ticket price').fill('50');
    await page.getByTestId('optimize').click();
    await expect(page.getByRole('alert').filter({ hasText: /Price must be between ₹100 and ₹50,000/ })).toBeVisible();
    await page.getByLabel('Proposed ticket price').fill('3000');
    await page.getByLabel('Venue capacity', { exact: true }).fill('50');
    await page.getByTestId('optimize').click();
    await expect(page.getByRole('alert').filter({ hasText: /Capacity must be a whole number between 100 and 1,00,000/ })).toBeVisible();
  });

  test('REAL analyst success path: UI equals the API response and the math holds', async ({ page }) => {
    const errors = trackErrors(page);
    await login(page);
    await page.goto('/pricing');
    await expect(page.getByText('price ladder')).toBeVisible(T);
    await pickFirstAct(page);
    await page.getByLabel('Venue capacity', { exact: true }).fill('5000');
    await page.getByLabel('Proposed ticket price').fill('2500');
    const resp = page.waitForResponse(r => r.url().includes('/pricing/optimize') && r.request().method() === 'POST', T);
    await page.getByTestId('optimize').click();
    const r = await resp;
    expect(r.status(), 'analyst role must be allowed').toBe(200);
    const j = (await r.json()) as Res;
    const rec = j.recommendation;

    // UI == API
    await expect(page.getByTestId('rec-price')).toHaveText(inr(rec.recommended_price), T);
    await expect(page.getByTestId('result').getByText(`${Math.round(rec.predicted_fill_rate)}%`).first()).toBeVisible();
    await expect(page.getByTestId('fill-at-rec')).toContainText(`${Math.round(rec.predicted_fill_rate_at_recommended)}% fill`);
    // revenue = price x seats x fill (no off-by-anything)
    await expect(page.getByTestId('rev-yours')).toHaveText(inrCompact(Math.round(2500 * 5000 * rec.predicted_fill_rate / 100)));
    await expect(page.getByTestId('rev-rec')).toHaveText(inrCompact(Math.round(rec.recommended_price * 5000 * rec.predicted_fill_rate_at_recommended / 100)));

    // API invariants
    expect(rec.predicted_fill_rate).toBeGreaterThanOrEqual(0);
    expect(rec.predicted_fill_rate).toBeLessThanOrEqual(100);
    expect(rec.recommended_price).toBeGreaterThanOrEqual(j.benchmarks.floor);
    expect(rec.recommended_price).toBeLessThanOrEqual(j.benchmarks.ultra_premium);
    expect(rec.recommended_price % 100).toBe(0);
    if (j.model === 'ml_gbr') {
      const fills = rec.sensitivity_curve.map(p => p.attendance_pct);
      expect([...fills].sort((a, b) => b - a)).toEqual(fills);              // higher price never raises attendance
      expect(rec.sensitivity_curve.find(p => p.price === 2500)?.attendance_pct).toBe(rec.predicted_fill_rate);
    }
    await expect(page.getByTestId('sens-chart')).toBeVisible();
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('API extremes stay in bounds: tiny/huge venue, cheap/expensive, every month, odd city strings', async ({ page }) => {
    await login(page);
    const ent = await firstEntity(page);
    const cases = [
      { venue_capacity: 100, proposed_price: 100 }, { venue_capacity: 100000, proposed_price: 50000 },
      { venue_capacity: 100, proposed_price: 50000 }, { venue_capacity: 100000, proposed_price: 100 },
    ];
    for (const c of cases) {
      const res = await optimizeApi(page, { entity_id: ent.id, city: 'Mumbai', ...c });
      expect(res.status()).toBe(200);
      const j = (await res.json()) as Res;
      expect(j.recommendation.predicted_fill_rate).toBeGreaterThanOrEqual(0);
      expect(j.recommendation.predicted_fill_rate).toBeLessThanOrEqual(100);
      expect(j.recommendation.recommended_price).toBeGreaterThanOrEqual(j.benchmarks.floor);
      expect(j.recommendation.recommended_price).toBeLessThanOrEqual(j.benchmarks.ultra_premium);
    }
    for (const month of [1, 7, 8, 12]) expect((await optimizeApi(page, { entity_id: ent.id, city: 'Pune', venue_capacity: 3000, proposed_price: 2000, event_date_month: month })).status()).toBe(200);
    // previously a 2-city LIKE match raised MultipleResultsFound -> 500; wildcards must be inert
    for (const city of ['a', 'ra', '%', '_', 'Delhi', "x'; drop", 'zzzz nowhere']) expect((await optimizeApi(page, { entity_id: ent.id, city, venue_capacity: 3000, proposed_price: 2000 })).status(), city).toBe(200);
    // out-of-range input is a clean 422, bad id is a 400/404, never a 500
    expect((await optimizeApi(page, { entity_id: ent.id, city: 'Mumbai', venue_capacity: 99, proposed_price: 2000 })).status()).toBe(422);
    expect((await optimizeApi(page, { entity_id: ent.id, city: 'Mumbai', venue_capacity: 3000, proposed_price: 99999 })).status()).toBe(422);
    expect((await optimizeApi(page, { entity_id: 'not-a-uuid', city: 'Mumbai', venue_capacity: 3000, proposed_price: 2000 })).status()).toBe(400);
  });

  test('price monotonicity: a higher proposed price never predicts higher fill (API)', async ({ page }) => {
    await login(page);
    const ent = await firstEntity(page);
    const fills: number[] = [];
    for (const price of [500, 1500, 4000, 12000]) {
      const j = (await (await optimizeApi(page, { entity_id: ent.id, city: 'Mumbai', venue_capacity: 5000, proposed_price: price })).json()) as Res;
      fills.push(j.recommendation.predicted_fill_rate);
    }
    expect([...fills].sort((a, b) => b - a)).toEqual(fills);
  });

  test('save scenarios, compare table survives reload, clear works', async ({ page }) => {
    await login(page);
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('rec-price')).toBeVisible(T);
    await page.getByTestId('save-scenario').click();
    await page.getByLabel('Proposed ticket price').fill('4000');
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('rec-price')).toBeVisible(T);
    await page.getByTestId('save-scenario').click();
    await expect(page.getByTestId('scenario-row')).toHaveCount(2);
    await page.reload();
    await expect(page.getByTestId('scenario-row')).toHaveCount(2, T);
    await page.getByRole('button', { name: 'Clear' }).click();
    await expect(page.getByTestId('scenario-row')).toHaveCount(0);
  });

  test('share link restores inputs and auto-runs the optimizer', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await login(page);
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByLabel('Venue capacity', { exact: true }).fill('3200');
    await page.getByLabel('Proposed ticket price').fill('1800');
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('rec-price')).toBeVisible(T);
    await page.getByTestId('copy-link').click();
    const url = await page.evaluate(() => navigator.clipboard.readText());
    expect(url).toContain('/pricing?act=');
    expect(url).toContain('cap=3200');
    await page.goto(url);
    await expect(page.getByLabel('Venue capacity', { exact: true })).toHaveValue('3200');
    await expect(page.getByLabel('Proposed ticket price')).toHaveValue('1800');
    await expect(page.getByTestId('rec-price')).toBeVisible(T);
  });

  test('chart metric toggle switches to revenue (mocked)', async ({ page }) => {
    await login(page);
    await page.route('**/pricing/optimize', r => r.fulfill({ json: OK }));
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('rec-price')).toHaveText('₹4,200');
    await expect(page.getByText('Expected attendance at each price point')).toBeVisible();
    await page.getByRole('group', { name: 'Chart metric' }).getByRole('button', { name: 'Revenue' }).click();
    await expect(page.getByText(/Best sampled price: ₹/)).toBeVisible();
    // 3000 x 8000 seats x 60% = 1.44 crore; 4200 x 8000 x 50% = 1.68 crore
    await expect(page.getByTestId('rev-yours')).toHaveText(inrCompact(3000 * 8000 * 0.6));
    await expect(page.getByTestId('rev-rec')).toHaveText(inrCompact(4200 * 8000 * 0.5));
  });

  test('forbidden role, 422, 500 and slow responses are handled (mocked)', async ({ page }) => {
    await login(page);
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.route('**/pricing/optimize', r => r.fulfill({ status: 403, json: { detail: 'Insufficient role' } }));
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('role-notice')).toContainText('Analyst', T);
    await page.unroute('**/pricing/optimize');
    await page.route('**/pricing/optimize', r => r.fulfill({ status: 422, json: { detail: [{ loc: ['body', 'venue_capacity'], msg: 'Input should be >= 100' }] } }));
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('error-notice')).toContainText('venue_capacity: Input should be >= 100');
    await page.unroute('**/pricing/optimize');
    await page.route('**/pricing/optimize', r => r.fulfill({ status: 500, json: { detail: 'Internal server error' } }));
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('error-notice')).toContainText(/Internal server error|500/);
    await page.unroute('**/pricing/optimize');
    await page.route('**/pricing/optimize', async r => { await new Promise(res => setTimeout(res, 1500)); await r.fulfill({ json: OK }); });
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('optimize')).toBeDisabled();
    await expect(page.getByTestId('optimize')).toContainText('Analysing');
    await expect(page.getByTestId('rec-price')).toHaveText('₹4,200', T);
  });

  test('null fill in the response renders dashes, not NaN (mocked)', async ({ page }) => {
    await login(page);
    await page.route('**/pricing/optimize', r => r.fulfill({ json: { ...OK, recommendation: { ...OK.recommendation, predicted_fill_rate: null, predicted_fill_rate_at_recommended: null, sensitivity_curve: [] } } }));
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('rec-price')).toBeVisible(T);
    expect(await page.locator('body').innerText()).not.toMatch(/NaN|undefined/);
  });

  test('mobile 390 and light theme have no horizontal scroll', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, 'light');
    await page.route('**/pricing/optimize', r => r.fulfill({ json: OK }));
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('rec-price')).toBeVisible(T);
    await expectNoHScroll(page);
  });
});
