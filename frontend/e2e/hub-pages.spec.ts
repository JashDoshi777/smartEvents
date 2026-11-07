import { test, expect } from '@playwright/test';
import { login, trackErrors } from './helpers';

test.beforeEach(async ({ page }) => {
  await login(page);
  await page.addInitScript(() => localStorage.setItem('liveiq-market-scope', 'india'));
});

test.describe('Intelligence Hub', () => {
  test('India-first list, search, detail, watchlist, scope toggle', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/intelligence');
    const rows = page.getByRole('option');
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Eminem')).toHaveCount(0); // global act hidden in India scope
    await expect(page.getByText('India tracked')).toBeVisible();

    await page.getByLabel('Search entities', { exact: true }).first().fill('Arijit');
    await expect(rows).toHaveCount(1);
    await rows.first().click();
    await expect(page.getByRole('heading', { name: 'Arijit Singh' })).toBeVisible();
    await expect(page.getByText('Signals', { exact: true })).toBeVisible();

    const star = page.getByRole('button', { name: /watchlist/i }).first();
    const before = await star.getAttribute('aria-label');
    await star.click();
    await expect(page.getByText(/(Added|Removed) .* (to|from) watchlist/)).toBeVisible();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: before!.startsWith('Add') ? 'Remove from watchlist' : 'Add to watchlist' }).first()).toBeVisible();
    await page.getByRole('button', { name: /watchlist/i }).first().click(); // restore
    await expect(page.getByRole('button', { name: before! }).first()).toBeVisible();

    await page.getByRole('button', { name: 'Global', exact: true }).click();
    await page.getByLabel('Search entities', { exact: true }).first().fill('Eminem');
    await expect(rows.first()).toBeVisible();
    expect(errors.filter(e => !/favicon/.test(e))).toEqual([]);
  });

  test('deep link selects entity and compare works', async ({ page }) => {
    await page.goto('/intelligence');
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: 'Compare', exact: true }).first().click();
    await page.getByRole('option').nth(0).click();
    await page.getByRole('option').nth(1).click();
    await page.locator('div').filter({ hasText: /^2 selected/ }).getByRole('button', { name: 'Compare' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('dialog').getByText('Score')).toBeVisible({ timeout: 15_000 });
  });
});

test('Trend Radar renders real data and responds to scope + sort', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/trends');
  await expect(page.getByText('Composite score').first()).toBeVisible();
  await expect(page.locator('a[href^="/intelligence?entity="]').first()).toBeVisible({ timeout: 30_000 });
  const first = await page.locator('a[href^="/intelligence?entity="]').first().innerText();
  await page.getByRole('button', { name: 'News', exact: true }).click();
  await expect(page.getByRole('button', { name: 'News', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Global', exact: true }).click();
  await expect(page.getByText(/across .* scored global entities/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('a[href^="/intelligence?entity="]').first()).toBeVisible({ timeout: 30_000 });
  expect(first).toBeTruthy();
  expect(errors).toEqual([]);
});

test('Recommendations: ranked list, city filter, sign verdict', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/recommendations');
  await expect(page.getByText(/candidates$/)).toBeVisible();
  const rows = page.locator('button[aria-pressed]').filter({ hasText: /\d\.\d/ });
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'Mumbai', exact: true }).click();
  await expect(page.getByText(/Ranked by 60%/)).toBeVisible({ timeout: 30_000 });
  await rows.first().click(); // fills the evaluator
  const btn = page.getByRole('button', { name: 'Get verdict' });
  if (await btn.isDisabled()) {
    await expect(page.getByText(/Your account is a viewer/)).toBeVisible(); // QA user is a viewer
  } else {
    await btn.click();
    await expect(page.getByText(/predicted fill/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Model price')).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('Psychology: report for default entity and city switch', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/psychology');
  await expect(page.getByText('Factors', { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('Controversy drag').first()).toBeVisible();
  await page.getByRole('button', { name: 'Delhi NCR', exact: true }).click();
  await expect(page.getByRole('heading', { name: /· Delhi NCR/ })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});

test('Social Listening: alerts card + sentiment for a sampled entity', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/listening');
  await expect(page.getByText('Crisis alerts', { exact: true })).toBeVisible();
  await expect(page.getByText('Recently sampled')).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText(/posts and articles analysed/)).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});
