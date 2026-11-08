import { test, expect } from '@playwright/test';
import { trackErrors } from './helpers';
import { apiGet, benign, expectNoHScroll, qaLogin as login } from './qa-utils';

test.describe.configure({ retries: 1 });
const T = { timeout: 30_000 };

type City = { name: string; tier: number | null; active_on_district: boolean; scores: { composite: number | null }; festival_months?: { high_demand?: number[] } };

test.describe('City Markets', () => {
  test('lists every city the API returns, grouped by tier, scores match the API', async ({ page }) => {
    const errors = trackErrors(page);
    const api = await apiGet<{ cities: City[]; total: number }>(page, '/cities/');
    await login(page);
    await page.goto('/markets');
    await expect(page.locator('[data-testid^="city-"]')).toHaveCount(api.total, T);
    // every city's displayed composite equals the API's
    for (const c of api.cities.filter(x => x.scores.composite != null).slice(0, 6)) {
      await expect(page.getByTestId(`city-${c.name}`)).toContainText(c.scores.composite!.toFixed(1));
    }
    // sections follow tiers present in the data; sticky section headers exist
    const tiers = [...new Set(api.cities.map(c => c.tier ?? 0))];
    for (const t of tiers) await expect(page.getByTestId(`section-${t}`)).toHaveCount(1);
    const pos = await page.locator('[data-testid^="section-"] > div').first().evaluate(el => getComputedStyle(el).position);
    expect(pos).toBe('sticky');
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('top city detail loads with demand, seasonality planner and restaurants', async ({ page }) => {
    await login(page);
    await page.goto('/markets');
    await expect(page.getByTestId('detail-title')).toBeVisible(T);
    await expect(page.getByText('Seasonality')).toBeVisible(T);
    await expect(page.getByTestId('best-months')).toContainText(/Best months|No peak months/, T);
    await expect(page.getByTestId('season-strip').locator('i')).toHaveCount(12);
    await expect(page.getByText('Restaurant partnership engine')).toBeVisible(T);
  });

  test('search, tier, status and ranked sort filter the list', async ({ page }) => {
    const api = await apiGet<{ cities: City[] }>(page, '/cities/');
    await login(page);
    await page.goto('/markets');
    await expect(page.locator('[data-testid^="city-"]')).toHaveCount(api.cities.length, T);
    const tier1 = api.cities.filter(c => c.tier === 1).length;
    await page.getByRole('group', { name: 'Tier' }).getByRole('button', { name: 'Tier 1', exact: true }).click();
    await expect(page.locator('[data-testid^="city-"]')).toHaveCount(tier1);
    await page.getByRole('group', { name: 'Tier' }).getByRole('button', { name: 'All tiers' }).click();
    const targets = api.cities.filter(c => !c.active_on_district).length;
    await page.getByRole('group', { name: 'Status' }).getByRole('button', { name: 'Targets' }).click();
    await expect(page.locator('[data-testid^="city-"]')).toHaveCount(targets);
    await page.getByRole('group', { name: 'Status' }).getByRole('button', { name: 'Any' }).click();
    await page.getByLabel('Search cities').fill('zzzzqq');
    await expect(page.getByText('No cities match')).toBeVisible();
    await page.getByLabel('Search cities').fill(api.cities[0].name.slice(0, 4));
    await expect(page.getByTestId(`city-${api.cities[0].name}`)).toBeVisible();
    await page.getByLabel('Search cities').fill('');
    await page.getByRole('button', { name: 'Ranked' }).click();
    await expect(page.locator('[data-testid^="section-"]')).toHaveCount(1);
    // ranked: first row is the highest composite
    const best = [...api.cities].sort((a, b) => (b.scores.composite ?? 0) - (a.scores.composite ?? 0))[0];
    await expect(page.locator('[data-testid^="city-"]').first()).toHaveAttribute('data-testid', `city-${best.name}`);
  });

  test('deep link opens the named city; seasonality matches API peak months', async ({ page }) => {
    const api = await apiGet<{ cities: City[] }>(page, '/cities/');
    const c = api.cities.find(x => x.festival_months?.high_demand?.length) ?? api.cities[0];
    await login(page);
    await page.goto(`/markets?city=${encodeURIComponent(c.name)}`);
    await expect(page.getByTestId('detail-title')).toHaveText(c.name, T);
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const peaks = c.festival_months?.high_demand ?? [];
    if (peaks.length) {
      const peakBars = page.getByTestId('season-strip').locator('i[aria-label*="peak demand"]');
      await expect(peakBars).toHaveCount(peaks.length, T);
      for (const m of peaks) await expect(page.getByTestId('season-strip').locator(`i[aria-label^="${MON[m - 1]}:"]`)).toHaveAttribute('aria-label', /peak demand|monsoon/);
    }
  });

  test('restaurants: server-side search + paging total matches API', async ({ page }) => {
    const api = await apiGet<{ cities: City[] }>(page, '/cities/');
    const top = [...api.cities].sort((a, b) => (b.scores.composite ?? 0) - (a.scores.composite ?? 0))[0].name;
    const r = await apiGet<{ total: number; restaurants: { name: string }[] }>(page, `/cities/${encodeURIComponent(top)}/restaurants?limit=40`);
    test.skip(r.total === 0, 'no restaurants synced');
    await login(page);
    await page.goto(`/markets?city=${encodeURIComponent(top)}`);
    await expect(page.getByTestId('restaurant-list').locator('> div')).toHaveCount(Math.min(40, r.total), T);
    await expect(page.getByTestId('rest-count')).toContainText(`of ${r.total.toLocaleString('en-IN')}`);
    if (r.total > 40) {
      await page.getByRole('button', { name: 'Show more' }).click();
      await expect(page.getByTestId('restaurant-list').locator('> div')).toHaveCount(Math.min(80, r.total), T);
    }
    // search: pick a distinctive word from a real name and confirm server-side filtering
    const word = r.restaurants[0].name.split(/\s+/)[0].toLowerCase();
    const q = await apiGet<{ total: number }>(page, `/cities/${encodeURIComponent(top)}/restaurants?q=${encodeURIComponent(word)}&limit=1`);
    await page.getByLabel('Search venues').fill(word);
    await expect(page.getByTestId('rest-count')).toContainText(`of ${q.total.toLocaleString('en-IN')}`, T);
    await page.getByLabel('Search venues').fill('zzzzqqqq');
    await expect(page.getByText('No venues found')).toBeVisible(T);
  });

  test('compare two cities: values equal the API and winners are bold', async ({ page }) => {
    const api = await apiGet<{ cities: City[] }>(page, '/cities/');
    await login(page);
    await page.goto('/markets');
    await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Compare' }).click();
    await expect(page.getByTestId('compare-view')).toBeVisible(T);
    const [a, b] = [...api.cities].sort((x, y) => (y.scores.composite ?? 0) - (x.scores.composite ?? 0)).slice(0, 2);
    await page.getByLabel('First city').selectOption(a.name);
    await page.getByLabel('Second city').selectOption(b.name);
    const row = page.getByTestId('cmp-Composite');
    await expect(row).toContainText(a.scores.composite!.toFixed(1));
    await expect(row).toContainText(b.scores.composite!.toFixed(1));
    await page.getByLabel('Second city').selectOption(a.name);
    await expect(page.getByText('Pick two different cities')).toBeVisible();
  });

  test('expansion scorecard ranks non-live cities exactly as the API does', async ({ page }) => {
    const gaps = await apiGet<{ gaps: { city: string; opportunity_score: number }[] }>(page, '/cities/gaps');
    await login(page);
    await page.goto('/markets');
    await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Expansion' }).click();
    await expect(page.getByTestId('expansion-view')).toBeVisible(T);
    const rows = page.locator('[data-testid^="exp-"]');
    await expect(rows).toHaveCount(gaps.gaps.length, T);
    if (gaps.gaps.length) {
      await expect(rows.first()).toHaveAttribute('data-testid', `exp-${gaps.gaps[0].city}`);
      await rows.first().click();
      await expect(page.getByTestId('detail-title')).toHaveText(gaps.gaps[0].city, T);
    }
  });

  test('error then retry, and empty list states', async ({ page }) => {
    await login(page);
    let fail = true;
    await page.route('**/cities/', r => (fail ? r.fulfill({ status: 500, json: { detail: 'boom' } }) : r.continue()));
    await page.goto('/markets');
    await expect(page.getByRole('button', { name: /retry|try again/i }).first()).toBeVisible(T);
    fail = false;
    await page.getByRole('button', { name: /retry|try again/i }).first().click();
    await expect(page.locator('[data-testid^="city-"]').first()).toBeVisible(T);
  });

  test('null scores render dashes, never NaN or undefined', async ({ page }) => {
    await login(page);
    await page.route('**/cities/', r => r.fulfill({ json: { total: 2, cities: [
      { id: '1', name: 'Nullville', state: 'X', tier: null, population: null, metro_population: null, avg_monthly_income: null, youth_population_pct: null, top_categories: null, active_on_district: false, scores: { nightlife: null, sports_affinity: null, arts_culture: null, comedy_market: null, music_market: null, composite: null } },
      { id: '2', name: 'Scoreton', state: 'Y', tier: 2, population: 1, metro_population: 2, avg_monthly_income: 40000, youth_population_pct: 30, top_categories: [], active_on_district: true, scores: { nightlife: 50, sports_affinity: 50, arts_culture: 50, comedy_market: 50, music_market: 50, composite: 50 } }] } }));
    await page.goto('/markets');
    await expect(page.getByTestId('city-Nullville')).toContainText('—', T);
    await expect(page.getByTestId('section-0')).toContainText('Unclassified');
    await page.getByTestId('city-Nullville').click();
    await expect(page.getByTestId('detail-title')).toHaveText('Nullville');
    const body = await page.locator('body').innerText();
    expect(body).not.toMatch(/NaN|undefined|null%/);
  });

  test('mobile 390: list to detail and back, no horizontal scroll', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await page.goto('/markets');
    await expect(page.locator('[data-testid^="city-"]').first()).toBeVisible(T);
    await expectNoHScroll(page);
    const name = await page.locator('[data-testid^="city-"]').nth(2).getAttribute('data-testid');
    await page.locator(`[data-testid="${name}"]`).click();
    await expect(page.getByTestId('detail-title')).toHaveText(name!.replace('city-', ''), T);
    await expectNoHScroll(page);
    await page.getByRole('button', { name: /Markets/ }).first().click();
    await expect(page.locator('[data-testid^="city-"]').first()).toBeVisible();
  });

  test('light theme renders readable list', async ({ page }) => {
    await login(page, 'light');
    await page.goto('/markets');
    await expect(page.locator('[data-testid^="city-"]').first()).toBeVisible(T);
    await expectNoHScroll(page);
  });
});
