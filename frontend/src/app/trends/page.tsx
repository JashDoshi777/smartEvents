'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell
} from 'recharts';
import {
  TrendingUp, ArrowUpRight, ArrowDownRight, Flame,
  Music2, Film, Users, Star, Info
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getDashboardAlerts, PortfolioEntity } from '@/lib/api';
import styles from './page.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreColor(s: number | null) {
  if (!s) return 'var(--text-tertiary)';
  if (s >= 70) return 'var(--positive)';
  if (s >= 45) return 'var(--accent)';
  return 'var(--warning)';
}

// ── Category icon ─────────────────────────────────────────────────────────────
function CatIcon({ cat }: { cat: string | null }) {
  if (!cat) return <Star size={13} />;
  const c = cat.toLowerCase();
  if (c.includes('bollywood') || c.includes('music') || c.includes('pop') || c.includes('rap'))
    return <Music2 size={13} />;
  if (c.includes('film') || c.includes('movie')) return <Film size={13} />;
  if (c.includes('sport')) return <Users size={13} />;
  return <Star size={13} />;
}

// ── Breakout card ─────────────────────────────────────────────────────────────
function BreakoutCard({ e, delay }: { e: PortfolioEntity; delay: number }) {
  // Direction derived from real signal: google_trend leading composite means
  // search demand is outpacing the current score — a genuine rising signal.
  const composite = e.composite_score ?? 0;
  const trend = e.google_trend_score ?? composite;
  const gap = Math.round(trend - composite);
  const rising = gap > 0;

  return (
    <motion.div
      className={styles.breakoutCard}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <div className={styles.breakoutHead}>
        <div className={styles.breakoutAvatar}>
          <CatIcon cat={e.category} />
        </div>
        <div className={styles.breakoutInfo}>
          <span className="t-callout text-primary" style={{ fontWeight: 700 }}>{e.name}</span>
          <span className="t-caption text-tertiary">{e.category ?? e.type} · {e.country}</span>
        </div>
        <div className={styles.breakoutScore}>
          <span style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.04em', color: scoreColor(e.composite_score) }}>
            {e.composite_score ?? '—'}
          </span>
          <div className={styles.breakoutTrend} style={{ color: rising ? 'var(--positive)' : 'var(--text-tertiary)' }}>
            {rising ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
            <span style={{ fontSize: '0.7rem', fontWeight: 700 }}>
              {gap > 0 ? `+${gap}` : `${gap}`} vs trend
            </span>
          </div>
        </div>
      </div>

      <div className={styles.breakoutSignals}>
        {e.google_trend_score != null && (
          <span className={styles.signalChip}>
            <TrendingUp size={10} /> G-Trend: {e.google_trend_score}
          </span>
        )}
        {e.news_mentions_7d != null && e.news_mentions_7d > 0 && (
          <span className={styles.signalChip}>
            <Flame size={10} /> {e.news_mentions_7d} news
          </span>
        )}
        {e.is_international && (
          <span className={styles.signalChip} style={{ color: 'var(--accent)', borderColor: 'rgba(10,132,255,0.3)', background: 'var(--accent-dim)' }}>
            Intl. act
          </span>
        )}
      </div>
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Trend Radar Page
// ═══════════════════════════════════════════════════════════════════════════════

const FILTERS = ['All', 'Breakout', 'Rising', 'Stable', 'International'];

export default function TrendsPage() {
  const [filter, setFilter] = useState('All');

  const { data: portfolio, isLoading } = useSWR(
    'portfolio/trends', () => getPortfolio(),
    { refreshInterval: 120000, shouldRetryOnError: false }
  );
  const { data: alertsData } = useSWR(
    'dashboard/alerts', getDashboardAlerts,
    { refreshInterval: 120000, shouldRetryOnError: false }
  );

  const all = portfolio?.portfolio ?? [];
  const alerts = alertsData?.alerts ?? [];

  // Score distribution for bar chart
  const distribution = [
    { range: '0–20',  count: all.filter(e => (e.composite_score ?? 0) <= 20).length },
    { range: '21–40', count: all.filter(e => { const s = e.composite_score ?? 0; return s > 20 && s <= 40; }).length },
    { range: '41–60', count: all.filter(e => { const s = e.composite_score ?? 0; return s > 40 && s <= 60; }).length },
    { range: '61–80', count: all.filter(e => { const s = e.composite_score ?? 0; return s > 60 && s <= 80; }).length },
    { range: '81–100',count: all.filter(e => (e.composite_score ?? 0) > 80).length },
  ];

  const distColors = ['var(--negative)', 'var(--warning)', 'var(--accent)', 'var(--positive)', 'var(--positive)'];

  // Filtered entities
  const filtered = all
    .filter(e => e.composite_score !== null)
    .filter(e => {
      if (filter === 'All') return true;
      if (filter === 'Breakout') return (e.google_trend_score ?? 0) > (e.composite_score ?? 0) + 10;
      if (filter === 'Rising')   return (e.google_trend_score ?? 0) > (e.composite_score ?? 0);
      if (filter === 'Stable')   return Math.abs((e.google_trend_score ?? 0) - (e.composite_score ?? 0)) <= 10;
      if (filter === 'International') return e.is_international;
      return true;
    })
    .sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0))
    .slice(0, 12);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Trend Radar" subtitle="Breakout detection, momentum signals, and score distribution" />

      <div className={styles.page}>

        {/* ── Summary row ── */}
        <div className={styles.summaryRow}>
          {[
            {
              label: 'Total tracked',
              value: all.length || '—',
              sub: 'entities in portfolio',
            },
            {
              label: 'With scores',
              value: portfolio?.with_scores ?? '—',
              sub: 'have live metrics',
            },
            {
              label: 'Breakout signals',
              value: all.filter(e => (e.google_trend_score ?? 0) > (e.composite_score ?? 0) + 10).length || '—',
              sub: 'trend > composite by 10+',
              accent: true,
            },
            {
              label: 'High performers',
              value: portfolio?.health_summary?.strong ?? '—',
              sub: 'score ≥ 70 ("Sign Now")',
            },
          ].map(({ label, value, sub, accent }, i) => (
            <motion.div
              key={label}
              className={`glass-card ${styles.summaryCard} ${accent ? styles.summaryAccent : ''}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05, duration: 0.35 }}
            >
              <span className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem' }}>{label}</span>
              <span style={{ fontSize: '2.2rem', fontWeight: 800, letterSpacing: '-0.05em', color: accent ? 'var(--positive)' : 'var(--text-primary)', lineHeight: 1 }}>
                {value}
              </span>
              <span className="t-caption text-tertiary">{sub}</span>
            </motion.div>
          ))}
        </div>

        <div className={styles.mainGrid}>
          {/* Score distribution chart */}
          <GlassCard className={styles.distCard} delay={0.1}>
            <h2 className="t-headline text-primary" style={{ marginBottom: 4 }}>Score Distribution</h2>
            <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>
              How many entities fall in each score bracket
            </p>
            {isLoading ? (
              <div className="skeleton" style={{ height: 160, borderRadius: 10 }} />
            ) : (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={distribution} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barSize={32}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--divider)" vertical={false} />
                  <XAxis dataKey="range" tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 12 }}
                    cursor={{ fill: 'var(--glass-fill)' }}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {distribution.map((_, i) => (
                      <Cell key={i} fill={distColors[i]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </GlassCard>

          {/* Live alerts from backend */}
          <GlassCard className={styles.alertsCard} delay={0.14}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Flame size={15} color="var(--negative)" />
              <h2 className="t-headline text-primary">Live Signal Alerts</h2>
            </div>
            {alerts.length === 0 ? (
              <div className={styles.emptyState}>
                <Info size={20} color="var(--text-tertiary)" strokeWidth={1.5} />
                <p className="t-callout text-tertiary" style={{ marginTop: 10 }}>
                  No signals yet. Run the entity metrics worker to detect breakouts.
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {alerts.map((a, i) => (
                  <motion.div
                    key={i}
                    className={styles.alertRow}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.18 + i * 0.05 }}
                  >
                    <div className={styles.alertDot} style={{
                      background: a.type === 'breakout' ? 'var(--positive)'
                        : a.type === 'buzz' ? 'var(--accent)' : 'var(--warning)',
                    }} />
                    <div style={{ flex: 1 }}>
                      <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{a.title}</p>
                      <p className="t-caption text-tertiary">{a.message}</p>
                    </div>
                    <span className={styles.alertSeverity} style={{
                      color: a.severity === 'high' ? 'var(--negative)' : a.severity === 'medium' ? 'var(--accent)' : 'var(--text-tertiary)',
                    }}>{a.severity}</span>
                  </motion.div>
                ))}
              </div>
            )}
          </GlassCard>
        </div>

        {/* Filter bar */}
        <GlassCard className={styles.filterCard} delay={0.18}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 className="t-headline text-primary">Momentum Heatmap</h2>
            <div style={{ display: 'flex', gap: 6 }}>
              {FILTERS.map(f => (
                <button
                  key={f}
                  className={`${styles.filterChip} ${filter === f ? styles.filterActive : ''}`}
                  onClick={() => setFilter(f)}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
        </GlassCard>

        {/* Entity breakout cards grid */}
        {isLoading ? (
          <div className={styles.cardsGrid}>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton" style={{ height: 160, borderRadius: 16 }} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <GlassCard style={{ padding: 40, textAlign: 'center' }} delay={0.2}>
            <p className="t-callout text-tertiary">
              No entities match this filter, or no entity metrics have been collected yet.
            </p>
          </GlassCard>
        ) : (
          <div className={styles.cardsGrid}>
            {filtered.map((e, i) => (
              <BreakoutCard key={e.id} e={e} delay={0.2 + i * 0.04} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
