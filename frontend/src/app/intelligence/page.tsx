'use client';

import { useState, useEffect } from 'react';
import { ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR, { mutate } from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Brain, TrendingUp, ArrowUpRight, ArrowDownRight,
  Globe, Music2, Star, Zap, ChevronRight, Users, Info,
  CheckCircle, XCircle, AlertCircle, Filter
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getWatchlist, addToWatchlist, removeFromWatchlist, optimizePrice, PortfolioEntity } from '@/lib/api';
import styles from './page.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreColor(s: number | null) {
  if (!s) return 'var(--text-tertiary)';
  if (s >= 70) return 'var(--positive)';
  if (s >= 45) return 'var(--accent)';
  return 'var(--warning)';
}

function scoreLabel(s: number | null): { label: string; color: string; icon: ReactNode } {
  if (!s) return { label: 'No data', color: 'var(--text-tertiary)', icon: <Info size={14} /> };
  if (s >= 70) return { label: 'Sign Now', color: 'var(--positive)', icon: <CheckCircle size={14} /> };
  if (s >= 50) return { label: 'Strong Candidate', color: 'var(--accent)', icon: <TrendingUp size={14} /> };
  if (s >= 35) return { label: 'Watch', color: 'var(--warning)', icon: <AlertCircle size={14} /> };
  return { label: 'Pass', color: 'var(--negative)', icon: <XCircle size={14} /> };
}

// ── Score ring SVG ────────────────────────────────────────────────────────────
function ScoreRing({ score, size = 72 }: { score: number | null; size?: number }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const pct = score ? Math.min(score / 100, 1) : 0;
  const dash = pct * circ;
  const color = scoreColor(score);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--divider)" strokeWidth={5} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={5}
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 0.7s cubic-bezier(0.25,0.46,0.45,0.94)' }}
      />
    </svg>
  );
}

// ── Entity detail panel ────────────────────────────────────────────────────────
function EntityPanel({
  entity, onClose, isWatched, onToggleWatch,
}: {
  entity: PortfolioEntity;
  onClose: () => void;
  isWatched: boolean;
  onToggleWatch: () => void;
}) {
  const rec = scoreLabel(entity.composite_score);

  return (
    <motion.div
      className={styles.panel}
      initial={{ opacity: 0, x: 32 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 32 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {/* Header */}
      <div className={styles.panelHeader}>
        <div className={styles.panelAvatar}>{entity.name.charAt(0).toUpperCase()}</div>
        <div className={styles.panelTitle}>
          <h2 className="t-title2 text-primary">{entity.name}</h2>
          <p className="t-callout text-tertiary">
            {entity.category ?? entity.type}
            {entity.is_international && ' · International'}
            {' · '}{entity.country}
          </p>
        </div>
        <button
          className="btn btn-icon"
          onClick={onToggleWatch}
          title={isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
          style={{ color: isWatched ? 'var(--warning)' : undefined }}
        >
          <Star size={18} fill={isWatched ? 'var(--warning)' : 'none'} />
        </button>
        <button className="btn btn-icon" onClick={onClose} title="Close">
          <XCircle size={18} />
        </button>
      </div>

      {/* Score + Recommendation */}
      <div className={styles.panelScore}>
        <div className={styles.ringWrap}>
          <ScoreRing score={entity.composite_score} size={88} />
          <div className={styles.ringLabel}>
            <span style={{ fontSize: '1.5rem', fontWeight: 800, letterSpacing: '-0.05em', color: scoreColor(entity.composite_score) }}>
              {entity.composite_score ?? '—'}
            </span>
            <span className="t-caption text-tertiary">/100</span>
          </div>
        </div>
        <div className={styles.recBox} style={{ borderColor: rec.color + '33', background: rec.color + '11' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: rec.color }}>
            {rec.icon}
            <span style={{ fontSize: '1rem', fontWeight: 700, color: rec.color }}>{rec.label}</span>
          </div>
          <p className="t-footnote text-tertiary" style={{ marginTop: 4 }}>
            {entity.composite_score && entity.composite_score >= 70
              ? 'High composite score + strong trend momentum. Recommend fast-track signing.'
              : entity.composite_score && entity.composite_score >= 50
              ? 'Good score — negotiate terms, target Tier-1 cities, mid-size venues.'
              : entity.composite_score && entity.composite_score >= 35
              ? 'Moderate momentum. Monitor for 30 days before committing.'
              : entity.composite_score
              ? 'Low score relative to portfolio. Explore smaller venues or pass.'
              : 'No metrics collected yet. Run the entity worker to generate intelligence.'}
          </p>
        </div>
      </div>

      {/* Signal breakdown */}
      <div className={styles.signals}>
        <p className="t-label text-tertiary" style={{ marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem' }}>Signal Breakdown</p>
        {[
          { label: 'Google Trend Score', value: entity.google_trend_score, max: 100, unit: '' },
          { label: 'News Mentions (7d)', value: entity.news_mentions_7d, max: 50, unit: ' articles' },
          { label: 'Composite Score', value: entity.composite_score, max: 100, unit: '' },
        ].map(({ label, value, max, unit }) => (
          <div key={label} className={styles.signalRow}>
            <div className={styles.signalMeta}>
              <span className="t-footnote text-secondary">{label}</span>
              <span className="t-footnote text-primary" style={{ fontWeight: 600 }}>
                {value != null ? `${value}${unit}` : '—'}
              </span>
            </div>
            <div className={styles.signalTrack}>
              <motion.div
                className={styles.signalFill}
                style={{ background: scoreColor(value) }}
                initial={{ width: 0 }}
                animate={{ width: value != null ? `${Math.min((value / max) * 100, 100)}%` : '0%' }}
                transition={{ duration: 0.65, ease: [0.25, 0.46, 0.45, 0.94] }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Trend sparkline — pending real history endpoint */}
      <div className={styles.sparkSection}>
        <p className="t-label text-tertiary" style={{ marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem' }}>Score Trend</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 100 }}>
          <Info size={14} color="var(--text-tertiary)" />
          <span className="t-caption text-tertiary">Not available yet — needs a /entities/:id/history endpoint over real metric time-series.</span>
        </div>
        <p className="t-caption text-tertiary" style={{ marginTop: 6 }}>
          Live trend data populates as the entity metrics worker runs every 6 hours.
        </p>
      </div>

      {/* Quick actions */}
      <div className={styles.panelActions}>
        <button className="btn btn-primary" style={{ flex: 1 }}>
          <Zap size={14} /> Run Venue Match
        </button>
        <button className="btn btn-secondary" style={{ flex: 1 }}>
          <Brain size={14} /> Ask AI About This Act
        </button>
      </div>
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Intelligence Hub Page
// ═══════════════════════════════════════════════════════════════════════════════

const TYPES = ['All', 'artist', 'film', 'sports', 'comedy', 'festival'];
const MARKETS = ['All', 'India', 'Global'] as const;
type MarketFilter = typeof MARKETS[number];

export default function IntelligencePage() {
  const searchParams = useSearchParams();
  const [query, setQuery]           = useState('');
  const [typeFilter, setTypeFilter] = useState('All');
  const [marketFilter, setMarketFilter] = useState<MarketFilter>('All');
  const [selected, setSelected]     = useState<PortfolioEntity | null>(null);

  const { data: portfolio, isLoading } = useSWR('portfolio/all', () => getPortfolio(), {
    refreshInterval: 120000,
    shouldRetryOnError: false,
  });

  // Deep-link support: Topbar's global search links here as
  // /intelligence?entity=<id> — once the portfolio loads, auto-select
  // the matching real entity so the link actually lands somewhere
  // instead of just opening the page with nothing selected.
  useEffect(() => {
    const entityId = searchParams.get('entity');
    if (!entityId || !portfolio?.portfolio) return;
    const match = portfolio.portfolio.find(e => e.id === entityId);
    if (match) setSelected(match);
  }, [searchParams, portfolio]);
  const { data: watchlistData } = useSWR('watchlist', () => getWatchlist(), { shouldRetryOnError: false });
  const watchedIds = new Set((watchlistData?.watchlist ?? []).map(w => w.id));

  async function handleToggleWatch(entityId: string) {
    if (watchedIds.has(entityId)) {
      await removeFromWatchlist(entityId);
    } else {
      await addToWatchlist(entityId);
    }
    mutate('watchlist');
  }

  const entities = portfolio?.portfolio ?? [];
  // is_international is a real signal set at discovery/seed time (true for
  // Global-market artists, false for India-market artists) — no separate
  // "market" field needed on the frontend.
  const indiaCount = entities.filter(e => !e.is_international).length;
  const globalCount = entities.filter(e => e.is_international).length;

  const filtered = entities.filter(e => {
    const matchQ = !query || e.name.toLowerCase().includes(query.toLowerCase()) ||
                   (e.category ?? '').toLowerCase().includes(query.toLowerCase());
    const matchT = typeFilter === 'All' || e.type === typeFilter;
    const matchM = marketFilter === 'All' ||
                   (marketFilter === 'India' && !e.is_international) ||
                   (marketFilter === 'Global' && e.is_international);
    return matchQ && matchT && matchM;
  });

  return (
    <div className={styles.page}>
      <Topbar title="Intelligence Hub" subtitle="Artist scoring, deal recommendation, signing intelligence" />

      <div className={styles.layout}>
        {/* ── Left: list ── */}
        <div className={styles.listPane}>

          {/* Stats bar */}
          <motion.div
            className={styles.statsBar}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            {[
              { label: 'Total tracked', value: portfolio?.total ?? '—' },
              { label: 'With metrics', value: portfolio?.with_scores ?? '—' },
              { label: 'Sign-ready', value: portfolio?.health_summary?.strong ?? '—' },
              { label: 'Needs data', value: portfolio?.health_summary?.needs_data ?? '—' },
            ].map(({ label, value }, i) => (
              <div key={label} className={styles.statChip}>
                <span className="t-title2 text-primary" style={{ fontWeight: 800, letterSpacing: '-0.04em' }}>{value}</span>
                <span className="t-caption text-tertiary">{label}</span>
              </div>
            ))}
          </motion.div>

          {/* Market tabs — India (deep coverage) vs Global (broad chart) */}
          <div className={styles.filterRow} style={{ marginBottom: 4 }}>
            {MARKETS.map(m => (
              <button
                key={m}
                className={`${styles.filterChip} ${marketFilter === m ? styles.filterActive : ''}`}
                onClick={() => setMarketFilter(m)}
              >
                {m}
                {m === 'India' && ` (${indiaCount})`}
                {m === 'Global' && ` (${globalCount})`}
              </button>
            ))}
          </div>

          {/* Search + filter */}
          <GlassCard className={styles.searchCard} delay={0.06}>
            <div className={styles.searchRow}>
              <div className={styles.searchWrap}>
                <Search size={14} className={styles.searchIcon} />
                <input
                  className={`input ${styles.searchInput}`}
                  placeholder="Search artists, acts, films..."
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                />
              </div>
              <div className={styles.filterRow}>
                {TYPES.map(t => (
                  <button
                    key={t}
                    className={`${styles.filterChip} ${typeFilter === t ? styles.filterActive : ''}`}
                    onClick={() => setTypeFilter(t)}
                  >
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </GlassCard>

          {/* Entity table */}
          <GlassCard className={styles.tableCard} delay={0.1}>
            {/* Header */}
            <div className={styles.tableHeader}>
              <span className="t-label text-tertiary" style={{ flex: 3 }}>Name</span>
              <span className="t-label text-tertiary" style={{ flex: 2 }}>Category</span>
              <span className="t-label text-tertiary" style={{ width: 80, textAlign: 'right' }}>Score</span>
              <span className="t-label text-tertiary" style={{ width: 90, textAlign: 'center' }}>Signal</span>
              <span className="t-label text-tertiary" style={{ width: 110, textAlign: 'center' }}>Verdict</span>
            </div>

            {isLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="skeleton" style={{ height: 48, borderRadius: 10 }} />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center' }}>
                <p className="t-callout text-tertiary">
                  {entities.length === 0
                    ? 'No entities found. Ensure the backend is running and the NeonDB is seeded.'
                    : 'No matches for your search.'}
                </p>
              </div>
            ) : (
              <div className={styles.tableBody}>
                <AnimatePresence>
                  {filtered.map((e, i) => {
                    const rec = scoreLabel(e.composite_score);
                    const isSelected = selected?.id === e.id;
                    return (
                      <motion.div
                        key={e.id}
                        className={`${styles.tableRow} ${isSelected ? styles.tableRowActive : ''}`}
                        onClick={() => setSelected(isSelected ? null : e)}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.03, duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
                        layout
                      >
                        <div style={{ flex: 3, display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                          <div className={styles.rowAvatar}>{e.name.charAt(0).toUpperCase()}</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                            <span className="t-callout text-primary" style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 5 }}>
                              {watchedIds.has(e.id) && <Star size={12} fill="var(--warning)" color="var(--warning)" />}
                              {e.name}
                            </span>
                            <span className="t-caption text-tertiary">{e.country}{e.is_international ? ' · International' : ''}</span>
                          </div>
                        </div>
                        <div style={{ flex: 2 }}>
                          <span className="t-footnote text-secondary">{e.category ?? e.type}</span>
                        </div>
                        <div style={{ width: 80, textAlign: 'right' }}>
                          <span style={{ fontSize: '1.1rem', fontWeight: 700, letterSpacing: '-0.03em', color: scoreColor(e.composite_score) }}>
                            {e.composite_score ?? '—'}
                          </span>
                        </div>
                        <div style={{ width: 90, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 4 }}>
                          {e.google_trend_score != null ? (
                            e.google_trend_score > (e.composite_score ?? 0) ? (
                              <span style={{ color: 'var(--positive)', display: 'flex', alignItems: 'center', gap: 3, fontSize: '0.75rem', fontWeight: 600 }}>
                                <ArrowUpRight size={12} /> Trending
                              </span>
                            ) : (
                              <span style={{ color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 3, fontSize: '0.75rem' }}>
                                <ArrowDownRight size={12} /> Stable
                              </span>
                            )
                          ) : (
                            <span className="t-caption text-tertiary">No data</span>
                          )}
                        </div>
                        <div style={{ width: 110, display: 'flex', justifyContent: 'center' }}>
                          <span className={styles.verdict} style={{ color: rec.color, background: rec.color + '18', borderColor: rec.color + '30' }}>
                            {rec.icon} {rec.label}
                          </span>
                        </div>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            )}
          </GlassCard>
        </div>

        {/* ── Right: detail panel ── */}
        <div className={styles.panelPane}>
          <AnimatePresence mode="wait">
            {selected ? (
              <EntityPanel
                key={selected.id}
                entity={selected}
                onClose={() => setSelected(null)}
                isWatched={watchedIds.has(selected.id)}
                onToggleWatch={() => handleToggleWatch(selected.id)}
              />
            ) : (
              <motion.div
                key="empty"
                className={styles.panelEmpty}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                <Brain size={40} color="var(--text-tertiary)" strokeWidth={1.5} />
                <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Select an entity</p>
                <p className="t-callout text-tertiary" style={{ maxWidth: 220, textAlign: 'center', lineHeight: 1.6, marginTop: 6 }}>
                  Click any row to view the full signing intelligence report — scores, signals, and AI recommendation.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
