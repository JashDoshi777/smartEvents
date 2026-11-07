import { test, expect } from '@playwright/test';
import { login, trackErrors } from './helpers';

test.describe.configure({ retries: 1 });

test.describe('Venue calendar', () => {
  test('month grid, navigation and day sheet', async ({ page }) => {
    const errors = trackErrors(page);
    await login(page);
    await page.goto('/venues/calendar');
    const title = page.getByTestId('month-title');
    await expect(title).toBeVisible({ timeout: 25_000 });
    await expect(page.getByLabel('Venue')).not.toHaveValue('', { timeout: 25_000 });
    const before = await title.innerText();
    await page.getByRole('button', { name: 'Next month' }).click();
    await expect(title).not.toHaveText(before);
    await page.getByRole('button', { name: 'Previous month' }).click();
    await expect(title).toHaveText(before);
    await page.locator('[role=gridcell]').nth(15).click();
    await expect(page.getByTestId('day-sheet')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('day-sheet')).toHaveCount(0);
    expect(errors.filter(e => !/auth\/me|CORS|ERR_FAILED/.test(e))).toEqual([]);
  });

  test('event dots appear for tracked events (mocked calendar)', async ({ page }) => {
    await login(page);
    const d = new Date(); d.setUTCHours(14, 0, 0, 0);
    const iso = d.toISOString();
    await page.route('**/venues/*/calendar*', r => r.fulfill({ json: {
      venue: { id: 'v', name: 'Test Arena', city: 'Mumbai', capacity: 5000 },
      range: { start: '2020-01-01', end: '2035-01-01', months: 12 },
      weeks: [{ week_start: iso.slice(0, 10), week_end: iso.slice(0, 10), events_this_week: [{ id: 'e1', title: 'Mock Gig', event_date: iso, status: 'scheduled', source: 'district' }], weekend_events: [], is_weekend_booked: false, is_booked: true }],
      summary: { total_weeks: 1, booked_weekends: 0, open_weekends: 1, total_tracked_events: 0 }, data_note: 'note',
    } }));
    await page.goto('/venues/calendar');
    await expect(page.getByText('Mock Gig').first()).toBeVisible({ timeout: 25_000 });
    await page.locator('[role=gridcell][aria-label*="1 event"]').first().click();
    await expect(page.getByTestId('day-sheet')).toContainText('Mock Gig');
  });
});
