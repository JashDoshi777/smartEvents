'use client';

import { useCallback, useMemo, useSyncExternalStore } from 'react';

function read(key: string): string {
  try { return window.localStorage.getItem(key) ?? '[]'; } catch { return '[]'; }
}

/**
 * A localStorage-backed list that is SSR-safe (server snapshot is empty), syncs across tabs and
 * across components using the same key, and never throws when storage is blocked.
 */
export function useLocalList<T>(key: string, max = 20): readonly [T[], (next: T[]) => void] {
  const subscribe = useCallback((cb: () => void) => {
    window.addEventListener('storage', cb);
    window.addEventListener(`locallist:${key}`, cb);
    return () => { window.removeEventListener('storage', cb); window.removeEventListener(`locallist:${key}`, cb); };
  }, [key]);
  const raw = useSyncExternalStore(subscribe, () => read(key), () => '[]');
  const list = useMemo<T[]>(() => { try { const v = JSON.parse(raw); return Array.isArray(v) ? v : []; } catch { return []; } }, [raw]);
  const set = useCallback((next: T[]) => {
    try { window.localStorage.setItem(key, JSON.stringify(next.slice(0, max))); } catch { /* storage blocked: keep UI usable */ }
    window.dispatchEvent(new Event(`locallist:${key}`));
  }, [key, max]);
  return [list, set] as const;
}
