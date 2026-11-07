'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { TrendingUp, TrendingDown, Flame, Radar, Newspaper, Search } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton } from '@/components/ui/Skeleton';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { ScoreRing } from '@/components/intel/ScoreRing';
import { initials, scoreColor, typeLabel, useScopedPortfolio } from '@/components/intel/entity-utils';
import { getTrendBreakouts, getTrendViral, BreakoutPrediction } from '@/lib/api';
import { compact, num, timeAgo } from '@/lib/format';
import styles from './page.module.css';

type SortKey = 'score' | 'search' | 'news' | 'listeners';
const SORTS: { value: SortKey; label: string }[] = [
  { value: 'score', label: 'Score' }, { value: 'search', label: 'Search' }, { value: 'news', label: 'News' }, { value: 'listeners', label: 'Listeners' },
];
const metricOf = (p: BreakoutPrediction, k: SortKey): number | null =>
  k === 'score' ? p.composite_score : k === 'search' ? p.google_trend_score : k === 'news' ? p.news_mentions_7d : (p.lastfm_listeners ?? null);
const fmtMetric = (v: number | null, k: SortKey) => (v == null ? '—' : k === 'score' ? v.toFixed(1) : k === 'search' ? String(Math.round(v)) : compact(v));

export default function TrendsPage() {
  const { scope, isIndia } = useMarketScope();
  const [sort, setSort] = useState<SortKey>('score');
  const [showAll, setShowAll] = useState(false);

  const br = useSWR(['trends/breakout', scope], () => getTrendBreakouts(scope, 50));
  const vi = useSWR(['trends/viral', scope], () => getTrendViral(scope, 8));
  const { scoped, isLoading: pLoading } = useScopedPortfolio();

  const preds = useMemo(() => br.data?.predictions ?? [], [br.data]);
  const ranked = useMemo(() => [...preds].filter(p => metricOf(p, sort) != null).sort((a, b) => (metricOf(b, sort) ?? 0) - (metricOf(a, sort) ?? 0)), [preds, sort]);
  const rows = showAll ? ranked : ranked.slice(0, 12);
  const max = Math.max(1, ...ranked.map(p => metricOf(p, sort) ?? 0));

  const scores = scoped.map(e => e.composite_score).filter((x): x is number => x != null);
  const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const rising = preds.filter(p => p.trend_direction === 'rising').length;
  const falling = preds.filter(p => p.trend_direction === 'falling').length;
  const dist = useMemo(() => {
    const b = [0, 0, 0, 0, 0];
    scoped.forEach(e => { if (e.composite_score != null) b[Math.min(4, Math.floor(e.composite_score / 20))]++; });
    return ['0–20', '20–40', '40–60', '60–80', '80–100'].map((range, i) => ({ range, count: b[i] }));
  }, [scoped]);
  const distColors = ['var(--fill-tertiary)', 'var(--divider-strong)', 'var(--c1)', 'var(--c1)', 'var(--c1)'];

  const heat = useMemo(() => [...preds].filter(p => p.google_trend_score != null).sort((a, b) => (b.google_trend_score ?? 0) - (a.google_trend_score ?? 0)).slice(0, 5), [preds]);
  const buzz = (vi.data?.signals ?? []).filter(s => (s.news_mentions_7d ?? 0) > 0).slice(0, 5);
  const maxBuzz = Math.max(1, ...buzz.map(s => s.news_mentions_7d ?? 0));
  const loading = br.isLoading && !br.data;
  const lastUpdated = preds.find(p => p.last_updated)?.last_updated ?? null;

  return (
    <Page title="Trend Radar" subtitle={`${isIndia ? 'India' : 'Global'}${lastUpdated ? ` · data from ${timeAgo(lastUpdated)}` : ''}`}>
      {br.error && !br.data ? (
        <GlassCard><ErrorState message="Couldn’t load trend data." onRetry={() => br.mutate()} /></GlassCard>
      ) : (
        <div className={styles.bento}>
          <GlassCard className={`${styles.tile} ${styles.hero}`} delay={0.02}>
            <div>
              <p className={styles.eyebrow}>{isIndia ? 'India' : 'Global'} scene temperature</p>
              <div className={styles.heroRow} style={{ marginTop: 14 }}>
                <span className={`${styles.num} ${styles.giant}`} style={{ color: 'var(--text-primary)' }}>{loading || pLoading && avg == null ? '…' : avg != null ? avg.toFixed(0) : '—'}</span>
                <ScoreRing score={avg} size={84} stroke={9} label={false} />
              </div>
              <p className="t-footnote text-secondary" style={{ marginTop: 10 }}>Average composite score across {num(scores.length)} scored {isIndia ? 'Indian' : 'global'} entities.</p>
            </div>
            <div className={styles.stats}>
              <div className={styles.stat}><b className={styles.num}>{loading ? '…' : num(br.data?.total ?? 0)}</b><span className="t-caption text-tertiary">in radar</span></div>
              <div className={styles.stat}><b className={styles.num} style={{ color: rising ? 'var(--positive)' : undefined }}>{loading ? '…' : rising}</b><span className="t-caption text-tertiary"><TrendingUp size={11} className={styles.arrow} /> rising</span></div>
              <div className={styles.stat}><b className={styles.num} style={{ color: falling ? 'var(--negative)' : undefined }}>{loading ? '…' : falling}</b><span className="t-caption text-tertiary"><TrendingDown size={11} className={styles.arrow} /> falling</span></div>
            </div>
          </GlassCard>

          <GlassCard className={`${styles.tile} ${styles.dist}`} delay={0.06}>
            <p className={styles.eyebrow}>Score distribution</p>
            <p className="t-footnote text-secondary" style={{ marginTop: 4 }}>How many entities sit in each score bracket</p>
            {pLoading && !scoped.length ? <Skeleton height={190} radius={14} style={{ marginTop: 14 }} /> : (
              <div className={styles.chart}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dist} margin={{ top: 8, right: 4, left: -22, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 4" stroke="var(--divider)" vertical={false} />
                    <XAxis dataKey="range" tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip cursor={{ fill: 'var(--fill-quaternary)' }} contentStyle={{ background: 'var(--glass-fill-strong)', border: '1px solid var(--glass-border)', borderRadius: 12, fontSize: 12, color: 'var(--text-primary)' }} formatter={(v) => [String(v), 'Entities']} />
                    <Bar dataKey="count" radius={[10, 10, 4, 4]} maxBarSize={44} animationDuration={800}>
                      {dist.map((_, i) => <Cell key={i} fill={distColors[i]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </GlassCard>

          <GlassCard className={`${styles.tile} ${styles.board}`} delay={0.1}>
            <div className={styles.boardHead}>
              <h2 className="t-headline">Leaderboard</h2>
              <Segmented ariaLabel="Rank by" value={sort} onChange={v => { setSort(v); setShowAll(false); }} options={SORTS} />
            </div>
            {loading ? <div style={{ display: 'grid', gap: 8, padding: '0 22px 22px' }}>{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} height={52} radius={12} />)}</div>
              : rows.length === 0 ? <EmptyState icon={<Radar size={34} strokeWidth={1.4} />} title="No data for this ranking" message="Try another metric, or switch market from the toggle above." />
              : (
                <>
                  {rows.map((p, i) => {
                    const v = metricOf(p, sort);
                    return (
                      <motion.div key={p.entity_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} whileTap={{ scale: 0.99 }} transition={{ duration: 0.28, delay: Math.min(i, 10) * 0.025 }}>
                        <Link className={styles.row} href={`/intelligence?entity=${p.entity_id}`}>
                          <span className={`${styles.rank} ${styles.num}`}>{i + 1}</span>
                          <span className={styles.av}>{initials(p.name)}</span>
                          <span className={styles.main}>
                            <b>{p.name}{p.trend_direction === 'rising' && <TrendingUp size={13} color="var(--positive)" className={styles.arrow} />}{p.trend_direction === 'falling' && <TrendingDown size={13} color="var(--negative)" className={styles.arrow} />}</b>
                            <span className="t-caption text-tertiary" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.category ?? typeLabel(p.entity_type)}</span>
                          </span>
                          <span className={styles.track} style={{ width: 90, flexShrink: 0 }}><motion.i initial={{ width: 0 }} animate={{ width: `${((v ?? 0) / max) * 100}%` }} transition={{ duration: 0.6, delay: 0.05 + Math.min(i, 10) * 0.02 }} style={{ background: scoreColor(sort === 'score' ? v : 60) }} /></span>
                          <span className={styles.metric}><b className={styles.num}>{fmtMetric(v, sort)}</b></span>
                        </Link>
                      </motion.div>
                    );
                  })}
                  {ranked.length > 12 && <div className={styles.more}><button className="btn btn-tinted btn-sm" onClick={() => setShowAll(s => !s)}>{showAll ? 'Show top 12' : `Show all ${ranked.length}`}</button></div>}
                </>
              )}
          </GlassCard>

          <div className={styles.side}>
            <GlassCard className={styles.tile} delay={0.14}>
              <p className={styles.eyebrow} style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Flame size={13} /> Buzz this week</p>
              {vi.isLoading && !vi.data ? <Skeleton height={150} radius={12} style={{ marginTop: 14 }} />
                : vi.error && !vi.data ? <ErrorState message="Couldn’t load buzz signals." onRetry={() => vi.mutate()} />
                : buzz.length === 0 ? <EmptyState icon={<Newspaper size={28} strokeWidth={1.4} />} title="No buzz yet" message="No news mentions in the last 7 days." />
                : (
                  <div className={styles.bars}>
                    {buzz.map((s, i) => (
                      <Link key={s.entity_id} className={styles.bar} href={`/intelligence?entity=${s.entity_id}`}>
                        <span className={styles.barTop}><span>{s.name}</span><span className={`${styles.num} text-secondary`}>{num(s.news_mentions_7d)}</span></span>
                        <span className={styles.track}><motion.i style={{ background: 'var(--text-secondary)' }} initial={{ width: 0 }} animate={{ width: `${((s.news_mentions_7d ?? 0) / maxBuzz) * 100}%` }} transition={{ duration: 0.7, delay: 0.15 + i * 0.05, ease: [0.22, 1, 0.36, 1] }} /></span>
                      </Link>
                    ))}
                  </div>
                )}
            </GlassCard>
            <GlassCard className={styles.tile} delay={0.18}>
              <p className={styles.eyebrow} style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Search size={13} /> Search heat</p>
              {loading ? <Skeleton height={150} radius={12} style={{ marginTop: 14 }} /> : heat.length === 0 ? <p className="t-footnote text-tertiary" style={{ marginTop: 12 }}>No Google Trends data for this market yet.</p> : (
                <div className={styles.bars}>
                  {heat.map((p, i) => (
                    <Link key={p.entity_id} className={styles.bar} href={`/intelligence?entity=${p.entity_id}`}>
                      <span className={styles.barTop}><span>{p.name}</span><span className={`${styles.num} text-secondary`}>{Math.round(p.google_trend_score ?? 0)}</span></span>
                      <span className={styles.track}><motion.i style={{ background: 'var(--accent)' }} initial={{ width: 0 }} animate={{ width: `${p.google_trend_score ?? 0}%` }} transition={{ duration: 0.7, delay: 0.2 + i * 0.05, ease: [0.22, 1, 0.36, 1] }} /></span>
                    </Link>
                  ))}
                </div>
              )}
            </GlassCard>
          </div>
        </div>
      )}
    </Page>
  );
}
