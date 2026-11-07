import { test, expect } from '@playwright/test';
import { login, trackErrors } from './helpers';

test.describe.configure({ retries: 1 });

test.describe('City Markets', () => {
  test('lists 12 cities with scores and loads detail', async ({ page }) => {
    const errors = trackErrors(page);
    await login(page);
    await page.goto('/markets');
    await expect(page.locator('[data-testid^="city-"]')).toHaveCount(12, { timeout: 25_000 });
    await expect(page.getByTestId('city-Mumbai')).toContainText('90.0');
    await expect(page.getByTestId('detail-title')).toHaveText('Mumbai');
    await expect(page.getByText('Restaurant partnership engine')).toBeVisible({ timeout: 25_000 });
    await expect(page.getByTestId('restaurant-list').locator('> div').first()).toBeVisible({ timeout: 25_000 });
    expect(errors.filter(e => !/auth\/me|CORS|ERR_FAILED/.test(e))).toEqual([]);
  });

  test('select city, filter tiers, search restaurants', async ({ page }) => {
    await login(page);
    await page.goto('/markets');
    await page.getByTestId('city-Kochi').click();
    await expect(page.getByTestId('detail-title')).toHaveText('Kochi');
    await expect(page.getByText('Expansion recommendation')).toBeVisible({ timeout: 25_000 });
    await expect(page.getByTestId('restaurant-list')).toBeVisible({ timeout: 25_000 });
    await page.getByLabel('Search venues').fill('zzzzqqqq');
    await expect(page.getByText('No venues found')).toBeVisible();
    await page.getByLabel('Search venues').fill('');
    await page.getByRole('button', { name: 'Tier 1' }).first().click();
    await expect(page.locator('[data-testid^="city-"]')).toHaveCount(4);
    await page.getByLabel('Search cities').fill('del');
    await expect(page.locator('[data-testid^="city-"]')).toHaveCount(1);
  });

  test('mobile: list then detail with back', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await page.goto('/markets');
    await page.getByTestId('city-Pune').click();
    await expect(page.getByTestId('detail-title')).toHaveText('Pune');
    await page.getByRole('button', { name: 'All markets' }).click();
    await expect(page.getByTestId('city-Pune')).toBeVisible();
  });
});
