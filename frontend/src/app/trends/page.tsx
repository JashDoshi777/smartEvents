'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, ChevronRight, Radar, Newspaper } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton } from '@/components/ui/Skeleton';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { Tick } from '@/components/intel/Tick';
import { initials, typeLabel, useScopedPortfolio } from '@/components/intel/entity-utils';
import { getTrendBreakouts, getTrendViral, getDashboardMovers, BreakoutPrediction } from '@/lib/api';
import { compact, num, timeAgo } from '@/lib/format';
import k from '@/components/intel/Kit.module.css';
import styles from './page.module.css';

type SortKey = 'score' | 'search' | 'news' | 'listeners';
const SORTS: { value: SortKey; label: string }[] = [
  { value: 'score', label: 'Score' }, { value: 'search', label: 'Search' }, { value: 'news', label: 'News' }, { value: 'listeners', label: 'Listeners' },
];
const metricOf = (p: BreakoutPrediction, s: SortKey): number | null =>
  s === 'score' ? p.composite_score : s === 'search' ? p.google_trend_score : s === 'news' ? p.news_mentions_7d : (p.lastfm_listeners ?? null);
const fmtMetric = (v: number | null, s: SortKey) => (v == null ? '—' : s === 'score' ? v.toFixed(1) : s === 'search' ? String(Math.round(v)) : compact(v));
const SORT_LABEL: Record<SortKey, string> = { score: 'Composite score', search: 'Search interest', news: 'News mentions, 7 days', listeners: 'Last.fm listeners' };

export default function TrendsPage() {
  const { scope, isIndia } = useMarketScope();
  const [sort, setSort] = useState<SortKey>('score');
  const [showAll, setShowAll] = useState(false);

  const br = useSWR(['trends/breakout', scope], () => getTrendBreakouts(scope, 50));
  const vi = useSWR(['trends/viral', scope], () => getTrendViral(scope, 8));
  const mv = useSWR(['trends/movers', scope], () => getDashboardMovers(scope, 5));
  const { scoped, isLoading: pLoading } = useScopedPortfolio();

  const preds = useMemo(() => br.data?.predictions ?? [], [br.data]);
  const ranked = useMemo(() => [...preds].filter(p => metricOf(p, sort) != null).sort((a, b) => (metricOf(b, sort) ?? 0) - (metricOf(a, sort) ?? 0)), [preds, sort]);
  const rows = showAll ? ranked : ranked.slice(0, 12);

  const scores = scoped.map(e => e.composite_score).filter((x): x is number => x != null);
  const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const rising = preds.filter(p => p.trend_direction === 'rising').length;
  const falling = preds.filter(p => p.trend_direction === 'falling').length;
  const dist = useMemo(() => {
    const b = [0, 0, 0, 0, 0];
    scoped.forEach(e => { if (e.composite_score != null) b[Math.min(4, Math.floor(e.composite_score / 20))]++; });
    return ['0–20', '20–40', '40–60', '60–80', '80–100'].map((range, i) => ({ range, count: b[i] }));
  }, [scoped]);

  const heat = useMemo(() => [...preds].filter(p => p.google_trend_score != null).sort((a, b) => (b.google_trend_score ?? 0) - (a.google_trend_score ?? 0)).slice(0, 5), [preds]);
  const buzz = (vi.data?.signals ?? []).filter(s => (s.news_mentions_7d ?? 0) > 0).slice(0, 5);
  const loading = br.isLoading && !br.data;
  const lastUpdated = preds.find(p => p.last_updated)?.last_updated ?? null;

  return (
    <Page title="Trend Radar" subtitle={`${isIndia ? 'India' : 'Global'}${lastUpdated ? ` · data from ${timeAgo(lastUpdated)}` : ''}`}>
      {br.error && !br.data ? (
        <GlassCard><ErrorState message="Couldn’t load trend data." onRetry={() => br.mutate()} /></GlassCard>
      ) : (
        <div className={styles.bento}>
          <GlassCard className={`${k.surface} ${styles.hero}`} delay={0.02}>
            <h2 className={k.title}>Average score</h2>
            <div className={styles.heroRow}>
              <span className={`num-rounded ${styles.giant}`}>{loading || (pLoading && avg == null) ? '…' : <Tick value={avg} decimals={1} />}</span>
            </div>
            <p className="t-footnote text-secondary" style={{ lineHeight: 1.45 }}>Across {num(scores.length)} scored {isIndia ? 'Indian' : 'global'} entities, out of 100.</p>
            <div className={styles.split}>
              <div><b className="num-rounded">{loading ? '…' : num(br.data?.total ?? 0)}</b><span className="t-caption text-tertiary">In radar</span></div>
              <div><b className="num-rounded" style={{ color: rising ? 'var(--positive)' : undefined }}>{loading ? '…' : rising}</b><span className="t-caption text-tertiary">Rising</span></div>
              <div><b className="num-rounded" style={{ color: falling ? 'var(--negative)' : undefined }}>{loading ? '…' : falling}</b><span className="t-caption text-tertiary">Falling</span></div>
            </div>
          </GlassCard>

          <GlassCard className={`${k.surface} ${styles.dist}`} delay={0.06}>
            <h2 className={k.title}>Score distribution</h2>
            <p className="t-footnote text-secondary" style={{ marginTop: 2 }}>Entities per score bracket</p>
            {pLoading && !scoped.length ? <Skeleton height={190} radius={14} style={{ marginTop: 14 }} /> : (
              <div className={styles.chart}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dist} margin={{ top: 8, right: 4, left: -24, bottom: 0 }}>
                    <CartesianGrid stroke="var(--divider)" strokeDasharray="0" vertical={false} strokeOpacity={0.5} />
                    <XAxis dataKey="range" tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip cursor={{ fill: 'var(--fill-quaternary)' }} contentStyle={{ background: 'var(--glass-fill-strong)', border: 0, borderRadius: 12, fontSize: 12, color: 'var(--text-primary)' }} formatter={(v) => [String(v), 'Entities']} />
                    <Bar dataKey="count" radius={[8, 8, 3, 3]} maxBarSize={44} fill="var(--c1)" animationDuration={800} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </GlassCard>

          <div className={styles.boardCol}>
            <div className={styles.sectionRow}>
              <span>{SORT_LABEL[sort]}</span>
              <Segmented ariaLabel="Rank by" value={sort} onChange={v => { setSort(v); setShowAll(false); }} options={SORTS} />
            </div>
            <GlassCard className={k.group} delay={0.1}>
              {loading ? <div style={{ display: 'grid', gap: 8, padding: 16 }}>{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} height={48} radius={12} />)}</div>
                : rows.length === 0 ? <EmptyState icon={<Radar size={32} strokeWidth={1.5} />} title="No data for this ranking" message="Try another metric, or switch market from the toggle above." />
                : (
                  <>
                    {rows.map((p, i) => (
                      <motion.div key={p.entity_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28, delay: Math.min(i, 10) * 0.025 }}>
                        <motion.div whileTap={{ scale: 0.99 }}>
                          <Link className={k.row} href={`/intelligence?entity=${p.entity_id}`} style={{ ['--inset' as string]: '86px' }}>
                            <span className="num-rounded" style={{ width: 20, textAlign: 'right', color: 'var(--text-tertiary)', fontSize: '.8125rem', flexShrink: 0 }}>{i + 1}</span>
                            <span className={k.avatar}>{initials(p.name)}</span>
                            <span className={k.main}>
                              <span className={k.name}>{p.name}{p.trend_direction === 'rising' && <TrendingUp size={13} strokeWidth={1.75} color="var(--positive)" />}{p.trend_direction === 'falling' && <TrendingDown size={13} strokeWidth={1.75} color="var(--negative)" />}</span>
                              <span className={k.sub}>{p.category ?? typeLabel(p.entity_type)}</span>
                            </span>
                            <span className={`${k.trail} num-rounded`} style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '1.0625rem' }}>{fmtMetric(metricOf(p, sort), sort)}</span>
                            <ChevronRight size={16} strokeWidth={1.7} className={k.chev} />
                          </Link>
                        </motion.div>
                      </motion.div>
                    ))}
                    {ranked.length > 12 && <div className={styles.more}><button className="btn btn-ghost btn-sm" style={{ color: 'var(--accent)' }} onClick={() => setShowAll(s => !s)}>{showAll ? 'Show top 12' : `Show all ${ranked.length}`}</button></div>}
                  </>
                )}
            </GlassCard>
          </div>

          <div className={styles.side}>
            <div>
              <div className={styles.sectionRow}><span>Biggest movers</span><span>Vs previous snapshot</span></div>
              <GlassCard className={k.group} delay={0.12}>
                {mv.isLoading && !mv.data ? <div style={{ padding: 16 }}><Skeleton height={150} radius={12} /></div>
                  : mv.error && !mv.data ? <ErrorState message="Couldn’t load movers." onRetry={() => mv.mutate()} />
                  : (mv.data?.risers.length ?? 0) + (mv.data?.fallers.length ?? 0) === 0 ? <p className="t-footnote text-tertiary" style={{ padding: 20 }}>No score changes between the last two snapshots.</p>
                  : [...(mv.data?.risers ?? []).slice(0, 3), ...(mv.data?.fallers ?? []).slice(0, 3)].map(m => (
                    <Link key={m.id} className={k.row} href={`/intelligence?entity=${m.id}`} style={{ ['--inset' as string]: '20px', minHeight: 48 }}>
                      <span className={k.main}><span className={k.name}>{m.name}</span><span className={k.sub}>{m.previous_score.toFixed(1)} to {m.score.toFixed(1)}</span></span>
                      <span className={`${k.trail} num-rounded`} style={{ color: m.delta > 0 ? 'var(--positive)' : 'var(--negative)', fontWeight: 600 }}>{m.delta > 0 ? '+' : ''}{m.delta.toFixed(1)}</span>
                      <ChevronRight size={16} strokeWidth={1.7} className={k.chev} />
                    </Link>
                  ))}
              </GlassCard>
            </div>
            <div>
              <div className={styles.sectionRow}><span>Buzz this week</span><span>News mentions</span></div>
              <GlassCard className={k.group} delay={0.14}>
                {vi.isLoading && !vi.data ? <div style={{ padding: 16 }}><Skeleton height={150} radius={12} /></div>
                  : vi.error && !vi.data ? <ErrorState message="Couldn’t load buzz signals." onRetry={() => vi.mutate()} />
                  : buzz.length === 0 ? <EmptyState icon={<Newspaper size={28} strokeWidth={1.5} />} title="No buzz yet" message="No news mentions in the last 7 days." />
                  : buzz.map(s => (
                    <Link key={s.entity_id} className={k.row} href={`/intelligence?entity=${s.entity_id}`} style={{ ['--inset' as string]: '20px', minHeight: 48 }}>
                      <span className={k.main}><span className={k.name}>{s.name}</span></span>
                      <span className={`${k.trail} num-rounded`} style={{ color: 'var(--text-primary)' }}>{num(s.news_mentions_7d)}</span>
                      <ChevronRight size={16} strokeWidth={1.7} className={k.chev} />
                    </Link>
                  ))}
              </GlassCard>
            </div>
            <div>
              <div className={styles.sectionRow}><span>Search interest</span><span>Google Trends, 0–100</span></div>
              <GlassCard className={k.group} delay={0.18}>
                {loading ? <div style={{ padding: 16 }}><Skeleton height={150} radius={12} /></div> : heat.length === 0 ? <p className="t-footnote text-tertiary" style={{ padding: 20 }}>No Google Trends data for this market yet.</p> : heat.map(p => (
                  <Link key={p.entity_id} className={k.row} href={`/intelligence?entity=${p.entity_id}`} style={{ ['--inset' as string]: '20px', minHeight: 48 }}>
                    <span className={k.main}><span className={k.name}>{p.name}</span></span>
                    <span className={`${k.trail} num-rounded`} style={{ color: 'var(--text-primary)' }}>{Math.round(p.google_trend_score ?? 0)}</span>
                    <ChevronRight size={16} strokeWidth={1.7} className={k.chev} />
                  </Link>
                ))}
              </GlassCard>
            </div>
          </div>
        </div>
      )}
    </Page>
  );
}
