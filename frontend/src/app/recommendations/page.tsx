'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import {
  Sparkles, ChevronDown, TrendingUp, TrendingDown, Minus,
  CheckCircle2, AlertTriangle, XCircle, Info,
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getCities, getRecommendedEntities, getSignRecommendation } from '@/lib/api';
import styles from './page.module.css';

function TrendIcon({ direction }: { direction?: string }) {
  if (direction === 'rising') return <TrendingUp size={14} color="var(--positive)" />;
  if (direction === 'falling') return <TrendingDown size={14} color="var(--negative)" />;
  return <Minus size={14} color="var(--text-tertiary)" />;
}

const VERDICT_STYLE: Record<string, { color: string; icon: any; label: string }> = {
  sign: { color: 'var(--positive)', icon: CheckCircle2, label: 'Sign' },
  consider: { color: 'var(--warning)', icon: AlertTriangle, label: 'Consider' },
  pass: { color: 'var(--negative)', icon: XCircle, label: 'Pass' },
  insufficient_data: { color: 'var(--text-tertiary)', icon: Info, label: 'Insufficient data' },
};

export default function RecommendationsPage() {
  const [category, setCategory] = useState('');
  const [city, setCity] = useState('');

  const { data: citiesData } = useSWR('cities/recommend', () => getCities(), { shouldRetryOnError: false });
  const cities = citiesData?.cities ?? [];

  const { data, isLoading } = useSWR(
    `recommend-entities-${category}-${city}`,
    () => getRecommendedEntities({ category: category || undefined, city: city || undefined, limit: 15 }),
    { shouldRetryOnError: false }
  );
  const recommendations = data?.recommendations ?? [];

  // ── Sign evaluator ────────────────────────────────────────────────────────
  const { data: portfolio } = useSWR('portfolio/recommend', () => getPortfolio(), { shouldRetryOnError: false });
  const entities = portfolio?.portfolio ?? [];

  const [signEntityId, setSignEntityId] = useState('');
  const [signCity, setSignCity] = useState('');
  const [capacity, setCapacity] = useState('5000');
  const [price, setPrice] = useState('2500');
  const [signResult, setSignResult] = useState<any>(null);
  const [signLoading, setSignLoading] = useState(false);
  const [signError, setSignError] = useState<string | null>(null);

  async function handleSign(e: React.FormEvent) {
    e.preventDefault();
    if (!signEntityId || !signCity || !capacity || !price) return;
    setSignLoading(true);
    setSignError(null);
    try {
      const res = await getSignRecommendation({
        entity_id: signEntityId,
        city: signCity,
        venue_capacity: Number(capacity),
        proposed_price: Number(price),
      });
      setSignResult(res);
    } catch (err: any) {
      setSignError(err.message ?? 'Failed to get a sign recommendation. Requires Executive/Analyst/Booker role.');
    } finally {
      setSignLoading(false);
    }
  }

  const verdict = signResult ? (VERDICT_STYLE[signResult.verdict] ?? VERDICT_STYLE.insufficient_data) : null;
  const VerdictIcon = verdict?.icon;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="AI Recommendations" subtitle="Rules + real-signal ranking of who to book, and a sign/consider/pass verdict for a specific deal" />

      <div className={styles.page}>
        {/* Ranked candidates */}
        <GlassCard className={styles.listCard} delay={0.04}>
          <div className={styles.cardHead}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Sparkles size={15} color="var(--accent)" />
              <h2 className="t-headline text-primary">Ranked Candidates</h2>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <div className={styles.selectWrap}>
                <select className={`input ${styles.select}`} value={category} onChange={e => setCategory(e.target.value)}>
                  <option value="">All categories</option>
                  <option value="music">Music</option>
                  <option value="comedy">Comedy</option>
                  <option value="sports">Sports</option>
                  <option value="theatre">Theatre</option>
                </select>
                <ChevronDown size={13} className={styles.selectIcon} />
              </div>
              <div className={styles.selectWrap}>
                <select className={`input ${styles.select}`} value={city} onChange={e => setCity(e.target.value)}>
                  <option value="">No target city</option>
                  {cities.map((c: any) => <option key={c.id} value={c.name}>{c.name}</option>)}
                </select>
                <ChevronDown size={13} className={styles.selectIcon} />
              </div>
            </div>
          </div>
          <p className="t-caption text-tertiary" style={{ marginBottom: 14 }}>{data?.methodology}</p>

          {isLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 52, borderRadius: 10 }} />)}
            </div>
          ) : recommendations.length === 0 ? (
            <div className={styles.empty}>
              <Info size={20} color="var(--text-tertiary)" strokeWidth={1.5} />
              <p className="t-callout text-tertiary" style={{ marginTop: 10, textAlign: 'center' }}>
                No entities with real collected metrics match these filters yet.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {recommendations.map((r: any, i: number) => (
                <motion.div key={r.entity_id} className={styles.recRow} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}>
                  <span className={styles.rank}>#{r.rank}</span>
                  <div style={{ flex: 1 }}>
                    <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{r.entity_name}</p>
                    <p className="t-caption text-tertiary">{r.category} {r.is_international && '· International'}</p>
                  </div>
                  <TrendIcon direction={r.trend_direction} />
                  {r.city_demand_score != null && (
                    <span className="t-caption text-tertiary">city fit {r.city_demand_score}</span>
                  )}
                  <span className="t-callout text-primary" style={{ fontWeight: 800, minWidth: 48, textAlign: 'right' }}>
                    {r.recommendation_score}
                  </span>
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>

        {/* Sign evaluator */}
        <GlassCard className={styles.formCard} delay={0.1}>
          <div className={styles.cardHead}>
            <h2 className="t-headline text-primary">Sign / Consider / Pass</h2>
          </div>
          <form onSubmit={handleSign} className={styles.form}>
            <div className={styles.formGrid}>
              <div className={styles.field}>
                <label className={styles.label}>Artist / Act</label>
                <div className={styles.selectWrap}>
                  <select className={`input ${styles.select}`} value={signEntityId} onChange={e => setSignEntityId(e.target.value)} required>
                    <option value="">Select...</option>
                    {entities.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                  <ChevronDown size={13} className={styles.selectIcon} />
                </div>
              </div>
              <div className={styles.field}>
                <label className={styles.label}>City</label>
                <div className={styles.selectWrap}>
                  <select className={`input ${styles.select}`} value={signCity} onChange={e => setSignCity(e.target.value)} required>
                    <option value="">Select...</option>
                    {cities.map((c: any) => <option key={c.id} value={c.name}>{c.name}</option>)}
                  </select>
                  <ChevronDown size={13} className={styles.selectIcon} />
                </div>
              </div>
              <div className={styles.field}>
                <label className={styles.label}>Venue capacity</label>
                <input className="input" type="number" value={capacity} onChange={e => setCapacity(e.target.value)} min={100} max={100000} required />
              </div>
              <div className={styles.field}>
                <label className={styles.label}>Proposed price (₹)</label>
                <input className="input" type="number" value={price} onChange={e => setPrice(e.target.value)} min={100} max={50000} required />
              </div>
            </div>
            {signError && (
              <div className={styles.errorBox}>
                <AlertTriangle size={16} color="var(--negative)" />
                <span className="t-callout" style={{ color: 'var(--negative)' }}>{signError}</span>
              </div>
            )}
            <button type="submit" className="btn btn-primary" disabled={signLoading} style={{ alignSelf: 'flex-start' }}>
              {signLoading ? 'Evaluating...' : 'Get Verdict'}
            </button>
          </form>

          {signResult && verdict && (
            <motion.div className={styles.verdictBox} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} style={{ borderColor: verdict.color + '50' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {VerdictIcon && <VerdictIcon size={22} color={verdict.color} />}
                <span style={{ fontSize: '1.1rem', fontWeight: 800, color: verdict.color }}>{verdict.label}</span>
                <span className="t-caption text-tertiary" style={{ marginLeft: 'auto' }}>
                  {signResult.predicted_fill_rate_pct}% predicted fill · {signResult.confidence}% confidence
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
                {signResult.reasons.map((r: string, i: number) => (
                  <p key={i} className="t-callout text-secondary" style={{ lineHeight: 1.5 }}>· {r}</p>
                ))}
              </div>
            </motion.div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
