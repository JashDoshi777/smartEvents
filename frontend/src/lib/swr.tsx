'use client';

import { SWRConfig } from 'swr';
import type { Cache } from 'swr';

/**
 * Global data layer: stale-while-revalidate with the cache persisted to
 * localStorage, so a returning user sees the last known data on first paint
 * (instant, like a native app) while fresh data loads in the background.
 */
const STORE_KEY = 'liveiq-swr-cache-v1';
const MAX_ENTRIES = 80;

function localStorageProvider(): Cache {
  let map = new Map<string, unknown>();
  if (typeof window !== 'undefined') {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) map = new Map(JSON.parse(raw));
    } catch { /* corrupt or blocked storage — start empty */ }

    const persist = () => {
      try {
        const entries = Array.from(map.entries())
          .filter(([, v]) => v && typeof v === 'object' && (v as { data?: unknown }).data !== undefined)
          .slice(-MAX_ENTRIES)
          .map(([k, v]) => [k, { data: (v as { data: unknown }).data }]);
        localStorage.setItem(STORE_KEY, JSON.stringify(entries));
      } catch { /* quota exceeded — non-fatal */ }
    };
    window.addEventListener('beforeunload', persist);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') persist(); });
  }
  return map as unknown as Cache;
}

export function SWRProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        provider: localStorageProvider,
        revalidateOnFocus: false,
        revalidateIfStale: true,
        dedupingInterval: 20_000,
        keepPreviousData: true,
        errorRetryCount: 2,
        errorRetryInterval: 2500,
      }}
    >
      {children}
    </SWRConfig>
  );
}
