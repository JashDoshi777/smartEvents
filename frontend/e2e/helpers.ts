import { Page, expect } from '@playwright/test';

export const API = process.env.E2E_API_URL ?? 'http://localhost:8000';
const EMAIL = process.env.E2E_EMAIL ?? 'qa@liveiq.dev';
const PASSWORD = process.env.E2E_PASSWORD ?? 'QaTest#2026';

type Tokens = { access_token: string; refresh_token: string };
let cached: { t: Tokens; at: number } | null = null;

/** Fresh login with 429-aware retry (the API rate-limits /auth/login to 10/min per IP, shared by all specs). */
export async function freshTokens(page: Page): Promise<Tokens> {
  for (let i = 0; i < 6; i++) {
    const res = await page.request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
    if (res.status() === 429) { await new Promise(r => setTimeout(r, 12_000)); continue; }
    expect(res.ok(), 'login API should succeed').toBeTruthy();
    return (await res.json()).tokens;
  }
  throw new Error('login API rate-limited');
}

/** One login per worker (re-used for 8 minutes) so a big suite never trips the login rate limit. */
export async function tokens(page: Page): Promise<Tokens> {
  if (!cached || Date.now() - cached.at > 8 * 60_000) cached = { t: await freshTokens(page), at: Date.now() };
  return cached.t;
}

/** Log in through the real API and seed the SPA's token storage. */
export async function login(page: Page) {
  const t = await tokens(page);
  await page.addInitScript(t => {
    localStorage.setItem('liveiq_access_token', t.access_token);
    localStorage.setItem('liveiq_refresh_token', t.refresh_token);
    localStorage.setItem('liveiq-theme', 'dark');
  }, t);
}

/** Collect console/page errors so specs can assert a page is clean. */
export function trackErrors(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 500) errors.push(`${r.status()} ${r.url()}`); });
  return errors;
}

/** Authenticated GET straight against the backend (ground truth for UI == API assertions). */
export async function apiGet<T = unknown>(page: Page, path: string): Promise<T> {
  const t = await tokens(page);
  const res = await page.request.get(`${API}${path}`, { headers: { Authorization: `Bearer ${t.access_token}` }, timeout: 60_000 });
  expect(res.ok(), `${path} should be 200`).toBeTruthy();
  return res.json() as Promise<T>;
}

/** Noise that is not an app bug (dev-mode preload warnings, aborted requests on navigation). */
export const benign = (e: string) => /ERR_|favicon|preloaded using link preload|Download the React DevTools|net::|Failed to load resource: the server responded with a status of (404|401)/.test(e);
