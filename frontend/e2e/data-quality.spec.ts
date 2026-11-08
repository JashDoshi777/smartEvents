import { test, expect } from '@playwright/test';
import { trackErrors } from './helpers';
import { apiGet, apiToken, benign, expectNoHScroll, qaLogin as login } from './qa-utils';

test.describe.configure({ retries: 1 });
const T = { timeout: 30_000 };
const API = process.env.E2E_API_URL ?? 'http://localhost:8000';

type Gaps = { scope_total: number; total: number; summary_missing_counts: Record<string, number>; items: { id: string; name: string; missing: string[] }[] };

test.describe('Data quality', () => {
  test('coverage matches /admin/data-gaps and the kind switch works', async ({ page }) => {
    const errors = trackErrors(page);
    const api = await apiGet<Gaps>(page, '/admin/data-gaps?kind=entities&page_size=1');
    await login(page);
    await page.goto('/data');
    await expect(page.getByRole('heading', { name: 'Data quality', level: 1 })).toBeVisible(T);
    const lang = api.summary_missing_counts.language;
    const pct = Math.round((1 - lang / api.scope_total) * 100);
    await expect(page.getByTestId('cov-language')).toContainText(`${pct}%`, T);
    await expect(page.getByTestId('gap-count')).toContainText(String(api.total).replace(/\B(?=(\d{3})+(?!\d))/g, ','), T);
    await page.getByRole('group', { name: 'Record type' }).getByRole('button', { name: 'Cities' }).click();
    await expect(page.getByTestId('cov-nightlife_score')).toBeVisible(T);
    await expectNoHScroll(page);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('missing-field filter narrows the list and CSV export downloads', async ({ page }) => {
    const api = await apiGet<Gaps>(page, '/admin/data-gaps?kind=venues&missing=address&page_size=1');
    await login(page);
    await page.goto('/data');
    await page.getByRole('group', { name: 'Record type' }).getByRole('button', { name: 'Venues' }).click();
    await page.getByRole('group', { name: 'Missing fields' }).getByRole('button', { name: /^Address/ }).click();
    await expect(page.getByTestId('gap-count')).toContainText(new RegExp(String(api.total).replace(/\B(?=(\d{3})+(?!\d))/g, ',')), T);
    const [dl] = await Promise.all([page.waitForEvent('download', T), page.getByTestId('export-gaps').click()]);
    expect(dl.suggestedFilename()).toMatch(/liveiq-data-gaps-venues-.*\.csv$/);
  });

  test('edit sheet validates, saves optimistically with toast (PATCH mocked)', async ({ page }) => {
    await login(page);
    let body: Record<string, unknown> | null = null;
    await page.route('**/admin/venues/*', async route => {
      if (route.request().method() !== 'PATCH') return route.continue();
      body = route.request().postDataJSON();
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'x', kind: 'venues', changed: { lat: { old: null, new: 19.1 } }, unchanged: [], provenance: { lat: { source: 'manual', by: 'qa@liveiq.dev', at: '2026-11-08T12:00:00+00:00' } } }) });
    });
    await page.goto('/data');
    await page.getByRole('group', { name: 'Record type' }).getByRole('button', { name: 'Venues' }).click();
    await page.getByRole('group', { name: 'Missing fields' }).getByRole('button', { name: /^Lat/ }).click();
    await expect(page.getByTestId('gap-row').first()).toContainText(/Lat/, T);
    await page.getByTestId('gap-row').first().click();
    const lat = page.getByLabel('Lat', { exact: true });
    await lat.fill('99');
    await page.getByTestId('save-record').click();
    await expect(page.getByText('Must be at most 38.')).toBeVisible();
    expect(body).toBeNull();
    await lat.fill('19.1');
    await page.getByTestId('save-record').click();
    await expect(page.getByText(/^Saved /)).toBeVisible(T);
    expect(body).toEqual({ lat: 19.1 });
  });

  test('real PATCH round trip on an unchanged field leaves data untouched', async ({ page }) => {
    const gaps = await apiGet<Gaps>(page, '/admin/data-gaps?kind=entities&missing=language&page_size=1');
    const id = gaps.items[0].id;
    const prof = await apiGet<{ category: string }>(page, `/entities/${id}/profile`);
    test.skip(!prof.category, 'needs an entity with a category');
    const res = await page.request.patch(`${API}/admin/entities/${id}`, { headers: { Authorization: `Bearer ${await apiToken(page)}` }, data: { category: prof.category } });
    expect(res.status()).toBe(200);
    const j = await res.json();
    expect(j.unchanged).toContain('category');
    expect(j.changed).toEqual({});
    const bad = await page.request.patch(`${API}/admin/entities/${id}`, { headers: { Authorization: `Bearer ${await apiToken(page)}` }, data: { nope: 1 } });
    expect(bad.status()).toBe(422);
  });

  test('Run now: analyst gets a friendly 403 message; 202 shows started', async ({ page }) => {
    await login(page);
    await page.goto('/data');
    await expect(page.getByTestId('job-news_backfill')).toBeVisible(T);
    await page.getByTestId('run-news_backfill').click();
    await expect(page.getByTestId('jobs-denied')).toContainText('Executive', T);
    // mocked executive path
    await page.route('**/admin/jobs/*/run', r => r.fulfill({ status: 202, contentType: 'application/json', body: '{"status":"started"}' }));
    await page.reload();
    await page.getByTestId('run-free_signals').click();
    await expect(page.getByText(/free signals started/)).toBeVisible(T);
  });

  test('viewer role sees a read-only notice', async ({ page }) => {
    await login(page);
    await page.route('**/auth/me', async r => { const res = await r.fetch(); const j = await res.json(); await r.fulfill({ response: res, json: { ...j, role: 'viewer' } }); });
    await page.goto('/data');
    await expect(page.getByTestId('viewer-notice')).toBeVisible(T);
  });

  test('sidebar and settings link to it', async ({ page }) => {
    await login(page);
    await page.goto('/settings');
    await expect(page.getByText('About the data')).toBeVisible(T);
    await expect(page.getByTestId('last-refreshed')).toBeVisible(T);
    await page.getByRole('link', { name: /Data quality/ }).last().click();
    await expect(page).toHaveURL(/\/data$/);
  });
});

test.describe('Honesty labels', () => {
  test('markets: derived label + info sheet + footnote', async ({ page }) => {
    await login(page);
    await page.goto('/markets');
    await expect(page.getByTestId('derived-legend')).toBeVisible(T);
    await page.getByTestId('derived-legend').getByRole('button').click();
    await expect(page.getByRole('dialog').getByText(/percentile rank/)).toBeVisible();
  });

  test('pricing: baseline provenance, soft fill and demand signal', async ({ page }) => {
    await login(page);
    await page.goto('/pricing');
    await page.getByTestId('act-picker').click();
    await page.getByRole('dialog').locator('button').filter({ hasText: /Arijit|India|·/ }).nth(1).click();
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('model-note')).toContainText(/Baseline estimate|Trained on real sales|Rule-based/, T);
    await expect(page.getByTestId('demand-level')).toContainText(/High|Medium|Low/, T);
  });
});
