import { test, expect } from '@playwright/test';
import { login, trackErrors } from './helpers';
import { forecastFixture, sseBody } from './intel-fixtures';

test.describe('forecast', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  test('empty prompt, then insufficient-history state from real API', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/intelligence/forecast');
    await expect(page.getByText('Pick an artist to forecast')).toBeVisible({ timeout: 20000 });
    await page.getByRole('button', { name: 'Quick picks' }).first().isVisible().catch(() => {});
    await page.locator('[aria-label="Quick picks"] .chip').first().click({ timeout: 20000 });
    await expect(page.getByText(/Not enough history|Trend/).first()).toBeVisible({ timeout: 30000 });
    expect(errors).toEqual([]);
  });

  test('renders chart with confidence band (mocked ok forecast)', async ({ page }) => {
    const errors = trackErrors(page);
    await page.route('**/intelligence/*/forecast*', r => r.fulfill({ json: forecastFixture() }));
    await page.goto('/intelligence/forecast');
    await page.locator('[aria-label="Quick picks"] .chip').first().click({ timeout: 20000 });
    await expect(page.locator('.recharts-area').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('rising').first()).toBeVisible();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/forecast-ok.png` : undefined });
    expect(errors).toEqual([]);
  });

  test('service error shows retry, not a crash', async ({ page }) => {
    await page.route('**/intelligence/*/forecast*', r => r.fulfill({ status: 503, json: { detail: 'x' } }));
    await page.goto('/intelligence/forecast');
    await page.locator('[aria-label="Quick picks"] .chip').first().click({ timeout: 20000 });
    await expect(page.locator('[role=alert]:not(#__next-route-announcer__)')).toContainText('Prophet', { timeout: 15000 });
    await expect(page.getByRole('button', { name: /Try again/ })).toBeVisible();
  });
});

test.describe('copilot', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  test('streams a response with markdown (mocked SSE)', async ({ page }) => {
    const errors = trackErrors(page);
    await page.route('**/copilot/stream', r => r.fulfill({ contentType: 'text/event-stream', body: sseBody(['**Nagpur** looks strong.\n\n', '- Tier-2, ', '- ₹1,800 avg ticket']) }));
    await page.goto('/copilot');
    await expect(page.getByText('Ask about the Indian live-events market')).toBeVisible({ timeout: 20000 });
    await page.getByRole('button', { name: /Tier-2 city should District/ }).click();
    await expect(page.locator('strong', { hasText: 'Nagpur' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('₹1,800 avg ticket')).toBeVisible();
    await page.waitForTimeout(600);
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/copilot-chat.png` : undefined });
    expect(errors).toEqual([]);
  });

  test('real backend: streams a real answer end-to-end (no mocks)', async ({ page }) => {
    test.setTimeout(90_000);
    const errors = trackErrors(page);
    await page.goto('/copilot');
    await page.getByLabel('Message').fill('In two short sentences: which Tier-2 Indian city suits a comedy night?');
    await page.getByLabel('Send').click();
    // typing indicator or first tokens appear, then the stop button flips back to send
    await expect(page.getByLabel(/Stop generating/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByLabel('Send')).toBeVisible({ timeout: 60000 });
    const reply = page.locator('[data-role=assistant]').last();
    await expect(reply).not.toBeEmpty();
    expect((await reply.innerText()).length).toBeGreaterThan(20);
    await expect(page.locator('[role=alert]:not(#__next-route-announcer__)')).toHaveCount(0);
    await page.waitForTimeout(500);
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/copilot-real.png` : undefined });
    expect(errors).toEqual([]);
  });

  test('error recovery: retry button after failure', async ({ page }) => {
    await page.route('**/copilot/stream', r => r.fulfill({ status: 500, body: 'x' }));
    await page.route('**/copilot/chat', r => r.fulfill({ status: 502, json: { detail: 'bad' } }));
    await page.goto('/copilot');
    await page.getByLabel('Message').fill('hello');
    await page.keyboard.press('Enter');
    await expect(page.locator('[role=alert]:not(#__next-route-announcer__)')).toContainText(/not responding/i, { timeout: 10000 });
    await expect(page.getByRole('button', { name: /Try again/ })).toBeVisible();
  });
});
