import { test, expect } from '@playwright/test';
import { login, trackErrors } from './helpers';
import { dealFixture } from './intel-fixtures';

test.describe('events pages', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  test('fill-rate monitor renders real events without errors', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/events');
    await expect(page.getByText('Events on record')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText('Events tracked')).toBeVisible();
    await expect(page.getByText(/^₹[\d,]+$/).first()).toBeVisible();
    await expect(page.getByText('City demand')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });

  test('deal modeler: viewer gets a friendly role message, no crash', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/events/model');
    await expect(page.getByText('Booking roles only')).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeDisabled();
    expect(errors.filter(e => !e.includes('403'))).toEqual([]);
  });

  test('deal modeler: submit renders P&L in lakh/crore (mocked success)', async ({ page }) => {
    const errors = trackErrors(page);
    await page.route('**/auth/me', r => r.fulfill({ json: { id: 'u', email: 'a@b.c', full_name: 'Booker', role: 'booker', is_verified: true } }));
    await page.route('http://localhost:8000/events/model', r => r.fulfill({ json: dealFixture }));
    await page.goto('/events/model');
    await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled({ timeout: 20000 });
    await page.locator('#m-artist').click();
    await page.getByRole('option').first().click();
    await page.selectOption('#m-city', { index: 1 });
    await page.fill('#m-cap', '9000');
    await page.fill('#m-price', '2500');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(page.getByText('expected net profit')).toBeVisible();
    await expect(page.getByText('₹1.8 Cr').first()).toBeVisible();
    await expect(page.getByText('Medium risk')).toBeVisible();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/model-result.png` : undefined });
    expect(errors).toEqual([]);
  });

  test('deal modeler: validation message on empty submit', async ({ page }) => {
    await page.route('**/auth/me', r => r.fulfill({ json: { id: 'u', email: 'a@b.c', full_name: 'B', role: 'analyst', is_verified: true } }));
    await page.goto('/events/model');
    await page.getByRole('button', { name: 'Run simulation' }).click();
    await expect(page.locator('[role=alert]:not(#__next-route-announcer__)')).toContainText('Choose an artist');
  });

  test('pairing returns real recommendations or a clean message', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/events/pairing');
    await expect(page.getByText(/Best pairing for Mumbai|Not enough|unavailable/)).toBeVisible({ timeout: 40000 });
    await expect(page.locator('text=&').first()).toBeVisible();
    await page.getByRole('button', { name: 'All', exact: true }).click();
    await page.getByRole('button', { name: 'Find pairings' }).click();
    await expect(page.getByText(/Best pairing for Mumbai/)).toBeVisible({ timeout: 40000 });
    expect(errors).toEqual([]);
  });
});
