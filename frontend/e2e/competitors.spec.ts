import { test, expect } from '@playwright/test';
import { login, trackErrors } from './helpers';

test.describe.configure({ retries: 1 });

test.describe('Competitors', () => {
  test('renders platform comparison, gaps and feed without errors', async ({ page }) => {
    const errors = trackErrors(page);
    await login(page);
    await page.goto('/competitors');
    await expect(page.getByRole('heading', { name: 'Competitors' }).first()).toBeVisible();
    for (const id of ['district', 'bookmyshow', 'insider', 'ticketmaster_india']) {
      await expect(page.getByTestId(`platform-${id}`)).toBeVisible({ timeout: 25_000 });
    }
    await expect(page.getByText('Market gaps by city')).toBeVisible();
    await expect(page.locator('p', { hasText: 'Pune' }).first()).toBeVisible();
    // NewsAPI can be rate-limited upstream: accept either live articles (with safe external links) or the empty state.
    const link = page.locator('a[href^="http"][target="_blank"]').first();
    const empty = page.getByText('No recent coverage');
    await expect(link.or(empty)).toBeVisible({ timeout: 25_000 });
    if (await link.count()) await expect(link).toHaveAttribute('rel', /noopener/);
    expect(errors.filter(e => !/auth\/me|CORS|ERR_FAILED/.test(e))).toEqual([]);
  });

  test('switching city reloads intelligence and priority filter works', async ({ page }) => {
    await login(page);
    await page.goto('/competitors');
    await expect(page.getByTestId('platform-district')).toBeVisible({ timeout: 25_000 });
    await page.getByLabel('City').selectOption('Pune');
    await expect(page.getByText('Expansion opportunity in Pune')).toBeVisible({ timeout: 25_000 });
    await page.getByRole('button', { name: 'High', exact: true }).click();
    await expect(page.getByText('Low priority')).toHaveCount(0);
    await expect(page.getByText('High priority').first()).toBeVisible();
  });
});
