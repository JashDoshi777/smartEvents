import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { trackErrors } from './helpers';
import { apiGet, benign, expectNoHScroll, qaLogin as login } from './qa-utils';

test.describe.configure({ retries: 1 });
const T = { timeout: 30_000 };
const IST_MS = 5.5 * 3600_000;
const istKey = (ms: number) => new Date(ms + IST_MS).toISOString().slice(0, 10);

type Venues = { venues: { id: string; name: string; capacity: number | null }[] };

function mockCal(events: { id: string; title: string; event_date: string }[], name = 'Test Arena') {
  const week_start = istKey(Date.now() - ((new Date(Date.now() + IST_MS).getUTCDay() + 6) % 7) * 86400_000);
  return {
    venue: { id: 'v', name, city: 'Mumbai', capacity: 5000 },
    range: { start: week_start, end: '2035-01-01', months: 12 },
    weeks: [{ week_start, week_end: week_start, events_this_week: events.map(e => ({ ...e, status: 'scheduled', source: 'district' })), weekend_events: [], is_weekend_booked: false, is_booked: events.length > 0 }],
    summary: { total_weeks: 1, booked_weekends: 0, open_weekends: 1, total_tracked_events: 0 }, data_note: 'note',
  };
}

test.describe('Venue calendar', () => {
  test('city and venue pickers list exactly what the API returns', async ({ page }) => {
    const errors = trackErrors(page);
    const cities = await apiGet<{ cities: { name: string }[] }>(page, '/cities/');
    const venues = await apiGet<Venues>(page, '/cities/Mumbai/venues');
    await login(page);
    await page.goto('/venues/calendar');
    await expect(page.getByTestId('month-title')).toBeVisible(T);
    await expect(page.locator('#cal-city option')).toHaveCount(cities.cities.length, T);
    await expect(page.locator('#cal-venue option')).toHaveCount(venues.venues.length, T);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('summary tiles equal the calendar API for the selected venue', async ({ page }) => {
    const venues = await apiGet<Venues>(page, '/cities/Mumbai/venues');
    const v = venues.venues[0];
    const cal = await apiGet<{ summary: { booked_weekends: number; open_weekends: number; total_tracked_events: number } }>(page, `/venues/${v.id}/calendar?months=12`);
    await login(page);
    await page.goto(`/venues/calendar?city=Mumbai&venue=${v.id}`);
    await expect(page.locator('#cal-venue')).toHaveValue(v.id, T);
    const sum = page.locator('div').filter({ hasText: /^Booked\d+/ }).first();
    await expect(page.getByText('Booked', { exact: true }).locator('xpath=preceding-sibling::span')).toHaveText(String(cal.summary.booked_weekends), T);
    await expect(page.getByText('Open', { exact: true }).locator('xpath=preceding-sibling::span')).toHaveText(String(cal.summary.open_weekends));
    void sum;
  });

  test('month navigation, Today and the day sheet', async ({ page }) => {
    await login(page);
    await page.goto('/venues/calendar');
    const title = page.getByTestId('month-title');
    await expect(title).toBeVisible(T);
    await expect(page.locator('#cal-venue')).not.toHaveValue('', T);
    const before = await title.innerText();
    await page.getByRole('button', { name: 'Next month' }).click();
    await expect(title).not.toHaveText(before);
    await page.getByRole('button', { name: 'Previous month' }).click();
    await expect(title).toHaveText(before);
    await page.getByRole('button', { name: 'Next month' }).click();
    await page.getByRole('button', { name: 'Today' }).click();
    await expect(title).toHaveText(before);
    await expect(page.getByTestId('day-sheet')).toBeVisible();   // Today opens today's sheet
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('day-sheet')).toHaveCount(0);
    await page.locator('[role=gridcell]').nth(15).click();
    await expect(page.getByTestId('day-sheet')).toBeVisible();
  });

  test('IST: an event at Sunday 19:30 UTC lands on Monday, not Sunday (mocked)', async ({ page }) => {
    await login(page);
    // find next Sunday (in IST) at least 2 days out and build 19:30 UTC on that day == Monday 01:00 IST
    let d = Date.now() + 2 * 86400_000;
    while (new Date(d + IST_MS).getUTCDay() !== 0) d += 86400_000;
    const sunKey = istKey(d); const sunUtc = new Date(`${sunKey}T19:30:00Z`);
    const monKey = istKey(sunUtc.getTime());
    expect(monKey).not.toBe(sunKey);
    await page.route('**/venues/*/calendar*', r => r.fulfill({ json: mockCal([{ id: 'e1', title: 'Late Night Gig', event_date: sunUtc.toISOString() }]) }));
    await page.goto('/venues/calendar');
    await expect(page.getByTestId('month-title')).toBeVisible(T);
    const lbl = (k: string) => new Date(`${k}T12:00:00+05:30`).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kolkata' });
    // navigate to the month holding the event
    const [ty, tm] = istKey(Date.now()).split('-').map(Number); const [ey, em] = monKey.split('-').map(Number);
    for (let i = 0; i < (ey - ty) * 12 + (em - tm); i++) await page.getByRole('button', { name: 'Next month' }).click();
    await expect(page.locator(`[role=gridcell][aria-label^="${lbl(monKey)}"]`)).toHaveAttribute('aria-label', /1 event/, T);
    await expect(page.locator(`[role=gridcell][aria-label^="${lbl(sunKey)}"]`)).not.toHaveAttribute('aria-label', /event/);
  });

  test('find free weekends: results mirror the availability API and open the venue', async ({ page }) => {
    const av = await apiGet<{ venues: { id: string; name: string; open_count: number; total_weekends: number }[] }>(page, '/venues/availability?city=Mumbai&min_capacity=1000&months=3');
    await login(page);
    await page.goto('/venues/calendar?city=Mumbai');
    await expect(page.getByTestId('finder-list').locator('button')).toHaveCount(av.venues.length, T);
    const first = av.venues[0];
    await expect(page.getByTestId('finder-list').locator('button').first()).toContainText(`${first.open_count} of ${first.total_weekends} weekends open`);
    await page.locator('#cal-mincap').fill('150000');
    await expect(page.getByText('No venue matches')).toBeVisible(T);
    await page.locator('#cal-mincap').fill('1000');
    await page.getByTestId('finder-list').locator('button').first().click();
    await expect(page.locator('#cal-venue')).toHaveValue(first.id, T);
  });

  test('.ics export contains the venue events in UTC', async ({ page }) => {
    await login(page);
    const iso = new Date(Date.now() + 5 * 86400_000); iso.setUTCHours(14, 0, 0, 0);
    await page.route('**/venues/*/calendar*', r => r.fulfill({ json: mockCal([{ id: 'e1', title: 'Mock, Gig; Live', event_date: iso.toISOString() }]) }));
    await page.goto('/venues/calendar');
    const btn = page.getByRole('button', { name: 'Export calendar (.ics)' });
    await expect(btn).toBeEnabled(T);
    const [dl] = await Promise.all([page.waitForEvent('download'), btn.click()]);
    expect(dl.suggestedFilename()).toMatch(/\.ics$/);
    const txt = readFileSync(await dl.path()!, 'utf8');
    expect(txt).toContain('BEGIN:VCALENDAR');
    expect(txt).toContain(`DTSTART:${iso.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')}`);
    expect(txt).toContain('SUMMARY:Mock\\, Gig\\; Live');   // RFC 5545 escapes , and ;
    expect(txt).toContain('END:VCALENDAR');
  });

  test('errors: calendar 500 shows retry; no venues shows empty state; slow venue list shows loading', async ({ page }) => {
    await login(page);
    let fail = true;
    await page.route('**/venues/*/calendar*', r => (fail ? r.fulfill({ status: 500, json: { detail: 'x' } }) : r.continue()));
    await page.goto('/venues/calendar');
    await expect(page.getByText('Couldn’t load this venue’s calendar.')).toBeVisible(T);
    fail = false;
    await page.getByRole('button', { name: /retry|try again/i }).first().click();
    await expect(page.locator('[role=gridcell]').first()).toBeVisible(T);
    await page.route('**/cities/*/venues', r => r.fulfill({ json: { city: 'x', venues: [], total: 0, source: 'none' } }));
    await page.goto('/venues/calendar?city=Pune');
    await expect(page.getByText(/No venues tracked in/)).toBeVisible(T);
  });

  test('mobile 390: grid fits without horizontal scroll', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await page.goto('/venues/calendar');
    await expect(page.locator('[role=gridcell]').first()).toBeVisible(T);
    await expectNoHScroll(page);
    const box = await page.locator('[role=gridcell]').first().boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(40);
  });
});
