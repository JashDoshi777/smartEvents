'use client';

/* eslint-disable react-hooks/set-state-in-effect -- these effects sync state from external sources (URL params, localStorage, debounced network results), which is the intended use */

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Info, AlertCircle } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { ChipRow, Segmented } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuth } from '@/components/providers/AuthProvider';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { EntityPicker } from '@/components/intel/EntityPicker';
import { ScoreRing } from '@/components/intel/ScoreRing';
import { initials, useScopedPortfolio } from '@/components/intel/entity-utils';
import { getCities, getRankedRecommendations, getSignVerdict, SignVerdictResponse } from '@/lib/api';
import { inr, num } from '@/lib/format';
import k from '@/components/intel/Kit.module.css';
import styles from './page.module.css';

const CATEGORIES = [
  { value: '', label: 'All' }, { value: 'music', label: 'Music' }, { value: 'comedy', label: 'Comedy' },
  { value: 'sports', label: 'Sports' }, { value: 'theatre', label: 'Theatre' },
];

const VERDICT: Record<string, { color: string; label: string }> = {
  sign: { color: 'var(--positive)', label: 'Sign' },
  consider: { color: 'var(--text-primary)', label: 'Consider' },
  pass: { color: 'var(--negative)', label: 'Pass' },
  insufficient_data: { color: 'var(--text-secondary)', label: 'Insufficient data' },
};

function Content() {
  const params = useSearchParams();
  const { isIndia, scope } = useMarketScope();
  const { user } = useAuth();
  const canSign = !user || user.role !== 'viewer';
  const [category, setCategory] = useState('');
  const [city, setCity] = useState('');

  const cities = useSWR('cities/all', () => getCities());
  const cityList = useMemo(() => cities.data?.cities ?? [], [cities.data]);
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
    <Page title="Recommendations" subtitle={`Who to book next in ${isIndia ? 'India' : 'global markets'}, and a call on each deal`}>
      <div className={styles.grid}>
        <div>
          <div className={styles.filters}>
            <Segmented ariaLabel="Category" value={category} onChange={setCategory} options={CATEGORIES} />
            <ChipRow value={city} onChange={setCity} options={[{ value: '', label: 'Any city' }, ...cityList.map(c => ({ value: c.name, label: c.name }))]} />
          </div>
          <div className={styles.secH}><span>{rec.data?.methodology ?? 'Ranked candidates'}</span>{rec.data && <span>{num(rec.data.total_candidates)} candidates</span>}</div>
          <GlassCard className={k.group} delay={0.04}>
            {rec.isLoading && !rec.data ? (
              <div style={{ display: 'grid', gap: 8, padding: 16 }}>{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} height={52} radius={12} />)}</div>
            ) : rec.error && !rec.data ? (
              <ErrorState message={city ? 'Couldn’t rank for this city. Try another or clear the city filter.' : 'Couldn’t load recommendations.'} onRetry={() => rec.mutate()} />
            ) : items.length === 0 ? (
              <EmptyState title="No candidates match" message={`No ${isIndia ? 'Indian' : 'global'} entities with live scores fit these filters${city ? ` for ${city}` : ''}. Try widening them.`} />
            ) : (
              <div style={{ opacity: rec.isValidating ? 0.6 : 1, transition: 'opacity .2s' }}>
                {items.map((r, i) => (
                  <motion.button key={r.entity_id} type="button" className={k.row} style={{ ['--inset' as string]: '84px' }} aria-pressed={entityId === r.entity_id} onClick={() => selectRow(r.entity_id)}
                    initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} whileTap={{ scale: 0.99 }} transition={{ duration: 0.28, delay: Math.min(i, 12) * 0.025 }}>
                    <span className="num-rounded" style={{ width: 20, textAlign: 'right', color: 'var(--text-tertiary)', fontSize: '.8125rem' }}>{r.rank}</span>
                    <span className={k.avatar}>{initials(r.entity_name)}</span>
                    <span className={k.main}>
                      <span className={k.name}>{r.entity_name}{r.trend_direction === 'rising' && <TrendingUp size={13} strokeWidth={1.75} color="var(--positive)" />}{r.trend_direction === 'falling' && <TrendingDown size={13} strokeWidth={1.75} color="var(--negative)" />}</span>
                      <span className={k.sub}>{r.category ?? '—'}{r.city_demand_score != null ? ` · ${city} fit ${Math.round(r.city_demand_score)}` : ''}</span>
                    </span>
                    <span className={`${k.trail} num-rounded`} style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '1.0625rem' }}>{r.recommendation_score.toFixed(1)}</span>
                  </motion.button>
                ))}
              </div>
            )}
          </GlassCard>
        </div>

        <div className={styles.sticky} ref={formRef}>
          <GlassCard className={k.surface} delay={0.1}>
            <h2 className={k.title}>Sign, consider or pass</h2>
            <p className="t-footnote text-secondary" style={{ margin: '2px 0 16px' }}>Run one booking through the fill-rate and pricing model.</p>
            <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className={styles.form}>
                <div className={styles.frow}><label>Artist</label><div className={styles.picker}><EntityPicker entities={pickerList} value={entityId} onChange={id => { setEntityId(id); setResult(null); }} loading={pLoading} placeholder="Select" inline /></div></div>
                <div className={styles.frow}><label htmlFor="sign-city">City</label>
                  <select id="sign-city" value={signCity} onChange={e => setSignCity(e.target.value)} dir="rtl">{cityList.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}</select></div>
                <div className={styles.frow}><label htmlFor="sign-cap">Venue capacity</label>
                  <input id="sign-cap" type="number" inputMode="numeric" min={100} max={200000} value={capacity} onChange={e => setCapacity(e.target.value)} /></div>
                <div className={styles.frow}><label htmlFor="sign-price">Ticket price (₹)</label>
                  <input id="sign-price" type="number" inputMode="numeric" min={100} max={100000} value={price} onChange={e => setPrice(e.target.value)} /></div>
              </div>
              <p className="t-footnote text-tertiary" style={{ padding: '0 4px' }}>{num(cap)} seats at {inr(pr)} is up to {inr(cap * pr)} gross.</p>
              {!canSign && <div className={styles.note}><Info size={16} strokeWidth={1.7} style={{ flexShrink: 0, marginTop: 1 }} />Sign verdicts need Analyst, Booker or Executive access. Your account is a viewer, so the form is read-only.</div>}
              {error && <div className={styles.err} role="alert"><AlertCircle size={16} strokeWidth={1.7} style={{ flexShrink: 0, marginTop: 1 }} />{error}</div>}
              <motion.button whileTap={{ scale: 0.98 }} type="submit" className="btn btn-primary" disabled={busy || !valid || !canSign} style={{ minHeight: 44, justifyContent: 'center' }}>{busy ? 'Evaluating…' : 'Get verdict'}</motion.button>
            </form>

            {result && v && (
              <motion.div className={styles.verdict} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ type: 'spring', stiffness: 220, damping: 24 }} aria-live="polite">
                <div className={styles.vTop}>
                  <ScoreRing score={result.predicted_fill_rate_pct} size={84} stroke={8} />
                  <div>
                    <p style={{ fontSize: '1.375rem', fontWeight: 700, letterSpacing: '-0.03em', color: v.color }}>{v.label}</p>
                    <p className="t-footnote text-secondary">{Math.round(result.predicted_fill_rate_pct)}% predicted fill · {Math.round(result.confidence)}% confidence</p>
                  </div>
                </div>
                <div className={styles.kv}>
                  <div className={k.kvRow} style={{ padding: '12px 16px' }}><span>Your price</span><span className="num-rounded">{inr(result.proposed_price)}</span></div>
                  <div className={k.kvRow} style={{ padding: '12px 16px' }}><span>Model price</span><span className="num-rounded">{inr(result.recommended_price)}</span></div>
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
