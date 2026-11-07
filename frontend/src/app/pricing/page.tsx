'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AreaChart, Area, ResponsiveContainer, Tooltip, CartesianGrid, XAxis, YAxis,
  ReferenceLine
} from 'recharts';
import {
  IndianRupee, TrendingUp, MapPin, Users, Zap,
  CheckCircle, AlertCircle, Info, ChevronDown
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { optimizePrice, getPortfolio, getCities, PricingResponse } from '@/lib/api';
import styles from './page.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number) {
  return `₹${n.toLocaleString('en-IN')}`;
}

// ── Recommendation card ───────────────────────────────────────────────────────

function RecommendationCard({ data }: { data: PricingResponse }) {
  const rec   = data.recommendation;
  const sigs  = data.signals ?? {};
  const bench = data.benchmarks ?? {};

  const isGood = rec?.recommended_price && rec?.recommended_price > 0;
  const diff   = rec?.proposed_price && rec?.recommended_price
    ? rec.recommended_price - rec.proposed_price
    : null;

  // Sensitivity curve only exists when the ML pricing engine ran (model: "ml_gbr").
  // The rule-based fallback path returns an empty curve — show nothing rather
  // than fabricate one.
  const sensitivity = rec?.sensitivity_curve ?? [];

  return (
    <motion.div
      className={styles.recWrap}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {/* Hero recommendation */}
      <GlassCard className={styles.recHero} delay={0}>
        <div className={styles.recTop}>
          <div>
            <p className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.6875rem', marginBottom: 6 }}>
              AI Recommended Price
            </p>
            <div className={styles.recPrice}>
              <span className={styles.priceNum}>
                {isGood ? fmt(rec.recommended_price) : '—'}
              </span>
              {diff !== null && (
                <span className={styles.priceDiff} style={{ color: diff > 0 ? 'var(--positive)' : diff < 0 ? 'var(--negative)' : 'var(--text-tertiary)' }}>
                  {diff > 0 ? '+' : ''}{fmt(Math.abs(diff))} vs your price
                </span>
              )}
            </div>
          </div>
          <div className={styles.recBadge} style={{
            background: rec?.confidence_level === 'High' ? 'var(--positive-dim)' : 'var(--accent-dim)',
            borderColor: rec?.confidence_level === 'High' ? 'rgba(52,199,89,0.3)' : 'rgba(10,132,255,0.3)',
          }}>
            {rec?.confidence_level === 'High'
              ? <><CheckCircle size={14} color="var(--positive)" /> <span style={{ color: 'var(--positive)', fontWeight: 700 }}>High Confidence</span></>
              : <><AlertCircle size={14} color="var(--accent)" /> <span style={{ color: 'var(--accent)', fontWeight: 700 }}>Medium Confidence</span></>
            }
          </div>
        </div>

        {/* Key metrics */}
        <div className={styles.recMetrics}>
          {[
            { label: 'Demand Score', value: sigs?.demand_score != null ? `${sigs.demand_score}/100` : '—' },
            { label: 'City Multiplier', value: sigs?.city_multiplier != null ? `${sigs.city_multiplier}×` : '—' },
            { label: 'Season Factor', value: sigs?.season_factor != null ? `${sigs.season_factor}×` : '—' },
            { label: 'Expected Fill', value: rec?.expected_fill_pct != null ? `${rec.expected_fill_pct}%` : '—' },
          ].map(({ label, value }) => (
            <div key={label} className={styles.recMetricBox}>
              <span className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem' }}>{label}</span>
              <span className="t-title2 text-primary" style={{ fontWeight: 800, letterSpacing: '-0.04em' }}>{value}</span>
            </div>
          ))}
        </div>

        {/* AI reasoning */}
        {rec?.reasoning && (
          <div className={styles.reasoning}>
            <Zap size={13} color="var(--accent)" />
            <p className="t-callout text-secondary" style={{ lineHeight: 1.65 }}>{rec.reasoning}</p>
          </div>
        )}
      </GlassCard>

      <div className={styles.recGrid}>
        {/* Price sensitivity chart — only when the ML engine returned a real curve */}
        <GlassCard className={styles.sensitivityCard} delay={0.08}>
          <h3 className="t-headline text-primary" style={{ marginBottom: 4 }}>Price Sensitivity</h3>
          <p className="t-footnote text-tertiary" style={{ marginBottom: 14 }}>Expected attendance at each price point</p>
          {sensitivity.length > 0 ? (
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={sensitivity} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="sensGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.22} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--divider)" vertical={false} />
                <XAxis
                  dataKey="price"
                  tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                  axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `₹${(v / 1000).toFixed(1)}k`}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                  axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 11 }}
                  formatter={(v: any) => [`${v}%`, 'Attendance'] as any}
                  labelFormatter={(v: any) => fmt(Number(v))}
                />
                {rec?.recommended_price && (
                  <ReferenceLine x={rec.recommended_price} stroke="var(--accent)" strokeDasharray="4 2" strokeWidth={1.5} />
                )}
                <Area
                  type="monotone" dataKey="attendance_pct"
                  stroke="var(--accent)" strokeWidth={2}
                  fill="url(#sensGrad)" dot={false}
                  activeDot={{ r: 3, strokeWidth: 0, fill: 'var(--accent)' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 160 }}>
              <Info size={14} color="var(--text-tertiary)" />
              <span className="t-caption text-tertiary">
                Not available for this recommendation — the ML pricing model didn&apos;t run (used rule-based fallback instead).
              </span>
            </div>
          )}
        </GlassCard>
      </div>

      {/* Benchmarks */}
      {bench && Object.keys(bench).length > 0 && (
        <GlassCard className={styles.benchCard} delay={0.16}>
          <h3 className="t-headline text-primary" style={{ marginBottom: 12 }}>Market Benchmarks</h3>
          <div className={styles.benchGrid}>
            {Object.entries(bench).map(([k, v]) => (
              <div key={k} className={styles.benchItem}>
                <span className="t-footnote text-tertiary">{k.replace(/_/g, ' ')}</span>
                <span className="t-callout text-primary" style={{ fontWeight: 700 }}>{typeof v === 'number' ? fmt(v) : String(v)}</span>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </motion.div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Pricing Optimizer Page
// ═══════════════════════════════════════════════════════════════════════════════

const MARKETS = ['All', 'India', 'Global'] as const;
type MarketFilter = typeof MARKETS[number];

export default function PricingPage() {
  const [entityId,   setEntityId]   = useState('');
  const [city,       setCity]       = useState('');
  const [capacity,   setCapacity]   = useState('');
  const [price,      setPrice]      = useState('');
  const [category,   setCategory]   = useState('');
  const [market,     setMarket]     = useState<MarketFilter>('All');
  const [result,     setResult]     = useState<PricingResponse | null>(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const { data: portfolio } = useSWR('portfolio/pricing', () => getPortfolio(), { shouldRetryOnError: false });
  const { data: citiesData } = useSWR('cities/pricing', () => getCities(), { shouldRetryOnError: false });

  const allEntities = portfolio?.portfolio ?? [];
  const indiaCount = allEntities.filter(e => !e.is_international).length;
  const globalCount = allEntities.filter(e => e.is_international).length;
  const entities = allEntities.filter(e => {
    if (market === 'India') return !e.is_international;
    if (market === 'Global') return e.is_international;
    return true;
  });
  const cities   = citiesData?.cities ?? [];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!entityId || !city || !capacity || !price) return;

    setLoading(true);
    setError(null);
    try {
      const res = await optimizePrice({
        entity_id:        entityId,
        city,
        venue_capacity:   Number(capacity),
        proposed_price:   Number(price),
        category:         category || undefined,
      });
      setResult(res);
    } catch (err: any) {
      setError(err.message ?? 'Failed to get pricing recommendation. Ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Pricing Optimizer" subtitle="Signal-based ticket price recommendation for every act and city" />

      <div className={styles.page}>
        {/* Form */}
        <GlassCard className={styles.formCard} delay={0.04}>
          <div className={styles.formHeader}>
            <IndianRupee size={18} color="var(--accent)" />
            <div>
              <h2 className="t-headline text-primary">Configure Event</h2>
              <p className="t-footnote text-tertiary">Select the artist, city, venue capacity, and your proposed price</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className={styles.form}>
            {/* Market toggle */}
            <div className={styles.filterRow} style={{ marginBottom: 4 }}>
              {MARKETS.map(m => (
                <button
                  key={m}
                  type="button"
                  className={`${styles.filterChip} ${market === m ? styles.filterActive : ''}`}
                  onClick={() => { setMarket(m); setEntityId(''); }}
                >
                  {m}
                  {m === 'India' && ` (${indiaCount})`}
                  {m === 'Global' && ` (${globalCount})`}
                </button>
              ))}
            </div>

            <div className={styles.formGrid}>
              {/* Artist selector */}
              <div className={styles.field}>
                <label className={styles.label}>Artist / Act</label>
                <div className={styles.selectWrap}>
                  <select
                    className={`input ${styles.select}`}
                    value={entityId}
                    onChange={e => setEntityId(e.target.value)}
                    required
                  >
                    <option value="">Select artist...</option>
                    {entities.map(e => (
                      <option key={e.id} value={e.id}>{e.name}</option>
                    ))}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
                {entities.length === 0 && (
                  <p className="t-caption text-tertiary" style={{ marginTop: 4 }}>
                    {allEntities.length === 0 ? 'Backend offline — start FastAPI to load artists' : `No ${market} artists match`}
                  </p>
                )}
              </div>

              {/* City selector */}
              <div className={styles.field}>
                <label className={styles.label}>City</label>
                <div className={styles.selectWrap}>
                  <select
                    className={`input ${styles.select}`}
                    value={city}
                    onChange={e => setCity(e.target.value)}
                    required
                    disabled={cities.length === 0}
                  >
                    <option value="">{cities.length > 0 ? 'Select city...' : 'Cities unavailable'}</option>
                    {cities.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
                {cities.length === 0 && (
                  <p className="t-caption text-tertiary" style={{ marginTop: 4 }}>Backend offline — start FastAPI to load cities</p>
                )}
              </div>

              {/* Capacity */}
              <div className={styles.field}>
                <label className={styles.label}>Venue Capacity</label>
                <input
                  type="number"
                  className="input"
                  placeholder="e.g. 15000"
                  value={capacity}
                  onChange={e => setCapacity(e.target.value)}
                  min={100}
                  max={200000}
                  required
                />
                <div className={styles.capacityChips}>
                  {[2000, 8000, 15000, 55000].map(c => (
                    <button
                      key={c}
                      type="button"
                      className={`${styles.filterChip} ${capacity === String(c) ? styles.filterActive : ''}`}
                      onClick={() => setCapacity(String(c))}
                    >
                      {c.toLocaleString()}
                    </button>
                  ))}
                </div>
              </div>

              {/* Proposed price */}
              <div className={styles.field}>
                <label className={styles.label}>Your Proposed Price (₹)</label>
                <input
                  type="number"
                  className="input"
                  placeholder="e.g. 4500"
                  value={price}
                  onChange={e => setPrice(e.target.value)}
                  min={100}
                  required
                />
                <div className={styles.capacityChips}>
                  {[1500, 3000, 5000, 8000].map(p => (
                    <button
                      key={p}
                      type="button"
                      className={`${styles.filterChip} ${price === String(p) ? styles.filterActive : ''}`}
                      onClick={() => setPrice(String(p))}
                    >
                      ₹{p.toLocaleString('en-IN')}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !entityId || !city || !capacity || !price}
              style={{ alignSelf: 'flex-end', minWidth: 180 }}
            >
              {loading ? 'Analyzing signals...' : <><Zap size={14} /> Optimize Price</>}
            </button>
          </form>

          {error && (
            <div className={styles.errorBox}>
              <AlertCircle size={14} color="var(--negative)" />
              <span className="t-callout" style={{ color: 'var(--negative)' }}>{error}</span>
            </div>
          )}
        </GlassCard>

        {/* Result */}
        <AnimatePresence mode="wait">
          {result && <RecommendationCard key="rec" data={result} />}
        </AnimatePresence>

        {!result && !loading && (
          <motion.div
            className={styles.placeholder}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
          >
            <IndianRupee size={36} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 14 }}>Configure an event above</p>
            <p className="t-callout text-tertiary" style={{ maxWidth: 320, textAlign: 'center', lineHeight: 1.6, marginTop: 6 }}>
              The optimizer uses Google Trend scores, city demand multipliers, venue capacity factors, and season signals to recommend the optimal ticket price.
            </p>
          </motion.div>
        )}
      </div>
    </div>
  );
}
