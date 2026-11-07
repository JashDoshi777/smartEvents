'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Sparkles, TrendingUp, TrendingDown, Minus, CheckCircle2, AlertTriangle, XCircle, Info, AlertCircle } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuth } from '@/components/providers/AuthProvider';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { EntityPicker } from '@/components/intel/EntityPicker';
import { ScoreRing } from '@/components/intel/ScoreRing';
import { initials, scoreColor, useScopedPortfolio } from '@/components/intel/entity-utils';
import { getCities, getRankedRecommendations, getSignVerdict, SignVerdictResponse } from '@/lib/api';
import { inr, num } from '@/lib/format';
import styles from './page.module.css';

const CATEGORIES = [
  { value: '', label: 'All' }, { value: 'music', label: 'Music' }, { value: 'comedy', label: 'Comedy' },
  { value: 'sports', label: 'Sports' }, { value: 'theatre', label: 'Theatre' },
];

const VERDICT: Record<string, { color: string; Icon: typeof Info; label: string }> = {
  sign: { color: 'var(--positive)', Icon: CheckCircle2, label: 'Sign' },
  consider: { color: 'var(--text-primary)', Icon: AlertTriangle, label: 'Consider' },
  pass: { color: 'var(--negative)', Icon: XCircle, label: 'Pass' },
  insufficient_data: { color: 'var(--text-tertiary)', Icon: Info, label: 'Insufficient data' },
};

function Trend({ d }: { d?: string }) {
  if (d === 'rising') return <TrendingUp size={14} color="var(--positive)" aria-label="Rising" />;
  if (d === 'falling') return <TrendingDown size={14} color="var(--negative)" aria-label="Falling" />;
  return <Minus size={14} color="var(--text-tertiary)" aria-label="Stable" />;
}

function Content() {
  const params = useSearchParams();
  const { isIndia, scope } = useMarketScope();
  const { user } = useAuth();
  const canSign = !user || user.role !== 'viewer';
  const [category, setCategory] = useState('');
  const [city, setCity] = useState('');

  const cities = useSWR('cities/all', () => getCities());
  const cityList = cities.data?.cities ?? [];
  const rec = useSWR(['recommend', scope, category, city], () => getRankedRecommendations({ category, city, isInternational: !isIndia, limit: 20 }), { keepPreviousData: true });
  const items = rec.data?.recommendations ?? [];
  const { scoped, all, isLoading: pLoading } = useScopedPortfolio();

  // Sign evaluator
  const formRef = useRef<HTMLDivElement>(null);
  const [entityId, setEntityId] = useState('');
  const [signCity, setSignCity] = useState('');
  const [capacity, setCapacity] = useState('5000');
  const [price, setPrice] = useState('2500');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SignVerdictResponse | null>(null);

  const deep = params.get('entity');
  useEffect(() => { if (deep) setEntityId(deep); }, [deep]);
  useEffect(() => { if (!signCity && cityList.length) setSignCity(cityList[0].name); }, [cityList, signCity]);

  // Picker offers scoped entities, plus whichever is selected (deep link / row click) even if out of scope.
  const pickerList = useMemo(() => {
    const extra = all.find(e => e.id === entityId);
    return extra && !scoped.some(e => e.id === entityId) ? [extra, ...scoped] : scoped;
  }, [scoped, all, entityId]);

  const cap = Number(capacity), pr = Number(price);
  const valid = !!entityId && !!signCity && cap >= 100 && cap <= 200000 && pr >= 100 && pr <= 100000;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true); setError(null);
    try {
      setResult(await getSignVerdict({ entity_id: entityId, city: signCity, venue_capacity: cap, proposed_price: pr }));
    } catch (err) {
      const m = err instanceof Error ? err.message : '';
      setResult(null);
      setError(m.includes('403') ? 'Your role can’t request sign verdicts. This needs Executive, Analyst or Booker access.'
        : m.includes('503') ? 'The pricing model is unavailable right now. Try again shortly.' : 'Couldn’t get a verdict. Please try again.');
    } finally { setBusy(false); }
  }

  function selectRow(id: string) {
    setEntityId(id); setResult(null); setError(null);
    if (city) setSignCity(city);
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  const v = result ? VERDICT[result.verdict] ?? VERDICT.insufficient_data : null;

  return (
    <Page title="AI Recommendations" subtitle={`Who to book next in ${isIndia ? 'India' : 'global markets'}, and a sign / consider / pass call per deal`}>
      <div className={styles.grid}>
        <GlassCard className={styles.card} delay={0.04}>
          <div className={styles.head}>
            <h2 className="t-headline" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Sparkles size={16} /> Ranked candidates</h2>
            {rec.data && <span className="t-caption text-tertiary">{num(rec.data.total_candidates)} candidates</span>}
          </div>
          <div className={styles.filters}>
            <ChipRow value={category} onChange={setCategory} options={CATEGORIES} />
            <ChipRow value={city} onChange={setCity} options={[{ value: '', label: 'Any city' }, ...cityList.map(c => ({ value: c.name, label: c.name }))]} />
          </div>
          <p className="t-caption text-tertiary" style={{ marginBottom: 10 }}>{rec.data?.methodology}</p>

          {rec.isLoading && !rec.data ? (
            <div style={{ display: 'grid', gap: 8 }}>{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} height={56} radius={12} />)}</div>
          ) : rec.error && !rec.data ? (
            <ErrorState message={city ? 'Couldn’t rank for this city. Try another or clear the city filter.' : 'Couldn’t load recommendations.'} onRetry={() => rec.mutate()} />
          ) : items.length === 0 ? (
            <EmptyState title="No candidates match" message={`No ${isIndia ? 'Indian' : 'global'} entities with live scores fit these filters${city ? ` for ${city}` : ''}. Try widening them.`} />
          ) : (
            <div style={{ opacity: rec.isValidating ? 0.6 : 1, transition: 'opacity .2s' }}>
              {items.map((r, i) => (
                <motion.button key={r.entity_id} type="button" className={styles.row} aria-pressed={entityId === r.entity_id} onClick={() => selectRow(r.entity_id)}
                  initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} whileTap={{ scale: 0.985 }} transition={{ duration: 0.28, delay: Math.min(i, 12) * 0.025 }}>
                  <span className={`${styles.rank} tnum`}>{r.rank}</span>
                  <span className={styles.av}>{initials(r.entity_name)}</span>
                  <span className={styles.main}>
                    <b>{r.entity_name}</b>
                    <span className="t-caption text-tertiary">{r.category ?? '—'}{r.city_demand_score != null ? ` · ${city} fit ${Math.round(r.city_demand_score)}` : ''}</span>
                  </span>
                  <Trend d={r.trend_direction} />
                  <span className={styles.right}>
                    <span className="tnum" style={{ fontWeight: 700, letterSpacing: '-0.03em', color: scoreColor(r.recommendation_score) }}>{r.recommendation_score.toFixed(1)}</span>
                    <span className={styles.bar}><i style={{ width: `${r.recommendation_score}%`, background: scoreColor(r.recommendation_score) }} /></span>
                  </span>
                </motion.button>
              ))}
            </div>
          )}
        </GlassCard>

        <div className={styles.sticky} ref={formRef}>
          <GlassCard className={styles.card} delay={0.1}>
            <h2 className="t-headline" style={{ marginBottom: 4 }}>Sign / consider / pass</h2>
            <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>Run one booking through the fill-rate and pricing model.</p>
            <form className={styles.form} onSubmit={submit}>
              <div className={styles.field}>
                <label className={styles.label}>Artist or act</label>
                <EntityPicker entities={pickerList} value={entityId} onChange={id => { setEntityId(id); setResult(null); }} loading={pLoading} />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="sign-city">City</label>
                <select id="sign-city" className="input" value={signCity} onChange={e => setSignCity(e.target.value)} style={{ minHeight: 44 }}>
                  {cityList.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
                </select>
              </div>
              <div className={styles.two}>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="sign-cap">Venue capacity</label>
                  <input id="sign-cap" className="input" type="number" inputMode="numeric" min={100} max={200000} value={capacity} onChange={e => setCapacity(e.target.value)} style={{ minHeight: 44 }} />
                </div>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="sign-price">Ticket price (₹)</label>
                  <input id="sign-price" className="input" type="number" inputMode="numeric" min={100} max={100000} value={price} onChange={e => setPrice(e.target.value)} style={{ minHeight: 44 }} />
                </div>
              </div>
              <p className="t-caption text-tertiary">{num(cap)} seats at {inr(pr)} is up to {inr(cap * pr)} gross.</p>
              {!canSign && <div className={styles.note}><Info size={16} style={{ flexShrink: 0, marginTop: 1 }} />Sign verdicts need Analyst, Booker or Executive access. Your account is a viewer, so the form is read-only.</div>}
              {error && <div className={styles.err} role="alert"><AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />{error}</div>}
              <button type="submit" className="btn btn-primary" disabled={busy || !valid || !canSign} style={{ justifyContent: 'center' }}>{busy ? 'Evaluating…' : 'Get verdict'}</button>
            </form>

            {result && v && (
              <motion.div className={styles.verdict} style={{ background: 'var(--fill-quaternary)' }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} aria-live="polite">
                <div className={styles.vTop}>
                  <ScoreRing score={result.predicted_fill_rate_pct} size={84} />
                  <div>
                    <p style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '1.25rem', fontWeight: 700, color: v.color }}><v.Icon size={20} /> {v.label}</p>
                    <p className="t-footnote text-tertiary">{Math.round(result.predicted_fill_rate_pct)}% predicted fill · {Math.round(result.confidence)}% confidence</p>
                  </div>
                </div>
                <div className={styles.kv}>
                  <div><span className="t-caption text-tertiary">Your price</span><b className="tnum">{inr(result.proposed_price)}</b></div>
                  <div><span className="t-caption text-tertiary">Model price</span><b className="tnum">{inr(result.recommended_price)}</b></div>
                </div>
                <ul className={styles.reasons}>{result.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </motion.div>
            )}
          </GlassCard>
        </div>
      </div>
    </Page>
  );
}

export default function RecommendationsPage() {
  return <Suspense fallback={null}><Content /></Suspense>;
}
