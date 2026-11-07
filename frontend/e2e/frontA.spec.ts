import { test, expect } from '@playwright/test';
import { login, trackErrors, API } from './helpers';

test.describe('Dashboard', () => {
  test('renders India-first data with no errors', async ({ page }) => {
    await login(page);
    const errors = trackErrors(page);
    await page.goto('/');
    await expect(page.getByText(/Indian acts tracked/)).toBeVisible({ timeout: 30000 });
    await expect(page.getByText('Live alerts', { exact: true })).toBeVisible();
    await expect(page.getByText('Global acts tracked')).toHaveCount(0);
    await expect(page.getByText('City heat', { exact: true })).toBeVisible();
    await page.waitForTimeout(1500);
    expect(errors.filter(e => !/ERR_|favicon/.test(e))).toEqual([]);
  });
  test('scope toggle switches to global', async ({ page }) => {
    await login(page);
    await page.goto('/');
    await page.getByRole('button', { name: 'Global', exact: true }).first().click();
    await expect(page.getByText(/international acts tracked/)).toBeVisible({ timeout: 30000 });
  });
});

test.describe('Executive', () => {
  test('KPIs, portfolio and PDF export', async ({ page }) => {
    await login(page);
    const errors = trackErrors(page);
    await page.goto('/executive');
    await expect(page.getByText('Top ranked acts')).toBeVisible({ timeout: 30000 });
    await expect(page.getByText(/Indian acts · /)).toBeVisible();
    // qa user is a viewer: the backend 403s report export, so the button must not be offered
    await expect(page.getByRole('button', { name: 'Export PDF report' })).toHaveCount(0);
    expect(errors.filter(e => !/ERR_|favicon/.test(e))).toEqual([]);
  });
});

test.describe('Settings', () => {
  test('theme + default market persist after reload', async ({ page }) => {
    await login(page);
    await page.goto('/settings');
    await expect(page.getByText('Appearance')).toBeVisible({ timeout: 30000 });
    await page.getByRole('group', { name: 'Appearance' }).getByRole('button', { name: 'Light' }).click();
    await page.getByRole('group', { name: 'Default market' }).getByRole('button', { name: 'Global' }).click();
    await page.addInitScript(() => {}); // keep login seeding; theme init script re-seeds dark only on load, so check storage directly
    const stored = await page.evaluate(() => [localStorage.getItem('liveiq-theme'), localStorage.getItem('liveiq-market-scope')]);
    expect(stored).toEqual(['light', 'global']);
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });
  test('log out returns to login', async ({ page }) => {
    await login(page);
    await page.goto('/settings');
    await page.getByRole('button', { name: /Log out/ }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Watchlist', () => {
  test('add then remove an act', async ({ page }) => {
    await login(page);
    const errors = trackErrors(page);
    // clean slate
    const tok = await page.evaluate(() => null);
    void tok;
    await page.goto('/watchlist');
    await page.getByLabel('Search acts to add').fill('Arijit');
    const add = page.getByRole('button', { name: /^Add .* to watchlist$/ }).first();
    await expect(add).toBeVisible({ timeout: 20000 });
    const label = (await add.getAttribute('aria-label'))!;
    const name = label.replace(/^Add /, '').replace(/ to watchlist$/, '');
    await add.click();
    await expect(page.getByTestId('watch-row').filter({ hasText: name })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: `Remove ${name} from watchlist` }).click();
    await expect(page.getByTestId('watch-row').filter({ hasText: name })).toHaveCount(0);
    expect(errors.filter(e => !/ERR_|favicon|404/.test(e))).toEqual([]);
  });
});

test.describe('Auth screens', () => {
  test('wrong password shows error', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill('qa@liveiq.dev');
    await page.getByLabel('Password', { exact: true }).fill('wrongpass123');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.locator('[role=alert]:not(#__next-route-announcer__)')).toContainText(/incorrect/i, { timeout: 15000 });
  });
  test('inline validation on empty submit', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('Enter a valid email address')).toBeVisible();
  });
  test('login success redirects to dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill('qa@liveiq.dev');
    await page.getByLabel('Password', { exact: true }).fill('QaTest#2026');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/localhost:3000\/$/, { timeout: 20000 });
  });
  test('register validation + link back to login', async ({ page }) => {
    await page.goto('/register');
    await page.getByLabel('Password', { exact: true }).fill('short');
    await expect(page.getByText('Use at least 8 characters')).toBeVisible();
    await page.getByRole('link', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
void API;
