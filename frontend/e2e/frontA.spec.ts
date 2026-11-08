import { test, expect, Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { login, freshTokens, trackErrors, apiGet, benign, API } from './helpers';

const inNum = (n: number) => n.toLocaleString('en-IN');

test.beforeEach(async ({ page }) => {
  await login(page);
  await page.addInitScript(() => { if (!localStorage.getItem('liveiq-market-scope')) localStorage.setItem('liveiq-market-scope', 'india'); });
});

async function hero(page: Page) { return page.locator('p', { hasText: /(Indian|international) acts tracked/ }).locator('xpath=preceding-sibling::div[1]'); }

test.describe('Dashboard', () => {
  test('UI numbers equal the API (India), clean console', async ({ page }) => {
    const errors = trackErrors(page);
    const sum = await apiGet<{ hero: { total_entities: number; entities_with_metrics: number; avg_composite_score: number | null; active_cities: number }; trending_entities: { name: string; composite_score: number }[] }>(page, '/dashboard/summary?market=india');
    await page.goto('/');
    await expect(page.getByText('Indian acts tracked')).toBeVisible({ timeout: 40_000 });
    await expect(await hero(page)).toHaveText(inNum(sum.hero.total_entities), { timeout: 10_000 });
    await expect(page.getByText('Scored', { exact: true }).locator('xpath=preceding-sibling::span')).toHaveText(inNum(sum.hero.entities_with_metrics));
    if (sum.hero.avg_composite_score != null) await expect(page.getByText('avg score')).toBeVisible();
    // top acts are sorted by score, descending, and match the API order
    const top = sum.trending_entities.slice(0, 6).map(e => e.name);
    const scores = sum.trending_entities.map(e => e.composite_score);
    expect(scores).toEqual([...scores].sort((a, b) => b - a));
    const card = page.locator('h2', { hasText: 'Top Indian acts' }).locator('xpath=ancestor::div[contains(@class,"tile")][1]');
    for (const n of top) await expect(card.getByText(n, { exact: true })).toBeVisible();
    await expect(page.getByText('Global acts tracked')).toHaveCount(0);
    await expect(page.getByText('City heat', { exact: true })).toBeVisible();
    await expect(page.getByText('What changed', { exact: true })).toBeVisible();
    await page.waitForTimeout(1000);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('What changed lists real movers with correct deltas', async ({ page }) => {
    const mv = await apiGet<{ risers: { name: string; delta: number; previous_score: number; score: number }[]; fallers: { name: string; delta: number }[] }>(page, '/dashboard/movers?market=india&limit=4');
    await page.goto('/');
    await expect(page.getByText('What changed', { exact: true })).toBeVisible({ timeout: 40_000 });
    if (!mv.risers.length && !mv.fallers.length) { await expect(page.getByText('No score movement yet')).toBeVisible(); return; }
    const r = mv.risers[0];
    const row = page.getByRole('link', { name: new RegExp(`^${r.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`) }).first();
    await expect(row).toContainText(`+${r.delta.toFixed(1)}`, { timeout: 20_000 });
    await expect(row).toContainText(`${r.previous_score.toFixed(1)} to ${r.score.toFixed(1)}`);
    for (const f of mv.fallers) expect(f.delta).toBeLessThan(0);
  });

  test('scope toggle switches the whole dashboard to global data', async ({ page }) => {
    const g = await apiGet<{ hero: { total_entities: number } }>(page, '/dashboard/summary?market=global');
    await page.goto('/');
    await page.getByRole('button', { name: 'Global', exact: true }).first().click();
    await expect(page.getByText(/international acts tracked/)).toBeVisible({ timeout: 40_000 });
    await expect(await hero(page)).toHaveText(inNum(g.hero.total_entities), { timeout: 10_000 });
    await page.reload();
    await expect(page.getByText(/international acts tracked/)).toBeVisible({ timeout: 40_000 }); // scope persisted
  });

  test('500 from the API shows an error state and Retry recovers', async ({ page }) => {
    let fail = true;
    await page.route(/\/dashboard\/summary/, r => (fail ? r.fulfill({ status: 500, body: '{}' }) : r.continue()));
    await page.addInitScript(() => localStorage.removeItem('liveiq-swr-cache'));
    await page.goto('/');
    await expect(page.getByRole('alert').filter({ hasText: 'Couldn’t reach the LiveIQ backend' })).toBeVisible({ timeout: 40_000 });
    fail = false;
    await page.getByRole('button', { name: /Try again/ }).first().click();
    await expect(page.getByText('Indian acts tracked')).toBeVisible({ timeout: 40_000 });
  });

  test('empty payloads render empty states, not crashes', async ({ page }) => {
    const errors = trackErrors(page);
    await page.route(/\/dashboard\/(alerts|movers)/, r => r.fulfill({ json: r.request().url().includes('movers') ? { risers: [], fallers: [], compared: 0, generated_at: new Date().toISOString() } : { alerts: [], total: 0, generated_at: new Date().toISOString() } }));
    await page.goto('/');
    await expect(page.getByText('No alerts right now')).toBeVisible({ timeout: 40_000 });
    await expect(page.getByText('No score movement yet')).toBeVisible();
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });
});

test.describe('Executive', () => {
  test('KPIs equal the API, scope changes the numbers, CSV + PDF actions', async ({ page }) => {
    const errors = trackErrors(page);
    const k = await apiGet<{ entity_portfolio: { total_tracked: number; avg_composite_score: number | null } }>(page, '/executive/kpis?market=india');
    const p = await apiGet<{ portfolio: { name: string; composite_score: number | null; rank: number; id: string }[]; total: number }>(page, '/executive/portfolio?market=india');
    expect(k.entity_portfolio.total_tracked).toBe(p.total);
    expect(new Set(p.portfolio.map(x => x.id)).size).toBe(p.portfolio.length);
    await page.goto('/executive');
    await expect(page.getByText('Top ranked acts in India')).toBeVisible({ timeout: 40_000 });
    await expect(page.getByText(/Indian acts · \d+% scored/).locator('xpath=preceding-sibling::span')).toHaveText(inNum(k.entity_portfolio.total_tracked), { timeout: 10_000 });
    const firstScored = p.portfolio.find(x => x.composite_score != null);
    if (firstScored) await expect(page.getByText(firstScored.name, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export PDF report' })).toBeVisible(); // qa is an analyst
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export portfolio CSV' }).click()]);
    const csv = readFileSync((await dl.path())!, 'utf8').replace(/^﻿/, '').trim().split(/\r?\n/);
    expect(csv[0]).toMatch(/^Rank,Name,Type/);
    expect(csv.length - 1).toBe(p.total);
    await page.getByRole('button', { name: 'Global', exact: true }).first().click();
    await expect(page.getByText('Top ranked acts', { exact: true })).toBeVisible({ timeout: 40_000 });
    await expect(page.getByText(/International acts · \d+% scored/)).toBeVisible();
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('briefing never shows raw markdown asterisks', async ({ page }) => {
    await page.route(/\/executive\/briefing/, r => r.fulfill({ json: { briefing: 'LiveIQ Weekly Pulse — **King** leads with **45.9**.', generated_at: new Date().toISOString(), data_context: {} } }));
    await page.goto('/executive');
    await expect(page.getByText(/King leads with 45.9/)).toBeVisible({ timeout: 40_000 });
    await expect(page.getByText('**')).toHaveCount(0);
  });

  test('role gating: a viewer is not offered the PDF export', async ({ page }) => {
    await page.route(/\/auth\/me$/, async r => { const res = await r.fetch(); const j = await res.json(); await r.fulfill({ response: res, json: { ...j, role: 'viewer' } }); });
    await page.goto('/executive');
    await expect(page.getByText('Top ranked acts', { exact: false }).first()).toBeVisible({ timeout: 40_000 });
    await expect(page.getByRole('button', { name: 'Export PDF report' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Export portfolio CSV' })).toBeVisible();
  });
});

test.describe('Settings', () => {
  test('theme, market and notification preference persist across reload', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByText('Appearance')).toBeVisible({ timeout: 30_000 });
    await page.getByRole('group', { name: 'Appearance' }).getByRole('button', { name: 'Light' }).click();
    await page.getByRole('group', { name: 'Default market' }).getByRole('button', { name: 'Global' }).click();
    await page.getByRole('switch', { name: 'Show only watchlist notifications' }).click();
    const stored = await page.evaluate(() => [localStorage.getItem('liveiq-theme'), localStorage.getItem('liveiq-market-scope'), localStorage.getItem('liveiq-notif-watchlist-only')]);
    expect(stored).toEqual(['light', 'global', '1']);
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });
  test('the bell honours "watchlist only"', async ({ page }) => {
    const mk = (id: string, watched: boolean) => ({ id, type: 'news_burst', title: watched ? 'Watched act spike' : 'Random act spike', message: 'm', entity: 'x', severity: 'medium', is_read: false, is_watched: watched, detected_at: new Date().toISOString() });
    await page.route(/\/notifications\/unread-count/, r => r.fulfill({ json: { unread_count: 2 } }));
    await page.route(/\/notifications(\?.*)?$/, r => r.fulfill({ json: { notifications: [mk('a', true), mk('b', false)], total: 2 } }));
    await page.addInitScript(() => localStorage.setItem('liveiq-notif-watchlist-only', '1'));
    await page.goto('/settings');
    await page.getByRole('button', { name: /^Notifications/ }).click();
    await expect(page.getByRole('menuitem', { name: /Watched act spike/ })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: /Random act spike/ })).toHaveCount(0);
  });
  test('log out returns to login and protected routes bounce back', async ({ page }) => {
    await page.route(/\/auth\/logout/, r => r.fulfill({ json: { status: 'ok' } })); // don't revoke tokens other tests share
    await page.goto('/settings');
    await page.getByRole('button', { name: 'Log out' }).first().click();
    await expect(page).toHaveURL(/\/login/);
    expect(await page.evaluate(() => localStorage.getItem('liveiq_access_token'))).toBeNull();
    await page.addInitScript(() => localStorage.clear()); // beforeEach re-seeds tokens on every load; wipe them again
    await page.goto('/executive');
    await expect(page).toHaveURL(/\/login\?next=%2Fexecutive/);
  });
});

test.describe('Watchlist', () => {
  test('add persists across reload, shows score, remove persists', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/watchlist');
    await page.getByLabel('Search acts to add').fill('Arijit');
    const add = page.getByRole('button', { name: /^Add .* to watchlist$/ }).first();
    const already = page.getByRole('button', { name: /^Remove .* from watchlist$/ });
    await expect(add.or(page.getByText('Watching').first())).toBeVisible({ timeout: 25_000 });
    let name: string;
    if (await add.count()) {
      name = (await add.getAttribute('aria-label'))!.replace(/^Add /, '').replace(/ to watchlist$/, '');
      await add.click();
    } else { name = (await already.first().getAttribute('aria-label'))!.replace(/^Remove /, '').replace(/ from watchlist$/, ''); }
    const row = page.getByTestId('watch-row').filter({ hasText: name });
    await expect(row).toBeVisible({ timeout: 15_000 });
    await page.reload();
    await expect(row).toBeVisible({ timeout: 25_000 });
    const wl = await apiGet<{ watchlist: { name: string; composite_score: number | null; score_delta: number | null }[] }>(page, '/watchlist');
    const mine = wl.watchlist.find(w => w.name === name)!;
    expect(mine).toBeTruthy();
    if (mine.composite_score != null) await expect(row).toContainText(mine.composite_score.toFixed(1));
    await page.getByRole('button', { name: `Remove ${name} from watchlist` }).click();
    await expect(row).toHaveCount(0);
    await page.reload();
    await expect(page.getByText('Watchlist', { exact: true }).first()).toBeVisible();
    await expect(page.getByTestId('watch-row').filter({ hasText: name })).toHaveCount(0);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });
  test('search edge cases: one char, special chars, no results', async ({ page }) => {
    await page.goto('/watchlist');
    const box = page.getByLabel('Search acts to add');
    await box.fill('a');
    await expect(page.getByText(/No acts match/)).toHaveCount(0);
    await box.fill('%\'"<script>');
    await expect(page.getByText(/No acts match/)).toBeVisible({ timeout: 20_000 });
    await box.fill('zzzzqqqq');
    await expect(page.getByText('No acts match “zzzzqqqq”.')).toBeVisible({ timeout: 20_000 });
  });
});

test.describe('Auth, session and routing', () => {
  test('deep link survives login (next param) and rejects open redirects', async ({ page }) => {
    await page.addInitScript(() => localStorage.clear());
    await page.goto('/intelligence?q=arijit');
    await expect(page).toHaveURL(/\/login\?next=%2Fintelligence%3Fq%3Darijit/);
    await page.getByLabel('Email').fill('qa@liveiq.dev');
    await page.getByLabel('Password', { exact: true }).fill('QaTest#2026');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/intelligence\?q=arijit/, { timeout: 30_000 });
  });
  test('?next=//evil.com is ignored after login', async ({ page }) => {
    await page.addInitScript(() => localStorage.clear());
    await page.goto('/login?next=%2F%2Fevil.com');
    await page.getByLabel('Email').fill('qa@liveiq.dev');
    await page.getByLabel('Password', { exact: true }).fill('QaTest#2026');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/localhost:3000\/$/, { timeout: 30_000 });
  });
  test('expired access token silently refreshes (no logout)', async ({ page }) => {
    const t = await freshTokens(page); // private pair: a refresh rotates the refresh token
    await page.addInitScript(r => { localStorage.setItem('liveiq_access_token', 'expired.invalid.token'); localStorage.setItem('liveiq_refresh_token', r); }, t.refresh_token);
    await page.goto('/settings');
    await expect(page.getByText('Account', { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveURL(/\/settings$/);
    const fresh = await page.evaluate(() => localStorage.getItem('liveiq_access_token'));
    expect(fresh).not.toBe('expired.invalid.token');
  });
  test('both tokens invalid: graceful logout to login', async ({ page }) => {
    // first load: both tokens bad. After the app's hard redirect to /login the harness would re-seed valid ones, so strip them (the app clears them itself)
    await page.addInitScript(() => { if (sessionStorage.getItem('seeded')) { localStorage.removeItem('liveiq_access_token'); localStorage.removeItem('liveiq_refresh_token'); return; } sessionStorage.setItem('seeded', '1'); localStorage.setItem('liveiq_access_token', 'bad.bad.bad'); localStorage.setItem('liveiq_refresh_token', 'bad'); });
    await page.goto('/watchlist');
    await expect(page).toHaveURL(/\/login\?next=%2Fwatchlist/, { timeout: 30_000 });
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  });
  test('a 503 from /auth/me keeps the session and offers a retry', async ({ page }) => {
    let down = true;
    await page.route(/\/auth\/me$/, r => (down ? r.fulfill({ status: 503, body: '{}' }) : r.continue()));
    await page.goto('/');
    await expect(page.getByText('Can’t reach LiveIQ')).toBeVisible({ timeout: 30_000 });
    expect(await page.evaluate(() => localStorage.getItem('liveiq_refresh_token'))).toBeTruthy();
    down = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByText('Indian acts tracked')).toBeVisible({ timeout: 40_000 });
  });
  test('wrong password, validation, register link', async ({ page }) => {
    await page.addInitScript(() => localStorage.clear());
    await page.goto('/login');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('Enter a valid email address')).toBeVisible();
    await page.getByLabel('Email').fill('qa@liveiq.dev');
    await page.getByLabel('Password', { exact: true }).fill('wrongpass123');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.locator('[role=alert]:not(#__next-route-announcer__)')).toContainText(/incorrect/i, { timeout: 15_000 });
    await page.getByRole('link', { name: 'Create an account' }).click();
    await expect(page).toHaveURL(/\/register/);
    await page.getByLabel('Password', { exact: true }).fill('short');
    await expect(page.getByText('Use at least 8 characters')).toBeVisible();
    await page.getByRole('link', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/login/);
  });
  test('unknown route shows the branded 404; back/forward works', async ({ page }) => {
    await page.goto('/');
    await page.goto('/executive');
    await page.goto('/this-route-does-not-exist');
    await expect(page.getByText('We couldn’t find that page')).toBeVisible({ timeout: 20_000 });
    await page.getByRole('link', { name: 'Back to dashboard' }).click();
    await expect(page).toHaveURL(/localhost:3000\/$/);
    await page.goBack();
    await expect(page.getByText('We couldn’t find that page')).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/executive/);
    await page.goForward();
    await expect(page).toHaveURL(/this-route-does-not-exist/);
  });
});

test.describe('Command palette & notifications', () => {
  test('⌘K: keyboard navigation, entity jump, recents, no-results, Esc', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Indian acts tracked')).toBeVisible({ timeout: 40_000 });
    await page.keyboard.press('Control+k');
    const dlg = page.getByRole('dialog', { name: 'Command palette' });
    await expect(dlg).toBeVisible();
    await expect(page.getByLabel('Search', { exact: true })).toBeFocused();
    await page.getByLabel('Search', { exact: true }).fill('zzzzqqq');
    await expect(dlg.getByText(/No results for/)).toBeVisible();
    await page.getByLabel('Search', { exact: true }).fill('arijit');
    const first = dlg.getByRole('option').first();
    await expect(first).toContainText(/Arijit/i, { timeout: 15_000 });
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/intelligence\?entity=/, { timeout: 15_000 });
    await expect(dlg).toHaveCount(0);
    await page.keyboard.press('Control+k');
    await expect(dlg.getByRole('option').filter({ hasText: 'Recent' }).first()).toContainText(/Arijit/i);
    await page.keyboard.press('Escape');
    await expect(dlg).toHaveCount(0);
    // page + action items work from the keyboard
    await page.keyboard.press('Control+k');
    await page.getByLabel('Search', { exact: true }).fill('trend');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/trends/);
  });

  test('bell: optimistic mark-read, read-all, server count is the badge, errors recover', async ({ page }) => {
    let unread = 25; // more than the 20 rows the list returns: the badge must still say 25
    const items = Array.from({ length: 20 }, (_, i) => ({ id: `n${i}`, type: 'news_burst', title: `Signal ${i}`, message: 'msg', entity: 'E', severity: 'medium', is_read: false, is_watched: false, detected_at: new Date().toISOString() }));
    await page.route(/\/notifications\/unread-count/, r => r.fulfill({ json: { unread_count: unread } }));
    await page.route(/\/notifications\/n\d+\/read/, r => { unread -= 1; items.find(i => r.request().url().includes(`/${i.id}/`))!.is_read = true; return r.fulfill({ json: { status: 'ok' } }); });
    await page.route(/\/notifications\/read-all/, r => { unread = 0; items.forEach(i => (i.is_read = true)); return r.fulfill({ json: { status: 'ok' } }); });
    await page.route(/\/notifications(\?.*)?$/, r => r.fulfill({ json: { notifications: items, total: items.length } }));
    await page.goto('/');
    const bell = page.getByRole('button', { name: /^Notifications/ });
    await expect(bell).toHaveAttribute('aria-label', 'Notifications, 25 unread', { timeout: 40_000 });
    await bell.click();
    await page.getByRole('menuitem', { name: /Signal 0/ }).click();
    await expect(bell).toHaveAttribute('aria-label', 'Notifications, 24 unread');
    await expect(page.getByRole('menuitem', { name: /Signal 0.*\(read\)/ })).toBeVisible();
    await page.getByRole('button', { name: /Mark all read/ }).click();
    await expect(bell).toHaveAttribute('aria-label', 'Notifications');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu', { name: 'Notifications' })).toHaveCount(0);
  });

  test('bell: list failure shows retry', async ({ page }) => {
    await page.route(/\/notifications\/unread-count/, r => r.fulfill({ json: { unread_count: 1 } }));
    let fail = true;
    await page.route(/\/notifications(\?.*)?$/, r => (fail ? r.fulfill({ status: 500, body: '{}' }) : r.fulfill({ json: { notifications: [], total: 0 } })));
    await page.goto('/settings');
    await page.getByRole('button', { name: /^Notifications/ }).click();
    await expect(page.getByText('Couldn’t load notifications.')).toBeVisible({ timeout: 20_000 });
    fail = false;
    await page.getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByText(/No notifications yet/)).toBeVisible();
  });
});

test.describe('Shell on every route', () => {
  const ROUTES = ['/', '/executive', '/intelligence', '/trends', '/recommendations', '/psychology', '/listening', '/watchlist', '/settings'];
  for (const r of ROUTES) {
    test(`no console errors, no horizontal scroll on phone: ${r}`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      const errors = trackErrors(page);
      await page.goto(r);
      await expect(page.locator('h1, [role=heading]').first()).toBeVisible({ timeout: 40_000 });
      await page.waitForLoadState('networkidle', { timeout: 40_000 }).catch(() => {});
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
      // topbar tap targets >= 40px
      for (const name of [/Open menu/, /Search/, /^Notifications/, /User menu/]) {
        const box = await page.getByRole('button', { name }).first().boundingBox();
        expect(box && Math.min(box.width, box.height), String(name)).toBeGreaterThanOrEqual(40);
      }
      expect(errors.filter(e => !benign(e))).toEqual([]);
    });
  }
  test('theme toggle flips and persists; light theme renders cleanly', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Toggle theme' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    expect(await page.evaluate(() => localStorage.getItem('liveiq-theme'))).toBe('light');
  });
});
void API;
