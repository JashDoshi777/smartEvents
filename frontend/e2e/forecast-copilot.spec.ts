import { test, expect, Page } from '@playwright/test';
import { trackErrors } from './helpers';
import { apiGet, apiToken, benign, expectNoHScroll, qaLogin as login } from './qa-utils';
import { forecastFixture, sseBody } from './intel-fixtures';

test.describe.configure({ retries: 1 });
const T = { timeout: 45_000 };
const API = process.env.E2E_API_URL ?? 'http://localhost:8000';
const alertBox = (page: Page) => page.locator('[role=alert]:not(#__next-route-announcer__)');

test.describe('Demand forecast', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  test('empty prompt, then the real insufficient-history state matches the API counts', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/intelligence/forecast');
    await expect(page.getByText('Pick an artist to forecast')).toBeVisible(T);
    const chip = page.locator('[aria-label="Quick picks"] .chip').first();
    await chip.click(T);
    const name = (await chip.innerText()).trim();
    const port = await apiGet<{ portfolio: { id: string; name: string }[] }>(page, '/executive/portfolio');
    const id = port.portfolio.find(e => e.name === name)!.id;
    const f = await apiGet<{ status: string; history_points: number; history_span_days: number; minimum_required?: { points: number; span_days: number } }>(page, `/intelligence/${id}/forecast?months=3`);
    if (f.status === 'insufficient_history') {
      await expect(page.getByText(`Not enough history for ${name}`)).toBeVisible(T);
      await expect(page.getByText(`${f.history_points} / ${f.minimum_required!.points}`)).toBeVisible();
      await expect(page.getByText(`${f.history_span_days} / ${f.minimum_required!.span_days}`)).toBeVisible();
    } else {
      await expect(page.locator('.recharts-area').first()).toBeVisible(T);
    }
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('ok forecast renders chart + band; horizon change refetches with the new months (mocked)', async ({ page }) => {
    const urls: string[] = [];
    await page.route('**/intelligence/*/forecast*', r => { urls.push(r.request().url()); return r.fulfill({ json: forecastFixture() }); });
    await page.goto('/intelligence/forecast');
    await page.locator('[aria-label="Quick picks"] .chip').first().click(T);
    await expect(page.locator('.recharts-area').first()).toBeVisible(T);
    await expect(page.getByText('rising').first()).toBeVisible();
    await page.getByRole('group', { name: 'Forecast horizon' }).getByRole('button', { name: '6 mo' }).click();
    await expect.poll(() => urls.some(u => u.includes('months=6'))).toBe(true);
    // forecast bounds invariant on the fixture the UI consumes: lower <= predicted <= upper
    const f = forecastFixture();
    for (const p of f.forecast) { expect(p.lower_bound).toBeLessThanOrEqual(p.predicted_trend_score); expect(p.predicted_trend_score).toBeLessThanOrEqual(p.upper_bound); }
  });

  test('404 / 500 / 503 show distinct readable errors with retry', async ({ page }) => {
    for (const [status, text] of [[404, /couldn’t find that artist/i], [500, /couldn’t fit/i], [503, /Prophet/]] as const) {
      await page.route('**/intelligence/*/forecast*', r => r.fulfill({ status, json: { detail: 'x' } }));
      await page.goto('/intelligence/forecast');
      await page.locator('[aria-label="Quick picks"] .chip').first().click(T);
      await expect(alertBox(page)).toContainText(text, T);
      await expect(page.getByRole('button', { name: /Try again/ })).toBeVisible();
      await page.unroute('**/intelligence/*/forecast*');
    }
  });

  test('mobile 390 has no horizontal scroll', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route('**/intelligence/*/forecast*', r => r.fulfill({ json: forecastFixture() }));
    await page.goto('/intelligence/forecast');
    await page.locator('[aria-label="Quick picks"] .chip').first().click(T);
    await expect(page.locator('.recharts-area').first()).toBeVisible(T);
    await expectNoHScroll(page);
  });
});

test.describe('AI Copilot', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  const sse = (chunks: string[], sources?: string[]) => (sources ? `data: ${JSON.stringify({ sources })}\n\n` : '') + sseBody(chunks);
  const ask = async (page: Page, text: string) => { await page.getByLabel('Message').fill(text); await page.keyboard.press('Enter'); };

  test('streams markdown incl. tables, shows data sources, copy works (mocked SSE)', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const errors = trackErrors(page);
    await page.route('**/copilot/stream', r => r.fulfill({ contentType: 'text/event-stream', body: sse(['**Nagpur** looks strong.\n\n', '| City | Score |\n|---|---|\n| Pune | 83.4 |\n\n', '- ₹1,800 avg ticket'], ['City market scores (12 cities)', 'Ticket price benchmarks']) }));
    await page.goto('/copilot');
    await expect(page.getByText('Ask about the Indian live-events market')).toBeVisible(T);
    await page.getByRole('button', { name: /Tier-2 city should District/ }).click();
    await expect(page.locator('strong', { hasText: 'Nagpur' })).toBeVisible(T);
    await expect(page.locator('table td', { hasText: '83.4' })).toBeVisible();
    await expect(page.getByText('₹1,800 avg ticket')).toBeVisible();
    await expect(page.getByTestId('sources')).toContainText('City market scores (12 cities)');
    await page.getByLabel('Copy answer').click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('Nagpur');
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('regenerate re-asks the same question and replaces the answer', async ({ page }) => {
    let n = 0;
    const bodies: string[] = [];
    await page.route('**/copilot/stream', r => { n++; bodies.push(r.request().postData() ?? ''); return r.fulfill({ contentType: 'text/event-stream', body: sse([n === 1 ? 'First answer' : 'Second answer']) }); });
    await page.goto('/copilot');
    await ask(page, 'hello there');
    await expect(page.getByText('First answer')).toBeVisible(T);
    await page.getByLabel('Regenerate answer').click();
    await expect(page.getByText('Second answer')).toBeVisible(T);
    await expect(page.getByText('First answer')).toHaveCount(0);
    expect(n).toBe(2);
    expect(JSON.parse(bodies[1]).messages.map((m: { role: string }) => m.role)).toEqual(['user']);   // history excludes the discarded answer
  });

  test('history persists across reload; open, delete and new chat work', async ({ page }) => {
    await page.route('**/copilot/stream', r => r.fulfill({ contentType: 'text/event-stream', body: sse(['Saved reply']) }));
    await page.goto('/copilot');
    await ask(page, 'remember me please');
    await expect(page.getByText('Saved reply')).toBeVisible(T);
    await page.getByLabel('New chat').click();
    await expect(page.getByText('Ask about the Indian live-events market')).toBeVisible();
    await page.reload();
    await page.getByLabel('Chat history').click();
    await expect(page.getByTestId('history-item')).toHaveCount(1, T);
    await expect(page.getByTestId('history-item')).toContainText('remember me please');
    await page.getByTestId('history-item').click();
    await expect(page.getByText('Saved reply')).toBeVisible();
    await page.getByLabel('Chat history').click();
    await page.getByRole('button', { name: /^Delete remember me/ }).click();
    await expect(page.getByTestId('history-item')).toHaveCount(0);
  });

  test('stop mid-flight keeps the UI usable; new chat while busy does not crash', async ({ page }) => {
    const errors = trackErrors(page);
    await page.route('**/copilot/stream', async r => { await new Promise(res => setTimeout(res, 6000)); await r.fulfill({ contentType: 'text/event-stream', body: sse(['too late']) }).catch(() => {}); });
    await page.goto('/copilot');
    await ask(page, 'long question');
    await expect(page.getByLabel('Stop generating')).toBeVisible(T);
    await page.getByLabel('Stop generating').click();
    await expect(page.getByLabel('Send')).toBeVisible();
    await expect(page.getByText('Stopped.')).toBeVisible();
    await expect(page.getByText('too late')).toHaveCount(0);
    await ask(page, 'second question');
    await expect(page.getByLabel('Stop generating')).toBeVisible();
    await page.getByLabel('New chat').click();            // concurrent: abort + reset while streaming
    await expect(page.getByText('Ask about the Indian live-events market')).toBeVisible();
    await expect(page.getByLabel('Send')).toBeVisible();
    await page.waitForTimeout(500);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('error then retry succeeds; mid-stream error keeps partial text with a notice', async ({ page }) => {
    let fail = true;
    await page.route('**/copilot/chat', r => r.fulfill({ status: 502, json: { detail: 'bad' } }));
    await page.route('**/copilot/stream', r => (fail ? r.fulfill({ status: 500, body: 'x' }) : r.fulfill({ contentType: 'text/event-stream', body: sse(['Recovered answer']) })));
    await page.goto('/copilot');
    await ask(page, 'hello');
    await expect(alertBox(page)).toContainText(/not responding/i, T);
    fail = false;
    await page.getByRole('button', { name: /Try again/ }).click();
    await expect(page.getByText('Recovered answer')).toBeVisible(T);
    await page.getByLabel('New chat').click();
    await page.unroute('**/copilot/stream');
    await page.route('**/copilot/stream', r => r.fulfill({ contentType: 'text/event-stream', body: `data: ${JSON.stringify({ chunk: 'Half an ans' })}\n\ndata: ${JSON.stringify({ error: 'upstream died' })}\n\n` }));
    await ask(page, 'again');
    await expect(page.getByText('Half an ans')).toBeVisible(T);
    await expect(alertBox(page)).toContainText('interrupted');
  });

  test('model picker lists API models and the choice is sent with the request', async ({ page }) => {
    const models = await apiGet<{ available_models: { id: string; name: string }[] }>(page, '/copilot/models');
    let sent = '';
    await page.route('**/copilot/stream', r => { sent = r.request().postData() ?? ''; return r.fulfill({ contentType: 'text/event-stream', body: sse(['ok']) }); });
    await page.goto('/copilot');
    await page.getByRole('button', { name: /GPT|Model/ }).first().click();
    await expect(page.getByRole('menuitemradio')).toHaveCount(models.available_models.length);
    const target = models.available_models[models.available_models.length - 1];
    await page.getByRole('menuitemradio', { name: new RegExp(target.name) }).click();
    await ask(page, 'hi');
    await expect(page.getByText('ok', { exact: true })).toBeVisible(T);
    expect(JSON.parse(sent).model).toBe(target.id);
  });

  test('long answer streams without layout break or horizontal scroll', async ({ page }) => {
    const para = Array.from({ length: 120 }, (_, i) => `Line ${i} with a fairly long sentence about Indian live events and ₹ pricing across tiers. `);
    await page.route('**/copilot/stream', r => r.fulfill({ contentType: 'text/event-stream', body: sse(para.map(p => p + '\n\n')) }));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/copilot');
    await ask(page, 'write a lot');
    await expect(page.getByText('Line 119 with a fairly')).toBeVisible(T);
    await expectNoHScroll(page);
    await expect(page.getByLabel('Message')).toBeVisible();
  });

  test('REAL backend: grounded answer cites our data and names the top-scoring city', async ({ page }) => {
    test.setTimeout(120_000);
    const errors = trackErrors(page);
    const cities = await apiGet<{ cities: { name: string; scores: { composite: number | null } }[] }>(page, '/cities/');
    const top = [...cities.cities].sort((a, b) => (b.scores.composite ?? 0) - (a.scores.composite ?? 0))[0];
    await page.goto('/copilot');
    await ask(page, 'Using only the LIVE DATA you have, which tracked Indian city has the highest composite market score? Reply with just the city name and its score.');
    await expect(page.getByLabel('Stop generating')).toBeVisible(T);
    await expect(page.getByLabel('Send')).toBeVisible({ timeout: 90_000 });
    const reply = page.locator('[data-role=assistant]').last();
    await expect(reply).toContainText(top.name, { ignoreCase: true });
    await expect(page.getByTestId('sources')).toContainText('City market scores');
    await expect(alertBox(page)).toHaveCount(0);
    expect(errors.filter(e => !benign(e))).toEqual([]);
  });

  test('API grounding: stream starts with a sources frame; chat endpoint returns sources', async ({ page }) => {
    const token = await apiToken(page);
    const res = await page.request.post(`${API}/copilot/chat`, { data: { question: 'Which city has the most venues?', max_tokens: 64 }, headers: { Authorization: `Bearer ${token}` }, timeout: 60_000 });
    expect(res.status()).toBe(200);
    const j = await res.json();
    expect(Array.isArray(j.sources)).toBe(true);
    expect(j.sources.join(' ')).toContain('City market scores');
    expect((await page.request.post(`${API}/copilot/chat`, { data: {}, headers: { Authorization: `Bearer ${token}` } })).status()).toBe(422);
  });

  test('mobile 390 light: welcome + suggestions fit, composer reachable', async ({ page }) => {
    await login(page, 'light');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/copilot');
    await expect(page.getByText('Ask about the Indian live-events market')).toBeVisible(T);
    await expectNoHScroll(page);
    const box = await page.getByLabel('Message').boundingBox();
    expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  });
});
