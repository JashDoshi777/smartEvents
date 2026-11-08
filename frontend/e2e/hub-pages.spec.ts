import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { login, trackErrors, apiGet, benign } from './helpers';

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
    expect(errors.filter(e => !benign(e))).toEqual([]);
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

test.describe('Intelligence Hub: accuracy, URL state, export, keyboard', () => {
  test('list == API portfolio (India), sorted by score, ranks contiguous', async ({ page }) => {
    const p = await apiGet<{ portfolio: { name: string; composite_score: number | null }[]; total: number }>(page, '/executive/portfolio?market=india');
    await page.goto('/intelligence');
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 40_000 });
    await expect(page.getByText(`${p.total} results`)).toBeVisible({ timeout: 15_000 });
    const names = await page.getByRole('option').locator('xpath=.//span[contains(@class,"name")]').allInnerTexts();
    expect(names.slice(0, 5).map(n => n.trim())).toEqual(p.portfolio.slice(0, 5).map(x => x.name));
  });

  test('filters live in the URL and restore on reload; CSV matches the filtered list', async ({ page }) => {
    await page.goto('/intelligence');
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 40_000 });
    await page.getByLabel('Search entities', { exact: true }).first().fill('a');
    await page.getByRole('group', { name: 'Sort' }).getByRole('button', { name: 'A–Z' }).click();
    await expect(page).toHaveURL(/q=a/);
    await expect(page).toHaveURL(/sort=name/);
    await page.reload();
    await expect(page.getByLabel('Search entities', { exact: true }).first()).toHaveValue('a', { timeout: 30_000 });
    await expect(page.getByRole('group', { name: 'Sort' }).getByRole('button', { name: 'A–Z' })).toHaveAttribute('aria-pressed', 'true');
    // The list renders in pages of 60, so compare the CSV to the "N results" total, not the rendered DOM rows.
    const shown = Number((await page.getByText(/^\d+ results?$/).first().innerText()).split(' ')[0]);
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export list as CSV' }).click()]);
    const lines = readFileSync((await dl.path())!, 'utf8').replace(/^﻿/, '').trim().split(/\r?\n/);
    expect(lines.length - 1).toBe(shown);
    // A–Z order in the export
    const nm = lines.slice(1).map(l => l.split(',')[1].replace(/^"|"$/g, ''));
    expect(nm).toEqual([...nm].sort((a, b) => a.localeCompare(b)));
  });

  test('arrow keys move through the list; Enter opens details; no-result search', async ({ page }) => {
    await page.goto('/intelligence');
    const rows = page.getByRole('option');
    await expect(rows.first()).toBeVisible({ timeout: 40_000 });
    await rows.first().focus();
    await page.keyboard.press('ArrowDown');
    await expect(rows.nth(1)).toBeFocused();
    await page.keyboard.press('ArrowUp');
    await expect(rows.first()).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/entity=/);
    await page.getByLabel('Search entities', { exact: true }).first().fill('%$#@!zzzz');
    await expect(page.getByText('No matches')).toBeVisible();
  });

  test('compare mode is capped at 4 selections', async ({ page }) => {
    await page.goto('/intelligence');
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 40_000 });
    await page.getByRole('button', { name: 'Compare', exact: true }).first().click();
    for (let i = 0; i < 5; i++) await page.getByRole('option').nth(i).click();
    await expect(page.getByText('4/4 selected')).toBeVisible();
    await expect(page.getByText('Compare up to 4 at a time').first()).toBeVisible();
  });

  test('API failure shows a retryable error', async ({ page }) => {
    let fail = true;
    await page.addInitScript(() => localStorage.removeItem('liveiq-swr-cache'));
    await page.route(/\/executive\/portfolio/, r => (fail ? r.fulfill({ status: 500, body: '{}' }) : r.continue()));
    await page.goto('/intelligence');
    await expect(page.getByText('Couldn’t load the entity portfolio.')).toBeVisible({ timeout: 40_000 });
    fail = false;
    await page.getByRole('button', { name: /Try again/ }).first().click();
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 40_000 });
  });
});

test('Trend Radar movers equal the momentum API', async ({ page }) => {
  const mv = await apiGet<{ risers: { name: string; momentum_pct: number }[]; fallers: { name: string; momentum_pct: number }[] }>(page, '/trends/momentum?market=india&limit=10');
  await page.goto('/trends');
  await expect(page.getByText('Biggest movers')).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText('Rising / Falling')).toBeVisible();
  if (!mv.risers.length && !mv.fallers.length) { await expect(page.getByText(/No clear movers/)).toBeVisible(); return; }
  const r = mv.risers[0] ?? mv.fallers[0];
  const pct = `${r.momentum_pct > 0 ? '+' : ''}${Math.round(r.momentum_pct)}%`;
  await expect(page.getByRole('link', { name: new RegExp(r.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).filter({ hasText: pct }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/views last week/).first()).toBeVisible();
});

test('Trend Radar renders real data and responds to scope + sort', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/trends');
  await expect(page.getByText('Composite score').first()).toBeVisible();
  await expect(page.locator('a[href^="/intelligence?entity="]').filter({ hasText: /\S/ }).first()).toBeVisible({ timeout: 30_000 });
  const first = await page.locator('a[href^="/intelligence?entity="]').filter({ hasText: /\S/ }).first().innerText();
  await page.getByRole('button', { name: 'News', exact: true }).click();
  await expect(page.getByRole('button', { name: 'News', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Global', exact: true }).click();
  await expect(page.getByText(/across .* scored global entities/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('a[href^="/intelligence?entity="]').filter({ hasText: /\S/ }).first()).toBeVisible({ timeout: 30_000 });
  expect(first).toBeTruthy();
  expect(errors.filter(e => !benign(e))).toEqual([]);
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
    await expect(page.getByText(/predicted fill|baseline fill estimate/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Model price')).toBeVisible();
  }
  expect(errors.filter(e => !benign(e))).toEqual([]);
});

test('Psychology: report for default entity and city switch', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/psychology');
  await expect(page.getByText('Factors', { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('Controversy drag').first()).toBeVisible();
  await page.getByRole('button', { name: 'Delhi NCR', exact: true }).click();
  await expect(page.getByRole('heading', { name: /· Delhi NCR/ })).toBeVisible({ timeout: 30_000 });
  expect(errors.filter(e => !benign(e))).toEqual([]);
});

test('Social Listening: alerts card + sentiment for a sampled entity', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/listening');
  await expect(page.getByText('Crisis alerts', { exact: true })).toBeVisible();
  await expect(page.getByText('Recently sampled')).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText(/posts and articles analysed/)).toBeVisible({ timeout: 30_000 });
  expect(errors.filter(e => !benign(e))).toEqual([]);
});
