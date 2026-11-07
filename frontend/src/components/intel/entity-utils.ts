import useSWR from 'swr';
import { useMarketScope, isIndianEntity } from '@/components/providers/MarketScopeProvider';
import { getPortfolio, PortfolioEntity } from '@/lib/api';

export function scoreColor(s: number | null | undefined) {
  if (s == null || s <= 0) return 'var(--text-tertiary)';
  return 'var(--text-primary)';
}

export type Verdict = { label: string; tone: 'accent' | 'neutral'; color: string; blurb: string };

/** Transparent, score-only verdict (same bands as the Sign / Consider / Pass model). */
export function verdictFor(s: number | null | undefined): Verdict {
  if (s == null) return { label: 'No data', tone: 'neutral', color: 'var(--text-tertiary)', blurb: 'No metrics collected yet. The entity worker refreshes scores every few hours.' };
  if (s >= 70) return { label: 'Sign now', tone: 'accent', color: 'var(--accent)', blurb: 'Top-tier composite score with strong momentum. Worth fast-tracking a deal.' };
  if (s >= 50) return { label: 'Strong candidate', tone: 'accent', color: 'var(--accent)', blurb: 'Healthy score. Negotiate terms and target Tier-1 cities with mid-size venues.' };
  if (s >= 35) return { label: 'Watch', tone: 'neutral', color: 'var(--text-secondary)', blurb: 'Moderate momentum. Monitor for a few weeks before committing.' };
  return { label: 'Pass', tone: 'neutral', color: 'var(--text-secondary)', blurb: 'Low score relative to the portfolio. Explore smaller venues or pass.' };
}

export function typeLabel(t: string | null | undefined) {
  const m: Record<string, string> = { artist: 'Artist', movie: 'Film', sports_team: 'Sports', comedian: 'Comedy', theatre_group: 'Theatre' };
  return t ? (m[t] ?? t.replace(/_/g, ' ')) : '—';
}

export function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/** Portfolio scoped by the global India/Global toggle. Shared SWR key so pages reuse the cache. */
export function useScopedPortfolio() {
  const { scope } = useMarketScope();
  const q = useSWR('portfolio/all', () => getPortfolio(), { refreshInterval: 180000 });
  const all: PortfolioEntity[] = q.data?.portfolio ?? [];
  const scoped = all.filter(e => (scope === 'india' ? isIndianEntity(e) : !isIndianEntity(e)));
  return { ...q, all, scoped, scope };
}
