import { test, expect } from '@playwright/test';
import { trackErrors } from './helpers';
import { apiGet, benign, expectNoHScroll, qaLogin as login } from './qa-utils';

test.describe.configure({ retries: 1 });
const T = { timeout: 45_000 };   // /competitors/intelligence calls two rate-limited third parties on a cold cache

type Cov = { cities: { city: string; market_score: number | null; district_active: boolean }[]; total: number };
type Gaps = { gaps: { city: string; priority: string }[]; total: number };

const INTEL = (extra: object = {}) => ({
  city: 'Mumbai', total_ticketmaster_events_live: 3, data_sources: ['x'],
  district_opportunity: { city_tier: 1, district_active: true, recommendation: 'GROW' },
  platforms: {
    district: { name: 'District by Zomato', parent: 'Zomato', founded: 2022, strengths: ['a', 'b'], markets: ['Mumbai'], active_in_city: true, estimated_events: 7, news_mentions_7d: 12, market_position: 'Growing' },
    bookmyshow: { name: 'BookMyShow', parent: 'Bigtree', founded: 1999, strengths: ['a'], markets: ['All India'], active_in_city: true, news_mentions_7d: 40, market_position: 'Dominant (x)' },
    insider: { name: 'Insider.in', parent: 'Paytm', founded: 2015, strengths: ['a'], markets: ['Mumbai'], active_in_city: true, news_mentions_7d: 5, market_position: 'Challenger' },
    ticketmaster_india: { name: 'Ticketmaster India', parent: 'Live Nation', founded: 2018, strengths: ['a'], markets: ['Mumbai'], active_in_city: true, live_events_count: 3, news_mentions_7d: 0, market_position: 'Niche' },
  }, ...extra,
});

test.describe('Competitors', () => {
  test('platform comparison, coverage, gaps render clean and match the API', async ({ page }) => {
    const errors = trackErrors(page);
    const cov = await apiGet<Cov>(page, '/competitors/coverage');
    await login(page);
    await page.goto('/competitors');
    for (const id of ['district', 'bookmyshow', 'insider', 'ticketmaster_india']) await expect(page.getByTestId(`platform-${id}`)).toBeVisible(T);
    // coverage chart: top 12 by market score, then all on demand
    const rows = page.getByTestId('coverage').locator('button');
    await expect(rows).toHaveCount(Math.min(12, cov.total), T);
    await expect(rows.first()).toHaveAttribute('data-testid', `cov-${cov.cities[0].city}`);
    await expect(rows.first()).toContainText(String(cov.cities[0].market_score));
    if (cov.total > 12) {
      await page.getByRole('button', { name: `Show all ${cov.total}` }).click();
      await expect(rows).toHaveCount(cov.total);
    }
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('district events in the table equal the API for the selected city', async ({ page }) => {
    const intel = await apiGet<{ platforms: { district: { estimated_events: number; active_in_city: boolean } } }>(page, '/competitors/intelligence?city=Mumbai');
    await login(page);
    await page.goto('/competitors');
    const row = page.getByTestId('platform-district');
    await expect(row).toContainText(String(intel.platforms.district.estimated_events), T);
    await expect(row).toContainText(intel.platforms.district.active_in_city ? 'Active in this city' : 'Not active here');
  });

  test('gap priority filter counts equal the gaps API; clicking coverage switches city', async ({ page }) => {
    const gaps = await apiGet<Gaps>(page, '/competitors/gaps');
    const cov = await apiGet<Cov>(page, '/competitors/coverage');
    await login(page);
    await page.goto('/competitors');
    await expect(page.getByText('Market gaps')).toBeVisible(T);
    for (const p of ['HIGH', 'MEDIUM', 'LOW'] as const) {
      const n = gaps.gaps.filter(g => g.priority === p).length;
      await page.getByRole('group', { name: 'Priority' }).getByRole('button', { name: p === 'MEDIUM' ? 'Med' : p[0] + p.slice(1).toLowerCase(), exact: true }).click();
      if (n) await expect(page.getByText(new RegExp(`${p[0]}${p.slice(1).toLowerCase()} priority`, 'i'))).toHaveCount(n);
      else await expect(page.getByText('No cities at this priority.')).toBeVisible();
    }
    await page.getByRole('group', { name: 'Priority' }).getByRole('button', { name: 'All' }).click();
    const target = cov.cities.find(c => !c.district_active) ?? cov.cities[1];
    const btn = page.getByTestId(`cov-${target.city}`);
    if (await btn.count()) { await btn.click(); await expect(page.getByLabel('City', { exact: true })).toHaveValue(target.city); }
  });

  test('news unavailable (rate limited) shows dashes and a notice, never fake zeros (mocked)', async ({ page }) => {
    await login(page);
    await page.route('**/competitors/intelligence*', r => r.fulfill({ json: INTEL({ news_available: false }) }));
    await page.route('**/competitors/activity-feed*', r => r.fulfill({ json: { articles: [], total: 0, platforms_monitored: [], news_available: false } }));
    await page.goto('/competitors');
    await expect(page.getByTestId('news-unavailable')).toBeVisible(T);
    await expect(page.getByTestId('news-district')).toHaveText('—');
    await expect(page.getByText('News is unavailable')).toBeVisible();
  });

  test('live news counts render when available; feed filter chips and safe links (mocked)', async ({ page }) => {
    await login(page);
    await page.route('**/competitors/intelligence*', r => r.fulfill({ json: INTEL({ news_available: true }) }));
    await page.route('**/competitors/activity-feed*', r => r.fulfill({ json: { total: 2, platforms_monitored: ['BookMyShow'], news_available: true, articles: [
      { platform: 'BookMyShow', title: 'BMS launches X', source: 'ET', published_at: '2026-11-01T10:00:00Z', url: 'https://example.com/a' },
      { platform: 'Insider.in', title: 'Insider does Y', source: 'Mint', published_at: '2026-11-02T10:00:00Z', url: null }] } }));
    await page.goto('/competitors');
    await expect(page.getByTestId('news-district')).toHaveText('12', T);
    await expect(page.getByTestId('news-bookmyshow')).toHaveText('40');
    const link = page.locator('a[href="https://example.com/a"]');
    await expect(link).toHaveAttribute('rel', /noopener/);
    await expect(link).toHaveAttribute('target', '_blank');
    await page.getByRole('button', { name: 'Insider.in', exact: true }).click();
    await expect(page.getByText('BMS launches X')).toHaveCount(0);
    await expect(page.getByText('Insider does Y')).toBeVisible();
  });

  test('intelligence 500 shows retry that recovers', async ({ page }) => {
    await login(page);
    let fail = true;
    await page.route('**/competitors/intelligence*', r => (fail ? r.fulfill({ status: 500, json: { detail: 'x' } }) : r.fulfill({ json: INTEL() })));
    await page.goto('/competitors');
    await expect(page.getByText('Couldn’t load the platform comparison.')).toBeVisible(T);
    fail = false;
    await page.getByRole('button', { name: /retry|try again/i }).first().click();
    await expect(page.getByTestId('platform-district')).toBeVisible(T);
  });

  test('mobile 390 has no horizontal scroll; light theme', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, 'light');
    await page.route('**/competitors/intelligence*', r => r.fulfill({ json: INTEL({ news_available: true }) }));
    await page.goto('/competitors');
    await expect(page.getByTestId('platform-district')).toBeVisible(T);
    await expect(page.getByTestId('coverage')).toBeVisible(T);
    await expectNoHScroll(page);
  });
});
