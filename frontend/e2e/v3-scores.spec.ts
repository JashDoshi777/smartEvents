import { test, expect } from '@playwright/test';
import { trackErrors } from './helpers';
import { apiGet, benign, qaLogin as login } from './qa-utils';

test.describe.configure({ retries: 1 });
const T = { timeout: 30_000 };

type Port = { portfolio: { id: string; name: string; composite_score: number | null; unrated?: boolean; score_confidence?: number | null; signals_used?: string[] | null }[]; total: number; unrated?: number };

test.describe('Score v3 cues', () => {
  test('portfolio API: unrated entities carry NULL composite + verdict, scored ones carry confidence and signals', async ({ page }) => {
    await login(page);
    const p = await apiGet<Port>(page, '/executive/portfolio?market=india');
    for (const e of p.portfolio) {
      if (e.composite_score == null) expect(e.unrated).toBe(true);
      else if (e.score_confidence != null) {
        expect(e.score_confidence).toBeGreaterThanOrEqual(0);
        expect(e.score_confidence).toBeLessThanOrEqual(1);
        expect((e.signals_used ?? []).length).toBeGreaterThanOrEqual(2);
      }
    }
  });

  test('unrated entity renders "Unrated" (no number), low-confidence tag, and the signal checks sheet (API mocked)', async ({ page }) => {
    const errors = trackErrors(page);
    await login(page);
    const base = { rank: 1, category: 'Music', country: 'India', primary_market: 'India', is_international: false, google_trend_score: null, news_mentions_7d: null, last_updated: null };
    const mockPortfolio = {
      portfolio: [
        { ...base, id: 'aaaaaaaa-0000-4000-8000-000000000001', name: 'Mock Scored Act', type: 'artist', composite_score: 61.2, health: 'Strong', unrated: false, score_confidence: 0.42, signals_used: ['youtube', 'wiki'] },
        { ...base, id: 'aaaaaaaa-0000-4000-8000-000000000002', name: 'Mock Unrated Act', type: 'artist', composite_score: null, health: 'Needs data', unrated: true, score_confidence: null, signals_used: [] },
      ],
      total: 2, offset: 0, market: 'all', with_scores: 1, unrated: 1, health_summary: { strong: 1, good: 0, needs_data: 1, weak: 0 },
    };
    await page.route(/\/executive\/portfolio/, r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockPortfolio) }));
    await page.route(/\/entities\/aaaaaaaa-0000-4000-8000-000000000002\/score/, r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      entity_id: 'aaaaaaaa-0000-4000-8000-000000000002', entity_name: 'Mock Unrated Act', composite_score: null, unrated: true, score_confidence: null, signals_used: [],
      score_verdict: 'Not enough verified data', trend_direction: 'stable',
      signal_validity: { youtube: 'unresolved', lastfm: 'wrong_type' },
      signals: { wikipedia_views_30d: null, google_trend_basis: 'none', news_confidence: 'ambiguous_skipped' }, last_updated: null, data_sources: [],
    }) }));
    await page.route(/\/entities\/aaaaaaaa-0000-4000-8000-00000000000\d\/cities/, r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entity_id: 'x', entity_name: 'x', cities: [], methodology: '' }) }));
    await page.addInitScript(() => { localStorage.setItem('liveiq-market-scope', 'india'); localStorage.removeItem('liveiq-swr-cache'); });
    await page.goto('/intelligence');
    const rows = page.getByRole('option');
    await expect(rows).toHaveCount(2, T);
    await expect(rows.nth(1).getByTestId('unrated')).toHaveText('Unrated');
    await expect(rows.nth(1)).not.toContainText(/\b0\.0\b/);
    await expect(rows.nth(0)).toContainText('61.2');
    await rows.nth(1).click();
    await expect(page.getByRole('heading', { name: 'Mock Unrated Act' })).toBeVisible(T);
    await expect(page.getByText('Not enough verified data').first()).toBeVisible(T);
    await page.getByTestId('signal-info').click();
    const dlg = page.getByRole('dialog');
    await expect(dlg.getByText('YouTube channel not identified, so it is not used')).toBeVisible();
    await expect(dlg.getByText(/Last\.fm not applicable to this type|Last\.fm not applicable to/)).toBeVisible();
    await expect(dlg.getByText(/News skipped: generic name/)).toBeVisible();
    await page.keyboard.press('Escape');
    await rows.nth(0).click();
    await expect(page.getByTestId('low-confidence').first()).toBeVisible(T);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('Trend Radar shows weekly views behind each momentum % and no breakout claims', async ({ page }) => {
    await login(page);
    await page.goto('/trends');
    await expect(page.getByText('Biggest movers')).toBeVisible(T);
    await expect(page.getByText(/breakout/i)).toHaveCount(0);
    const mom = await apiGet<{ risers: unknown[]; fallers: unknown[] }>(page, '/trends/momentum?market=india&limit=10');
    if (mom.risers.length) await expect(page.getByText(/views last week · was/).first()).toBeVisible(T);
    await page.getByRole('group', { name: 'Direction' }).getByRole('button', { name: 'Falling' }).click();
    await expect(page.getByRole('group', { name: 'Direction' }).getByRole('button', { name: 'Falling' })).toHaveAttribute('aria-pressed', 'true');
  });

  test('Data quality: Signals chips filter entities (request carries signal=...)', async ({ page }) => {
    await login(page);
    await page.goto('/data');
    await expect(page.getByTestId('signal-chips')).toBeVisible(T);
    const req = page.waitForRequest(r => r.url().includes('/admin/data-gaps') && r.url().includes('signal=youtube%3Aunresolved'), T);
    await page.getByTestId('signal-chips').getByRole('button', { name: 'YouTube unresolved' }).click();
    await req;
    await expect(page.getByTestId('gap-row').first()).toContainText(/YouTube unresolved/, T);
    await page.getByTestId('gap-row').first().click();
    await expect(page.getByLabel('YouTube channel ID (UC…)')).toBeVisible(T);
    await page.getByLabel('YouTube channel ID (UC…)').fill('@somehandle');
    await page.getByTestId('save-record').click();
    await expect(page.getByText(/Use the channel ID/)).toBeVisible();
  });
});
