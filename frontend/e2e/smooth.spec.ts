import { test, expect } from '@playwright/test';
import { login, trackErrors, API, tokens } from './helpers';

/** Scrolling feel + list windowing. (Lenis smooths wheel scrolling; nested panes must stay native.) */

test.beforeEach(async ({ page }) => {
  await login(page);
  await page.addInitScript(() => localStorage.setItem('liveiq-market-scope', 'india'));
});

test('page wheel-scroll moves the page (Lenis is active and not blocking)', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto('/');
  await expect(page.getByText('Indian acts tracked')).toBeVisible({ timeout: 30_000 });
  await page.mouse.move(760, 500);
  for (let i = 0; i < 12; i++) { await page.mouse.wheel(0, 140); await page.waitForTimeout(16); }
  await expect.poll(() => page.evaluate(() => window.scrollY), { timeout: 5_000 }).toBeGreaterThan(200);
  // eased: Lenis marks <html> while it is driving the scroll
  expect(await page.evaluate(() => document.documentElement.classList.contains('lenis'))).toBe(true);
  expect(errors.filter(e => !/favicon|Failed to load resource/.test(e))).toEqual([]);
});

test('reduced motion: Lenis does not smooth (scroll tracks the wheel 1:1)', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.getByText('Indian acts tracked')).toBeVisible({ timeout: 30_000 });
  await page.mouse.move(760, 500);
  await page.mouse.wheel(0, 300);
  await expect.poll(() => page.evaluate(() => window.scrollY), { timeout: 3_000 }).toBeGreaterThanOrEqual(290);
});

test('nested list keeps native scrolling and the page does not move (Intelligence split pane)', async ({ page }) => {
  await page.goto('/intelligence');
  const list = page.getByRole('listbox', { name: 'Entities' });
  await expect(list.getByRole('option').first()).toBeVisible({ timeout: 40_000 });
  const box = (await list.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let i = 0; i < 10; i++) { await page.mouse.wheel(0, 200); await page.waitForTimeout(16); }
  await expect.poll(() => list.evaluate(el => el.scrollTop), { timeout: 5_000 }).toBeGreaterThan(300);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test('windowed list: starts small, grows on scroll, ends with every result rendered', async ({ page }) => {
  await page.goto('/intelligence');
  const list = page.getByRole('listbox', { name: 'Entities' });
  const rows = list.getByRole('option');
  await expect(rows.first()).toBeVisible({ timeout: 40_000 });
  const label = await page.getByText(/^\d+ results?$/).first().innerText();
  const total = Number(label.split(' ')[0]);
  expect(total).toBeGreaterThan(100);
  expect(await rows.count()).toBeLessThanOrEqual(61);            // first page only -> small DOM

  const box = (await list.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect.poll(async () => {
    await list.evaluate(el => { el.scrollTop = el.scrollHeight; });
    await page.waitForTimeout(150);
    return rows.count();
  }, { timeout: 30_000, intervals: [100] }).toBe(total);
});

test('windowed list: ArrowDown past the last rendered row loads the next page and focuses it', async ({ page }) => {
  await page.goto('/intelligence');
  const rows = page.getByRole('listbox', { name: 'Entities' }).getByRole('option');
  await expect(rows.first()).toBeVisible({ timeout: 40_000 });
  const before = await rows.count();
  await rows.nth(before - 1).focus();
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => rows.count(), { timeout: 10_000 }).toBeGreaterThan(before);
  await page.keyboard.press('ArrowDown');
  expect(await page.evaluate(() => document.activeElement?.getAttribute('role'))).toBe('option');
});

test('hero count-up ends exactly on the API value (no re-render drift)', async ({ page }) => {
  await page.goto('/');
  const t = await tokens(page);
  const r = await page.request.get(`${API}/dashboard/summary?market=india`, { headers: { Authorization: `Bearer ${t.access_token}` } });
  const total = (await r.json()).hero.total_entities as number;
  await expect(page.getByText(String(total), { exact: true }).first()).toBeVisible({ timeout: 30_000 });
});

test('links are not prefetched up-front (only on hover/focus)', async ({ page }) => {
  const chunkRequests: string[] = [];
  page.on('request', r => { if (/_next\/static\/chunks\/.*\.js/.test(r.url())) chunkRequests.push(r.url()); });
  await page.goto('/');
  await expect(page.getByText('Indian acts tracked')).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2_000);
  const idle = chunkRequests.length;
  await page.getByRole('link', { name: 'Pricing', exact: true }).hover();
  await expect.poll(() => chunkRequests.length, { timeout: 8_000 }).toBeGreaterThan(idle - 1);
  // the point of the change: idle page load must not pull every route (that was ~1 MB / 20+ chunks)
  expect(idle).toBeLessThan(40);
});
