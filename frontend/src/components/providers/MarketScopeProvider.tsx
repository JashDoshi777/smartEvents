'use client';

/* eslint-disable react-hooks/set-state-in-effect -- these effects sync state from external sources (URL params, localStorage, debounced network results), which is the intended use */

import { createContext, useContext, useEffect, useMemo, useState } from 'react';

export type MarketScope = 'india' | 'global';

const KEY = 'liveiq-market-scope';
const Ctx = createContext<{ scope: MarketScope; setScope: (s: MarketScope) => void; isIndia: boolean }>({
  scope: 'india', setScope: () => {}, isIndia: true,
});

/** India-first by default. Pages read `scope` to filter entity/market data. */
export function MarketScopeProvider({ children }: { children: React.ReactNode }) {
  const [scope, setScopeState] = useState<MarketScope>('india');

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === 'india' || saved === 'global') setScopeState(saved);
    } catch { /* ignore */ }
  }, []);

  const value = useMemo(() => ({
    scope,
    isIndia: scope === 'india',
    setScope: (s: MarketScope) => {
      setScopeState(s);
      try { localStorage.setItem(KEY, s); } catch { /* ignore */ }
    },
  }), [scope]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useMarketScope = () => useContext(Ctx);

/** Is an entity/record part of the Indian market? Handles all shapes the API returns. */
export function isIndianEntity(e: { primary_market?: string | null; country?: string | null; is_international?: boolean | null; market?: string | null }): boolean {
  // Foreign acts that tour India are "global" even when their target market is India.
  if (e.is_international === true) return false;
  if (e.primary_market) return e.primary_market.toLowerCase() === 'india';
  if (e.market) return e.market.toLowerCase() === 'india';
  if (e.country) return e.country.toLowerCase() === 'india';
  return e.is_international === false;
}
