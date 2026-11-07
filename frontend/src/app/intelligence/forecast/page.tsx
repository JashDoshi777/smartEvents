'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import {
  LineChart, Line, ResponsiveContainer, Tooltip, CartesianGrid, XAxis, YAxis, Area, ComposedChart,
} from 'recharts';
import {
  LineChart as LineChartIcon, ChevronDown, AlertCircle, Info, TrendingUp, TrendingDown, Minus,
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getDemandForecast, DemandForecastResponse } from '@/lib/api';
import styles from './page.module.css';

const MARKETS = ['All', 'India', 'Global'] as const;
type MarketFilter = typeof MARKETS[number];

function trendColor(direction?: string) {
  if (direction === 'rising') return 'var(--positive)';
  if (direction === 'falling') return 'var(--negative)';
  return 'var(--text-tertiary)';
}

function TrendIcon({ direction }: { direction?: string }) {
  if (direction === 'rising') return <TrendingUp size={15} />;
  if (direction === 'falling') return <TrendingDown size={15} />;
  return <Minus size={15} />;
}

export default function DemandForecastPage() {
  const [entityId, setEntityId] = useState('');
  const [months, setMonths] = useState('3');
  const [market, setMarket] = useState<MarketFilter>('All');
  const [result, setResult] = useState<DemandForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: portfolio } = useSWR('portfolio/forecast', () => getPortfolio(), { shouldRetryOnError: false });

  const allEntities = portfolio?.portfolio ?? [];
  const indiaCount = allEntities.filter(e => !e.is_international).length;
  const globalCount = allEntities.filter(e => e.is_international).length;
  const entities = allEntities.filter(e => {
    if (market === 'India') return !e.is_international;
    if (market === 'Global') return e.is_international;
    return true;
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!entityId) {
      setError('Select an artist to forecast.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await getDemandForecast(entityId, { months: Number(months) || 3 });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch forecast. Ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }

  // Merge history + forecast into one chart series, keyed on a numeric
  // timestamp (not the date string) so the x-axis reflects true elapsed
  // calendar time. History points are collected every few days while the
  // forecast is daily — a category axis would space both by point COUNT,
  // visually crushing the sparser-but-longer-spanning history segment.
  const chartData = result ? [
    ...result.history.map(h => ({ ts: new Date(h.date).getTime(), date: h.date, actual: h.google_trend_score, predicted: null, lower: null, upper: null })),
    ...(result.forecast ?? []).map(f => ({
      ts: new Date(f.date).getTime(), date: f.date, actual: null, predicted: f.predicted_trend_score, lower: f.lower_bound, upper: f.upper_bound,
    })),
  ].sort((a, b) => a.ts - b.ts) : [];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Demand Forecast" subtitle="Prophet-based projection of Google Trends interest, built from real tracked history" />

      <div className={styles.page}>
        <GlassCard className={styles.formCard} delay={0.04}>
          <div className={styles.formHeader}>
            <LineChartIcon size={18} color="var(--accent)" />
            <div>
              <h2 className="t-headline text-primary">Configure the Forecast</h2>
              <p className="t-footnote text-tertiary">Requires at least 10 tracked data points spanning 21+ days — entities with less history will show what's missing instead of a fabricated forecast</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className={styles.form}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {MARKETS.map(m => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setMarket(m); setEntityId(''); }}
                  style={{
                    padding: '4px 12px', borderRadius: 999, fontSize: '0.75rem', fontWeight: 500,
                    background: market === m ? 'var(--accent-dim)' : 'var(--glass-fill)',
                    border: `1px solid ${market === m ? 'var(--accent)' : 'var(--glass-border)'}`,
                    color: market === m ? 'var(--accent)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  {m}
                  {m === 'India' && ` (${indiaCount})`}
                  {m === 'Global' && ` (${globalCount})`}
                </button>
              ))}
            </div>

            <div className={styles.formGrid}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="forecast-entity">Artist / Act</label>
                <div className={styles.selectWrap}>
                  <select id="forecast-entity" className={`input ${styles.select}`} value={entityId} onChange={e => setEntityId(e.target.value)} required>
                    <option value="">Select artist...</option>
                    {entities.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="forecast-months">Months Ahead</label>
                <div className={styles.selectWrap}>
                  <select id="forecast-months" className={`input ${styles.select}`} value={months} onChange={e => setMonths(e.target.value)}>
                    {[1, 2, 3, 6, 12].map(m => <option key={m} value={m}>{m} month{m > 1 ? 's' : ''}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>
            </div>

            {error && (
              <div className={styles.errorBox}>
                <AlertCircle size={16} color="var(--negative)" />
                <span className="t-callout" style={{ color: 'var(--negative)' }}>{error}</span>
              </div>
            )}

            <button type="submit" className="btn btn-primary" disabled={loading} style={{ alignSelf: 'flex-start' }}>
              {loading ? 'Forecasting...' : 'Run Forecast'}
            </button>
          </form>
        </GlassCard>

        {result && result.status === 'insufficient_history' && (
          <GlassCard className={styles.insufficientBox} delay={0.05}>
            <Info size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-primary">Not enough history yet for {result.entity.name}</p>
            <p className="t-callout text-tertiary" style={{ maxWidth: 480 }}>{result.message}</p>
            <p className="t-caption text-tertiary">
              {result.history_points} point(s) tracked · {result.history_span_days} day(s) span · needs {result.minimum_required?.points}+ points across {result.minimum_required?.span_days}+ days
            </p>
          </GlassCard>
        )}

        {result && result.status === 'ok' && (
          <motion.div className={styles.resultWrap} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <GlassCard className={styles.heroCard} delay={0}>
              <div className={styles.heroTop}>
                <div>
                  <p className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem', marginBottom: 6 }}>
                    {result.entity.name} · {result.history_points} real data points · {result.history_span_days} days of history
                  </p>
                  <h2 className="t-title2 text-primary" style={{ fontWeight: 800 }}>
                    Google Trends interest is {result.trend_direction}
                  </h2>
                </div>
                <div className={styles.trendBadge} style={{
                  color: trendColor(result.trend_direction),
                  borderColor: trendColor(result.trend_direction) + '50',
                  background: trendColor(result.trend_direction) + '18',
                }}>
                  <TrendIcon direction={result.trend_direction} />
                  {result.trend_direction}
                </div>
              </div>
            </GlassCard>

            <GlassCard className={styles.chartCard} delay={0.05}>
              <h3 className="t-headline text-primary" style={{ marginBottom: 4 }}>Trend Score — History &amp; Forecast</h3>
              <p className="t-footnote text-tertiary" style={{ marginBottom: 14 }}>Solid line is real tracked data; dashed region is the Prophet projection with an 80% confidence band</p>
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="forecastBand" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.18} />
                      <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--divider)" vertical={false} />
                  <XAxis
                    dataKey="ts"
                    type="number"
                    scale="time"
                    domain={['dataMin', 'dataMax']}
                    tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                    axisLine={false} tickLine={false} minTickGap={60}
                    tickFormatter={(ts: number) => new Date(ts).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
                  />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 11 }}
                    labelFormatter={(ts: React.ReactNode) => new Date(Number(ts)).toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' })}
                  />
                  <Area type="monotone" dataKey="upper" stroke="none" fill="url(#forecastBand)" isAnimationActive={false} />
                  <Area type="monotone" dataKey="lower" stroke="none" fill="var(--bg-base)" isAnimationActive={false} />
                  <Line type="monotone" dataKey="actual" stroke="var(--text-primary)" strokeWidth={2} dot={false} connectNulls={false} />
                  <Line type="monotone" dataKey="predicted" stroke="var(--accent)" strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </GlassCard>

            <GlassCard style={{ padding: 18 }} delay={0.1}>
              <div className={styles.noteBox}>
                <Info size={15} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: 1 }} />
                <p className="t-caption text-tertiary" style={{ lineHeight: 1.6 }}>{result.methodology}</p>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {!result && !loading && (
          <GlassCard className={styles.placeholder} delay={0.1}>
            <LineChartIcon size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Select an artist above to see their demand forecast</p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
