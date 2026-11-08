import { Page, expect } from '@playwright/test';
import { API } from './helpers';

const EMAIL = process.env.E2E_EMAIL ?? 'qa@liveiq.dev';
const PASSWORD = process.env.E2E_PASSWORD ?? 'QaTest#2026';

type Tokens = { access_token: string; refresh_token: string };
let cached: { tokens: Tokens; at: number } | null = null;
/** One login per worker (the API allows 10 logins/minute): tokens are reused across tests for 8 minutes. */
async function tokens(page: Page): Promise<Tokens> {
  if (cached && Date.now() - cached.at < 480_000) return cached.tokens;
  let last = 0;
  for (let i = 0; i < 4; i++) {
    const res = await page.request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
    last = res.status();
    if (res.ok()) { cached = { tokens: (await res.json()).tokens, at: Date.now() }; return cached.tokens; }
    await page.waitForTimeout(7000 * (i + 1));   // login limiter: back off instead of failing the suite
  }
  throw new Error(`login failed (${last})`);
}
export const apiToken = async (page: Page) => (await tokens(page)).access_token;

/** Seeds SPA token storage from the shared per-worker login (dark theme default). */
export async function qaLogin(page: Page, theme: 'dark' | 'light' = 'dark') {
  const t = await tokens(page);
  await page.addInitScript(([tk, th]) => {
    localStorage.setItem('liveiq_access_token', (tk as Tokens).access_token);
    localStorage.setItem('liveiq_refresh_token', (tk as Tokens).refresh_token);
    localStorage.setItem('liveiq-theme', th as string);
  }, [t, theme] as const);
}

export async function apiGet<T = any>(page: Page, path: string): Promise<T> { // eslint-disable-line @typescript-eslint/no-explicit-any
  const res = await page.request.get(`${API}${path}`, { headers: { Authorization: `Bearer ${await apiToken(page)}` }, timeout: 60_000 });
  expect(res.ok(), `${path} -> ${res.status()}`).toBeTruthy();
  return res.json();
}

/** Console noise that is not an app bug (auth refresh race, aborted prefetches, third-party image hosts). */
export const benign = (e: string) => /auth\/me|CORS|ERR_FAILED|net::ERR_ABORTED|Failed to load resource.*(401|429)|favicon/i.test(e);

export async function expectNoHScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(over, 'page must not scroll horizontally').toBeLessThanOrEqual(1);
}
