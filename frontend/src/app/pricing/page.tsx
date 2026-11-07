'use client';

import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { AnimatePresence, motion } from 'framer-motion';
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowDownRight, ArrowUpRight, ChevronRight, Lock, Search, Sparkles, TriangleAlert } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { useAuth } from '@/components/providers/AuthProvider';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { Ring, ROUNDED } from '@/components/insights/Ring';
import { CountUp } from '@/components/insights/CountUp';
import { inr, inrCompact, num } from '@/lib/format';
import {
  ApiError, EntitySearchResult, PricingResult, getElasticityCurve, getMarketCities, getPortfolio,
  getPriceBenchmarkTable, optimizePriceStrict, searchEntities,
} from '@/lib/api';
import styles from './page.module.css';

const CAP = { min: 100, max: 100000 };
const PRICE = { min: 100, max: 50000 };
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const CAP_PRESETS = [800, 2000, 8000, 15000, 50000];
const PRICE_PRESETS = [800, 1500, 3000, 5000, 8000];

const toSlider = (v: number, lo: number, hi: number) => Math.round((Math.log(Math.max(v, lo) / lo) / Math.log(hi / lo)) * 1000);
const fromSlider = (t: number, lo: number, hi: number, step: number) => Math.round((lo * Math.pow(hi / lo, t / 1000)) / step) * step;
const guessCategory = (cat: string | null | undefined, keys: string[]) => keys.find(k => (cat ?? '').toLowerCase().includes(k)) ?? 'music';

type Picked = { id: string; name: string; category: string | null; is_international: boolean };

function LogRange({ value, lo, hi, step, onChange, label }: { value: number; lo: number; hi: number; step: number; onChange: (v: number) => void; label: string }) {
  return <input type="range" className={styles.range} aria-label={label} min={0} max={1000} value={toSlider(value || lo, lo, hi)} onChange={e => onChange(Math.min(hi, Math.max(lo, fromSlider(+e.target.value, lo, hi, step))))} />;
}

function PriceLadder({ bench, proposed, recommended }: { bench: { floor: number; sweet_spot: number; premium: number; ultra_premium: number }; proposed: number | null; recommended: number | null }) {
  const lo = bench.floor * 0.6, hi = bench.ultra_premium * 1.1;
  const pos = (v: number) => `${Math.max(2, Math.min(98, ((Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * 100))}%`;
  return (
    <div>
      <div className={styles.ladder}>
        <div className={styles.ladderTrack}><div className={styles.ladderBand} style={{ left: pos(bench.sweet_spot * 0.8), right: `calc(100% - ${pos(bench.premium)})` }} /></div>
        {proposed != null && <div className={`${styles.pin} ${styles.pinLow}`} style={{ left: pos(proposed), color: 'var(--text-secondary)' }}><span className={styles.pinStem} style={{ background: 'var(--text-secondary)' }} />Yours {inrCompact(proposed)}</div>}
        {recommended != null && <div className={styles.pin} style={{ left: pos(recommended), color: 'var(--accent)' }}>Optimal {inrCompact(recommended)}<span className={styles.pinStem} style={{ background: 'var(--accent)' }} /></div>}
      </div>
      <div className={styles.ticks}><span>Floor {inrCompact(bench.floor)}</span><span>Sweet spot {inrCompact(bench.sweet_spot)}</span><span>Premium {inrCompact(bench.premium)}</span><span>Ultra {inrCompact(bench.ultra_premium)}</span></div>
    </div>
  );
}

function ActPicker({ open, onClose, onPick }: { open: boolean; onClose: () => void; onPick: (e: Picked) => void }) {
  const { isIndia } = useMarketScope();
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const portfolio = useSWR(open ? 'pricing-portfolio' : null, () => getPortfolio());
  const search = useSWR(open && dq.length >= 2 ? ['pricing-search', dq] : null, () => searchEntities(dq, 20));
  const list: Picked[] = dq.length >= 2
    ? (search.data?.results ?? []).map((r: EntitySearchResult) => ({ id: r.id, name: r.name, category: r.category, is_international: r.is_international }))
    : (portfolio.data?.portfolio ?? []).filter(p => !isIndia || !p.is_international).slice(0, 40).map(p => ({ id: p.id, name: p.name, category: p.category, is_international: p.is_international }));
  const loading = dq.length >= 2 ? search.isLoading : portfolio.isLoading;
  return (
    <Sheet open={open} onClose={onClose} title="Choose an act">
      <div style={{ position: 'relative' }}>
        <Search size={15} style={{ position: 'absolute', left: 12, top: 15, color: 'var(--text-tertiary)' }} />
        <input autoFocus className={`input ${styles.pickerSearch}`} style={{ paddingLeft: 36 }} placeholder="Search artists, comedians, bands" aria-label="Search acts" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <div className={styles.pickList}>
        {loading ? <Skeleton height={52} radius={12} style={{ margin: '6px 0' }} /> : list.length === 0 ? <EmptyState title="No acts found" message="Try a different name." /> : list.map(e => (
          <button key={e.id} className={styles.pick} onClick={() => { onPick(e); onClose(); setQ(''); }}>
            <div style={{ flex: 1, minWidth: 0 }}><p className="t-callout" style={{ fontWeight: 600 }}>{e.name}</p><p className="t-caption text-tertiary">{e.category ?? '—'}{e.is_international ? ' · International' : ' · India'}</p></div>
            <ChevronRight size={16} color="var(--text-tertiary)" />
          </button>
        ))}
      </div>
    </Sheet>
  );
}

export default function PricingPage() {
  const { user } = useAuth();
  const toast = useToast();
  const { data: citiesData } = useSWR('market-cities', getMarketCities);
  const { data: bm } = useSWR('price-benchmarks', getPriceBenchmarkTable);
  const cities = citiesData?.cities.map(c => c.name) ?? [];
  const catKeys = Object.keys(bm?.benchmarks ?? {});

  const [act, setAct] = useState<Picked | null>(null);
  const [pickOpen, setPickOpen] = useState(false);
  const [city, setCity] = useState('Mumbai');
  const [category, setCategory] = useState('');
  const [month, setMonth] = useState('');
  const [capacity, setCapacity] = useState('8000');
  const [price, setPrice] = useState('3000');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PricingResult | null>(null);
  const [failure, setFailure] = useState<{ status: number; message: string } | null>(null);

  const capN = Number(capacity), priceN = Number(price);
  const errors = {
    act: act ? '' : 'Choose an act to price.',
    capacity: Number.isInteger(capN) && capN >= CAP.min && capN <= CAP.max ? '' : `Capacity must be a whole number between ${num(CAP.min)} and ${num(CAP.max)}.`,
    price: priceN >= PRICE.min && priceN <= PRICE.max ? '' : `Price must be between ${inr(PRICE.min)} and ${inr(PRICE.max)}.`,
  };
  const valid = !errors.act && !errors.capacity && !errors.price;

  const catKey = category || guessCategory(act?.category, catKeys);
  const bench = bm?.benchmarks[catKey];
  const cityMult = bm?.city_multipliers[city.toLowerCase()];

  // Viewer-safe live preview: price by city (GET endpoint is not role-gated)
  const elasticity = useSWR(act && !errors.price ? ['elasticity', act.id, priceN] : null, () => getElasticityCurve(act!.id, priceN), { keepPreviousData: true });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!valid || !act) return;
    setBusy(true); setFailure(null);
    try {
      const res = await optimizePriceStrict({ entity_id: act.id, city, venue_capacity: capN, proposed_price: priceN, category: category || undefined, event_date_month: month ? Number(month) : undefined });
      setResult(res);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setResult(null);
      setFailure({ status, message: err instanceof Error ? err.message : 'Something went wrong.' });
      if (status !== 403) toast('Couldn’t optimize price', 'error');
    } finally { setBusy(false); }
  }

  const rec = result?.recommendation;
  const delta = rec ? rec.recommended_price - rec.proposed_price : null;
  const deltaPct = rec && rec.proposed_price ? (delta! / rec.proposed_price) * 100 : null;
  const signals = result ? [
    ['Composite demand score', `${result.signals.composite_score}/100`],
    ['Search interest (Google Trends)', `${result.signals.google_trend_score}/100`],
    ['City price multiplier', `${result.signals.city_multiplier}×`],
    ['Venue capacity factor', `${result.signals.capacity_factor}×`],
    ['Season factor', `${result.signals.season_factor}×`],
    ['International premium', `${result.signals.international_factor}×`],
  ] : [];
  const curve = useMemo(() => (elasticity.data?.elasticity_curve ?? []).slice(0, 12), [elasticity.data]);
  const maxCurve = Math.max(1, ...curve.map(c => c.optimal_price));

  return (
    <Page title="Pricing" subtitle="ML ticket-price optimizer · all prices in ₹">
      <div className={styles.layout}>
        <form className={styles.form} onSubmit={submit} noValidate>
          <div>
            <p className={styles.groupLabel}>Event</p>
            <div className={styles.group}>
              <button type="button" className={styles.row} onClick={() => setPickOpen(true)} data-testid="act-picker">
                <span className={styles.rowLabel}>Act</span>
                <span className={styles.rowVal} style={{ color: act ? 'var(--text-primary)' : 'var(--text-tertiary)' }}>{act?.name ?? 'Choose'} <ChevronRight size={15} color="var(--text-tertiary)" /></span>
              </button>
              <div className={styles.row}>
                <label className={styles.rowLabel} htmlFor="pr-city">City</label>
                <select id="pr-city" className={styles.plainSelect} value={city} onChange={e => setCity(e.target.value)}>{(cities.length ? cities : [city]).map(c => <option key={c}>{c}</option>)}</select>
              </div>
              <div className={styles.row}>
                <label className={styles.rowLabel} htmlFor="pr-cat">Category</label>
                <select id="pr-cat" className={styles.plainSelect} value={category} onChange={e => setCategory(e.target.value)}>
                  <option value="">Auto ({catKey})</option>{catKeys.map(k => <option key={k} value={k}>{k}</option>)}
                </select>
              </div>
              <div className={styles.row}>
                <label className={styles.rowLabel} htmlFor="pr-month">Month</label>
                <select id="pr-month" className={styles.plainSelect} value={month} onChange={e => setMonth(e.target.value)}>
                  <option value="">Any</option>{MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
              </div>
            </div>
            {touched && errors.act && <p className={styles.err} role="alert">{errors.act}</p>}
          </div>

          <div>
            <p className={styles.groupLabel}>Venue and price</p>
            <div className={styles.group}>
              <div className={styles.block}>
                <div className={styles.blockTop}>
                  <label className="t-callout" htmlFor="pr-cap">Venue capacity</label>
                  <input id="pr-cap" className={styles.bigInput} inputMode="numeric" value={capacity} onChange={e => setCapacity(e.target.value.replace(/\D/g, ''))} aria-invalid={touched && !!errors.capacity} />
                </div>
                <LogRange label="Capacity slider" value={capN} lo={CAP.min} hi={CAP.max} step={100} onChange={v => setCapacity(String(v))} />
                <div className={styles.presets}>{CAP_PRESETS.map(c => <button key={c} type="button" className="chip" aria-pressed={capN === c} onClick={() => setCapacity(String(c))}>{num(c)}</button>)}</div>
              </div>
              <div className={styles.block}>
                <div className={styles.blockTop}>
                  <label className="t-callout" htmlFor="pr-price">Proposed ticket price</label>
                  <span style={{ display: 'flex', alignItems: 'baseline' }}><span className={styles.bigInput} style={{ width: 'auto', color: 'var(--text-tertiary)', marginRight: 4 }}>₹</span><input id="pr-price" className={styles.bigInput} style={{ width: 96 }} inputMode="numeric" value={price} onChange={e => setPrice(e.target.value.replace(/\D/g, ''))} aria-invalid={touched && !!errors.price} /></span>
                </div>
                <LogRange label="Price slider" value={priceN} lo={PRICE.min} hi={PRICE.max} step={50} onChange={v => setPrice(String(v))} />
                <div className={styles.presets}>{PRICE_PRESETS.map(p => <button key={p} type="button" className="chip" aria-pressed={priceN === p} onClick={() => setPrice(String(p))}>{inrCompact(p)}</button>)}</div>
              </div>
            </div>
            {touched && (errors.capacity || errors.price) && <p className={styles.err} role="alert">{errors.capacity || errors.price}</p>}
          </div>

          <button type="submit" className={`btn btn-primary ${styles.cta}`} disabled={busy} data-testid="optimize">{busy ? 'Analysing signals…' : <><Sparkles size={16} strokeWidth={1.75} /> Optimize price</>}</button>
        </form>

        <div className={styles.results} aria-live="polite">
          <AnimatePresence mode="wait">
            {failure?.status === 403 ? (
              <motion.div key="403" className={styles.notice} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="alert" data-testid="role-notice">
                <Lock size={22} color="var(--text-secondary)" style={{ flexShrink: 0, marginTop: 2 }} />
                <div><p className="t-headline">Optimizer requires Analyst or Booker access</p><p className="t-callout text-secondary" style={{ marginTop: 4 }}>You’re signed in as {user?.role ?? 'a viewer'}. Ask an admin to upgrade your role to Analyst, Booker or Executive. You can still explore benchmarks and city price levels below.</p></div>
              </motion.div>
            ) : failure ? (
              <motion.div key="err" className={`${styles.notice} ${styles.noticeErr}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="alert" data-testid="error-notice">
                <TriangleAlert size={22} color="var(--warning)" style={{ flexShrink: 0, marginTop: 2 }} />
                <div><p className="t-headline">{failure.status === 422 ? 'Check your inputs' : 'Couldn’t optimize this price'}</p><p className="t-callout text-secondary" style={{ marginTop: 4 }}>{failure.message}</p></div>
              </motion.div>
            ) : null}
          </AnimatePresence>

          {result && rec && (
            <motion.div className={styles.bento} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ type: 'spring', stiffness: 140, damping: 20 }} data-testid="result">
              <GlassCard className={styles.hero}>
                <div>
                  <h3 className={styles.title}>Recommended price</h3>
                  <p className={styles.sub}>{result.entity.name} · {city} · {rec.price_tier}</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
                  <CountUp className={styles.price} data-testid="rec-price" value={rec.recommended_price} format={inr} />
                  {delta != null && <span className={styles.delta} style={{ color: delta > 0 ? 'var(--positive)' : delta < 0 ? 'var(--negative)' : 'var(--text-tertiary)' }}>
                    {delta >= 0 ? <ArrowUpRight size={17} /> : <ArrowDownRight size={17} />}{inr(Math.abs(delta))}{deltaPct != null && ` (${Math.abs(deltaPct).toFixed(0)}%)`} vs {inr(rec.proposed_price)}</span>}
                </div>
                <PriceLadder bench={result.benchmarks} proposed={rec.proposed_price} recommended={rec.recommended_price} />
              </GlassCard>
              <GlassCard className={styles.fill}>
                <h3 className={styles.title}>Predicted fill</h3>
                <Ring value={rec.predicted_fill_rate} size={116} stroke={13} color="var(--text-primary)"><span style={{ fontFamily: ROUNDED, fontSize: '1.75rem', fontWeight: 700 }}>{rec.predicted_fill_rate != null ? `${Math.round(rec.predicted_fill_rate)}%` : '—'}</span></Ring>
                <p className={styles.sub}>{rec.predicted_fill_rate != null ? `≈ ${num(Math.round(capN * rec.predicted_fill_rate / 100))} of ${num(capN)} seats` : 'No fill estimate'}</p>
              </GlassCard>
              <GlassCard className={styles.half}>
                <h3 className={styles.title}>Why this price</h3>
                <p className={styles.reason}>{rec.reasoning}</p>
                <p className={styles.sub}>{rec.confidence} · model {result.model}</p>
              </GlassCard>
              <GlassCard className={styles.half}>
                <h3 className={styles.title}>Signals</h3>
                <div className={styles.signalList}>{signals.map(([k, v]) => <div key={k} className={styles.signal}><span className={styles.reason}>{k}</span><span className="num-rounded" style={{ fontWeight: 600 }}>{v}</span></div>)}</div>
              </GlassCard>
              <GlassCard className={styles.wide}>
                <div><h3 className={styles.title}>Price elasticity</h3><p className={styles.sub}>Expected attendance at each price point</p></div>
                {rec.sensitivity_curve.length > 0 ? (
                  <div className={styles.chart}><ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={rec.sensitivity_curve} margin={{ top: 8, right: 10, left: -12, bottom: 0 }}>
                      <defs><linearGradient id="elg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity={.3} /><stop offset="100%" stopColor="var(--accent)" stopOpacity={0} /></linearGradient></defs>
                      <CartesianGrid stroke="var(--divider)" vertical={false} />
                      <XAxis dataKey="price" type="number" domain={['dataMin', 'dataMax']} tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} tickFormatter={(v: number) => inrCompact(v)} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v}%`} />
                      <Tooltip contentStyle={{ background: 'var(--glass-fill-strong)', border: '1px solid var(--glass-border)', borderRadius: 12, fontSize: 12 }} formatter={(v: unknown) => [`${v}%`, 'Attendance']} labelFormatter={(v: unknown) => inr(Number(v))} />
                      <ReferenceLine x={rec.recommended_price} stroke="var(--accent)" strokeDasharray="4 3" label={{ value: 'Optimal', fill: 'var(--accent)', fontSize: 11, position: 'insideTopRight' }} />
                      <Area type="monotone" dataKey="attendance_pct" stroke="var(--accent)" strokeWidth={2.5} fill="url(#elg)" dot={false} />
                    </AreaChart></ResponsiveContainer></div>
                ) : <p className="t-callout text-tertiary">The ML model fell back to rules for this request, so no elasticity curve is available.</p>}
              </GlassCard>
            </motion.div>
          )}

          {!result && (
            <div className={styles.bento}>
              <GlassCard className={styles.wide} delay={0.05}>
                <div><h3 className={styles.title}>{catKey.charAt(0).toUpperCase() + catKey.slice(1)} price ladder</h3><p className={styles.sub}>Market benchmarks{cityMult != null ? ` · ${city} runs at ${cityMult}× the national level` : ''}</p></div>
                {bench ? <PriceLadder bench={bench} proposed={price && !errors.price ? priceN : null} recommended={null} /> : <Skeleton height={80} radius={14} />}
              </GlassCard>
              <GlassCard className={styles.wide} delay={0.1}>
                <div><h3 className={styles.title}>Price level by city</h3><p className={styles.sub}>{act ? `Where ${act.name} supports the highest ticket, starting from ${inr(priceN)}` : 'Choose an act to see how the same ticket prices across Indian cities.'}</p></div>
                {!act ? <EmptyState title="Pick an act" message="City price levels are shown for the act you choose." />
                  : !elasticity.data ? <Skeleton height={140} radius={14} />
                  : <div className={styles.bars} data-testid="city-bars">{curve.map(c => (
                    <div key={c.city} className={styles.barRow}><span className={styles.reason} style={{ color: 'var(--text-primary)' }}>{c.city}</span>
                      <div className={styles.barTrack}><motion.div className={styles.barFill} style={{ background: c.city === city ? 'var(--accent)' : 'var(--text-tertiary)' }} initial={{ width: 0 }} animate={{ width: `${(c.optimal_price / maxCurve) * 100}%` }} transition={{ duration: .6 }} /></div>
                      <span className="num-rounded" style={{ fontWeight: 600, textAlign: 'right' }}>{inrCompact(c.optimal_price)}</span></div>))}</div>}
              </GlassCard>
            </div>
          )}
        </div>
      </div>
      <ActPicker open={pickOpen} onClose={() => setPickOpen(false)} onPick={setAct} />
    </Page>
  );
}
