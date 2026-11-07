import { test, expect, Page } from '@playwright/test';
import { login } from './helpers';

test.describe.configure({ retries: 1 });

async function pickFirstAct(page: Page) {
  await page.getByTestId('act-picker').click();
  const first = page.locator('button[class*="__pick"]').first();
  await first.waitFor({ timeout: 25_000 });
  await first.click();
}

const OK = {
  entity: { id: 'x', name: 'Test Act', type: 'artist', category: 'Music', is_international: false },
  recommendation: { proposed_price: 3000, recommended_price: 4200, price_tier: 'Premium', confidence: 'High (ML GBR · 84%)', reasoning: 'Strong signal.', predicted_fill_rate: 76.4,
    sensitivity_curve: [1500, 3000, 6000].map((p, i) => ({ price: p, attendance_pct: [95, 80, 45][i] })) },
  signals: { composite_score: 78, google_trend_score: 64, demand_score: 71, city_multiplier: 1.2, capacity_factor: 0.92, season_factor: 1.12, international_factor: 1 },
  benchmarks: { category: 'music', floor: 500, sweet_spot: 2500, premium: 8000, ultra_premium: 25000 }, model: 'ml_gbr',
};

test.describe('Pricing optimizer', () => {
  test('shows benchmarks in rupees and validates before submit', async ({ page }) => {
    await login(page);
    await page.goto('/pricing');
    await expect(page.getByText('price ladder')).toBeVisible({ timeout: 25_000 });
    await expect(page.getByText(/Floor ₹/)).toBeVisible();
    await page.getByTestId('optimize').click();
    await expect(page.getByText('Choose an act to price.')).toBeVisible();
    await pickFirstAct(page);
    await page.getByLabel('Proposed ticket price').fill('50');
    await page.getByTestId('optimize').click();
    await expect(page.getByRole('alert').filter({ hasText: /Price must be between ₹100 and ₹50,000/ })).toBeVisible();
  });

  test('viewer role gets a friendly 403 message (real API)', async ({ page }) => {
    await login(page);
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByTestId('optimize').click();
    const notice = page.getByTestId('role-notice');
    await expect(notice).toBeVisible({ timeout: 25_000 });
    await expect(notice).toContainText('Analyst');
    await expect(page.getByTestId('city-bars')).toBeVisible({ timeout: 25_000 });
  });

  test('success result renders rupee price, fill ring and chart (mocked)', async ({ page }) => {
    await login(page);
    await page.route('**/pricing/optimize', r => r.fulfill({ json: OK }));
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('rec-price')).toHaveText('₹4,200');
    await expect(page.getByText('76%')).toBeVisible();
    await expect(page.getByText('Price elasticity')).toBeVisible();
  });

  test('422 from backend shows readable message (mocked)', async ({ page }) => {
    await login(page);
    await page.route('**/pricing/optimize', r => r.fulfill({ status: 422, json: { detail: [{ loc: ['body', 'venue_capacity'], msg: 'Input should be >= 100' }] } }));
    await page.goto('/pricing');
    await pickFirstAct(page);
    await page.getByTestId('optimize').click();
    await expect(page.getByTestId('error-notice')).toContainText('venue_capacity: Input should be >= 100');
  });
});
