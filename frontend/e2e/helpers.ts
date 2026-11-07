import { Page, expect } from '@playwright/test';

export const API = process.env.E2E_API_URL ?? 'http://localhost:8000';
const EMAIL = process.env.E2E_EMAIL ?? 'qa@liveiq.dev';
const PASSWORD = process.env.E2E_PASSWORD ?? 'QaTest#2026';

/** Log in through the real API and seed the SPA's token storage (fresh token every call). */
export async function login(page: Page) {
  const res = await page.request.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
  expect(res.ok(), 'login API should succeed').toBeTruthy();
  const { tokens } = await res.json();
  await page.addInitScript(t => {
    localStorage.setItem('liveiq_access_token', t.access_token);
    localStorage.setItem('liveiq_refresh_token', t.refresh_token);
    localStorage.setItem('liveiq-theme', 'dark');
  }, tokens);
}

/** Collect console/page errors so specs can assert a page is clean. */
export function trackErrors(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 500) errors.push(`${r.status()} ${r.url()}`); });
  return errors;
}
