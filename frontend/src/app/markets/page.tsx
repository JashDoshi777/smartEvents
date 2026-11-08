'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import useSWRInfinite from 'swr/infinite';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, Building2, MapPin, Search } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented, ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { capacityLabel, compact, inrCompact, inr, num } from '@/lib/format';
import { Ring } from '@/components/insights/Ring';
import { CityIntelDetail, MarketCity, getCityRestaurants, getCityVenuesStrict, getExpansionGaps, getMarketCities, getMarketCityIntel } from '@/lib/api';
import { InfoSheet, Tag } from '@/components/ui/Provenance';
import styles from './page.module.css';

const isDerived = (c: MarketCity) => c.scores_basis === 'derived';
function DerivedExplain() {
  return (
    <>
      <p>Most cities have no hand-set market scores, so LiveIQ derives them from public counts. They are an estimate of how a city compares, not a measurement of demand.</p>
      <ul>
        <li><b>Nightlife, music, comedy, sports, arts.</b> Each score is the average percentile rank of the city across a few counts: bars, pubs and clubs, theatres, stadiums and venues mapped in OpenStreetMap, plus our own counts of events, venues and tracked acts based there. Zero stays zero.</li>
        <li><b>Youth share.</b> Census 2011 urban age tables for the city’s district(s), ages 18 to 35.</li>
        <li><b>Income.</b> The state’s per-capita GSDP divided by 12. It is a state-level proxy, not the city’s own income.</li>
      </ul>
      <p>The 12 original cities carry editorial scores set by hand. Derived and editorial scores are not equally precise, so compare them with care. None of this is Zomato District data.</p>
    </>
  );
}
function BasisTag({ c }: { c: MarketCity }) {
  if (!isDerived(c)) return null;
  return <Tag title="Derived scores" explain={<DerivedExplain />} testId="derived-tag">Derived</Tag>;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const tierName = (t: number | null | undefined) => (t ? `Tier ${t}` : 'Unclassified');
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

type MS = { label: string; cls: '' | 'monthHigh' | 'monthLow' | 'monthMonsoon'; h: number };
function monthState(m: number, peak: Set<number>, low: Set<number>, monsoon: Set<number>): MS {
  if (peak.has(m)) return { label: 'peak demand', cls: 'monthHigh', h: 40 };
  if (monsoon.has(m)) return { label: 'monsoon, outdoor risk', cls: 'monthMonsoon', h: 14 };
  if (low.has(m)) return { label: 'low demand', cls: 'monthLow', h: 20 };
  return { label: 'regular demand', cls: '', h: 28 };
}
function rangeLabel(ms: number[]) {
  const sorted = [...ms].sort((a, b) => a - b);
  // wrap-aware: find longest circular runs
  const set = new Set(sorted); const runs: number[][] = []; const seen = new Set<number>();
  for (const m of sorted) {
    if (seen.has(m)) continue;
    let start = m; while (set.has(((start + 10) % 12) + 1) && ((start + 10) % 12) + 1 !== m) start = ((start + 10) % 12) + 1;
    const run = [start]; seen.add(start); let cur = start;
    while (set.has((cur % 12) + 1) && !seen.has((cur % 12) + 1)) { cur = (cur % 12) + 1; run.push(cur); seen.add(cur); }
    runs.push(run);
  }
  return runs.map(r => r.length === 1 ? MONTHS[r[0] - 1] : `${MONTHS[r[0] - 1]} to ${MONTHS[r[r.length - 1] - 1]}`).join(', ');
}
function planner(peak: Set<number>, monsoon: Set<number>) {
  const p = peak.size ? `Best months to schedule: ${rangeLabel([...peak])}.` : 'No peak months on record for this city.';
  const m = monsoon.size ? ` Avoid outdoor shows in ${rangeLabel([...monsoon])} (monsoon).` : '';
  return p + m;
}

function Meter({ value, color, delay = 0 }: { value: number | null; color: string; delay?: number }) {
  return (
    <div className={styles.meter}>
      <motion.div className={styles.meterFill} style={{ background: color, opacity: .85 }} initial={{ width: 0 }} animate={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} transition={{ duration: .7, delay, ease: [0.22, 1, 0.36, 1] }} />
    </div>
  );
}

function CityRow({ c, rank, active, onSelect }: { c: MarketCity; rank: number; active: boolean; onSelect: () => void }) {
  const comp = c.scores?.composite ?? null;
  return (
    <motion.button
      type="button" data-testid={`city-${c.name}`} aria-pressed={active}
      className={`${styles.city} ${active ? styles.cityActive : ''}`}
      onClick={onSelect} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} whileTap={{ scale: .985 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30, delay: Math.min(rank, 10) * 0.02 }}
    >
      <span className={styles.rank} aria-label={`Rank ${rank}`}>{rank}</span>
      <div className={styles.cityName}>
        <p className={styles.cityTitle}>{c.name}{!c.active_on_district && <i className={styles.dot} aria-label="Expansion target" title="Expansion target" />}</p>
        <p className={styles.sub}>{c.state} · {tierName(c.tier)} · {c.active_on_district ? 'Live' : 'Expansion target'}{isDerived(c) && ' · Derived'}</p>
      </div>
      <span className={`${styles.cityScore} num-rounded`} style={isDerived(c) ? { color: 'var(--text-secondary)', fontStyle: 'italic' } : undefined} title={isDerived(c) ? 'Derived estimate' : undefined}>{comp != null ? `${isDerived(c) ? '~' : ''}${comp.toFixed(1)}` : '—'}</span>
    </motion.button>
  );
}

const REST_PAGE = 40;
function Restaurants({ city, counts }: { city: string; counts: Record<string, number> }) {
  const [type, setType] = useState('all');
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const { data, error, size, setSize, isValidating, mutate } = useSWRInfinite(
    i => ['restaurants', city, type, dq, i],
    ([, c, t, s, i]: [string, string, string, string, number]) => getCityRestaurants(c, { venue_type: t === 'all' ? undefined : t, q: s || undefined, limit: REST_PAGE, offset: i * REST_PAGE }),
    {},
  );
  const rows = useMemo(() => (data ?? []).flatMap(p => p.restaurants), [data]);
  const total = data?.[0]?.total ?? 0;
  const cityTotal = Object.values(counts).reduce((a, b) => a + b, 0);
  const loadingMore = isValidating && size > (data?.length ?? 0);
  const opts = [{ value: 'all', label: 'All', count: cityTotal }, ...['restaurant', 'cafe', 'bar', 'nightclub'].filter(t => (counts[t] ?? 0) > 0).map(t => ({ value: t, label: cap(t) + 's', count: counts[t] }))];

  return (
    <GlassCard className={styles.card} delay={0.1}>
      <div className={styles.cardHead}>
        <h3 className={styles.title}>Restaurant partnership engine</h3>
        <span className={styles.sub}>{num(cityTotal)} venues in {city}</span>
      </div>
      <p className={styles.sub}>Dining and nightlife venues from Foursquare and OpenStreetMap, candidates for event cross-promotion.</p>
      <ChipRow value={type} onChange={setType} options={opts} />
      <div className={styles.searchWrap}>
        <Search size={15} strokeWidth={1.75} className={styles.searchIcon} />
        <input className={`input ${styles.search}`} placeholder="Search by name" aria-label="Search venues" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      {error && !data ? <ErrorState onRetry={() => mutate()} />
        : !data ? <SkeletonRows rows={5} />
        : rows.length === 0 ? <EmptyState title="No venues found" message={dq ? `Nothing matches “${dq}” in ${city}.` : 'No venues synced for this filter.'} />
        : (
          <>
            <div className={styles.restList} data-testid="restaurant-list">
              {rows.map(r => (
                <div key={r.id} className={styles.restRow}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <p className={styles.rowTitle} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</p>
                    <p className={styles.sub} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {[r.venue_type && cap(r.venue_type), r.cuisines.slice(0, 2).join(', ') || null].filter(Boolean).join(' · ') || '—'}
                    </p>
                  </div>
                  {r.website && <a className={styles.link} href={r.website} target="_blank" rel="noopener noreferrer">Website</a>}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span className={styles.sub} data-testid="rest-count">Showing {num(rows.length)} of {num(total)}</span>
              {rows.length < total && <button className="btn btn-tinted btn-sm" disabled={loadingMore} onClick={() => setSize(size + 1)}>{loadingMore ? 'Loading…' : 'Show more'}</button>}
            </div>
          </>
        )}
    </GlassCard>
  );
}

function Venues({ city }: { city: string }) {
  const { data, error, isLoading, mutate } = useSWR(['city-venues', city], () => getCityVenuesStrict(city));
  const [vq, setVq] = useState('');
  const all = data?.venues ?? [];
  const venues = vq.trim() ? all.filter(v => v.name.toLowerCase().includes(vq.trim().toLowerCase())) : all;
  return (
    <GlassCard className={styles.card} delay={0.06}>
      <div className={styles.cardHead}><h3 className={styles.title}>Recommended venues</h3>{data && <span className={styles.sub}>{vq.trim() ? `${venues.length} of ${all.length}` : all.length} venues</span>}</div>
      {all.length > 8 && <div className={styles.searchWrap}><Search size={15} strokeWidth={1.75} className={styles.searchIcon} /><input className={`input ${styles.search}`} placeholder="Search venues by name" aria-label="Search city venues" value={vq} onChange={e => setVq(e.target.value)} /></div>}
      {error && !data ? <ErrorState onRetry={() => mutate()} />
        : isLoading && !data ? <SkeletonRows rows={3} />
        : venues.length === 0 ? <EmptyState icon={<Building2 size={32} strokeWidth={1.5} />} title={vq.trim() ? 'No venue matches' : 'No venues on file'} message={vq.trim() ? `Nothing named “${vq.trim()}” in ${city}.` : `No venues are tracked for ${city} yet.`} />
        : <div>
          {venues.map((v, i) => (
            <motion.div key={v.id ?? v.name} className={styles.venueRow} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <div style={{ minWidth: 0 }}>
                <p className={styles.rowTitle}>{v.name}</p>
                <p className={styles.sub}>{[v.type?.replace(/_/g, ' '), ...(v.categories ?? []).slice(0, 2)].filter(Boolean).join(' · ') || '—'}</p>
              </div>
              <div className={styles.venueStat}><p className="num-rounded" style={{ fontWeight: 600, ...(v.capacity ? {} : { color: 'var(--text-tertiary)', fontSize: '.8125rem' }) }}>{capacityLabel(v.capacity)}</p><p className={styles.sub}>capacity</p></div>
              <div className={`${styles.venueStat} ${styles.hideSm}`}><p className="num-rounded" style={{ fontWeight: 600 }}>{v.avg_fill_rate != null ? `${Math.round(v.avg_fill_rate * 100)}%` : 'Not tracked'}</p><p className={styles.sub}>avg fill</p></div>
              <div className={`${styles.venueStat} ${styles.hideSm}`}><p className="num-rounded" style={{ fontWeight: 600 }}>{inr(v.avg_ticket_price)}</p><p className={styles.sub}>avg ticket</p></div>
            </motion.div>
          ))}
        </div>}
    </GlassCard>
  );
}

function CityDetail({ city, onBack }: { city: MarketCity; onBack: () => void }) {
  const { data, error, isLoading, mutate } = useSWR<CityIntelDetail>(['city-intel', city.name], () => getMarketCityIntel(city.name));
  const intel = data?.intelligence;
  const fm = data?.festival_months;
  const peak = new Set(fm?.high_demand ?? city.festival_months?.high_demand ?? []);
  const low = new Set(fm?.low_demand ?? city.festival_months?.low_demand ?? []);
  const monsoon = new Set(data?.monsoon_months ?? city.monsoon_months ?? []);
  const s = city.scores;
  const scoreRows: [string, number | null][] = [['Music', s.music_market], ['Nightlife', s.nightlife], ['Comedy', s.comedy_market], ['Sports', s.sports_affinity], ['Arts & culture', s.arts_culture]];

  return (
    <div className={styles.detail}>
      <button className={`${styles.back}`} onClick={onBack}><ArrowLeft size={16} strokeWidth={1.75} /> Markets</button>
      <div>
        <h2 className={styles.cityHead} data-testid="detail-title">{city.name}</h2>
        <p className={styles.sub}>{city.state} · {tierName(city.tier)} · {city.active_on_district ? 'District live' : 'Expansion target'}</p>
        {isDerived(city) && <div style={{ marginTop: 6 }}><BasisTag c={city} /></div>}
      </div>

      <GlassCard className={styles.stats}>
        <div className={styles.statRing}>
          <Ring value={s.composite} size={96} stroke={11} color="var(--text-primary)"><span className={`${styles.ringNum} num-rounded`}>{s.composite != null ? s.composite.toFixed(1) : '—'}</span></Ring>
          <span className={styles.sub}>Composite</span>
        </div>
        {[
          { l: 'Metro population', v: compact(city.metro_population ?? city.population) },
          { l: city.income_basis === 'state_proxy' ? 'State income proxy / month' : 'Avg monthly income', v: inrCompact(city.avg_monthly_income) },
          { l: 'Youth share', v: city.youth_population_pct != null ? `${city.youth_population_pct}%` : '—' },
        ].map(t => (
          <div key={t.l} className={styles.stat}><span className={`${styles.statVal} num-rounded`}>{t.v}</span><span className={styles.sub}>{t.l}</span></div>
        ))}
      </GlassCard>

      {error && !data ? <GlassCard className={styles.card}><ErrorState message="Couldn’t load the intelligence report for this city." onRetry={() => mutate()} /></GlassCard>
        : isLoading && !data ? <Skeleton height={70} radius={20} />
        : intel && (
          <GlassCard className={styles.card}>
            <h3 className={styles.title}>{city.active_on_district ? 'District is live here' : 'Expansion recommendation'}</h3>
            <p className={styles.body}>{!city.active_on_district && <i className={styles.dot} style={{ marginRight: 8 }} />}{intel.expansion_recommendation}</p>
          </GlassCard>
        )}

      <GlassCard className={styles.card} delay={0.04}>
        <div className={styles.cardHead}><h3 className={styles.title}>Demand</h3>{isDerived(city) ? <BasisTag c={city} /> : <span className={styles.sub}>Editorial</span>}</div>
        <div className={styles.scoreGrid}>
          {scoreRows.map(([l, v], i) => (
            <div key={l} className={styles.scoreRow}>
              <div className={styles.scoreTop}><span className={styles.body}>{l}</span><span className="num-rounded" style={{ fontWeight: 600 }}>{v ?? '—'}</span></div>
              <Meter value={v} color="var(--text-primary)" delay={i * 0.06} />
            </div>
          ))}
        </div>
        {isDerived(city) && <p className={styles.sub} data-testid="derived-footnote">Derived from public venue counts and our own data. An estimate of relative scale, not measured demand.</p>}
        {(city.top_categories ?? []).length > 0 && <p className={styles.sub}>Top categories: {city.top_categories!.map(c => c.replace(/_/g, ' ')).join(' · ')}</p>}
      </GlassCard>

      {intel && (
        <GlassCard className={styles.card} delay={0.05}>
          <div className={styles.cardHead}><h3 className={styles.title}>Seasonality</h3><span className={styles.sub}>{intel.income_tier} income · {intel.youth_index} youth index</span></div>
          <div className={styles.months} aria-label="Demand by month" data-testid="season-strip">
            {MONTHS.map((m, i) => {
              const st = monthState(i + 1, peak, low, monsoon);
              return (
                <div key={m} className={styles.monthCol} title={`${m}: ${st.label}`}>
                  <i className={`${styles.monthBar} ${st.cls ? styles[st.cls] : ''}`} style={{ height: st.h }} aria-label={`${m}: ${st.label}`} />
                  <span>{m[0]}</span>
                </div>
              );
            })}
          </div>
          <div className={styles.legendRow}><span><i className={`${styles.swatch} ${styles.monthHigh}`} /> Peak</span><span><i className={styles.swatch} /> Regular</span><span><i className={`${styles.swatch} ${styles.monthLow}`} /> Low</span><span><i className={`${styles.swatch} ${styles.monthMonsoon}`} /> Monsoon</span></div>
          <p className={styles.body} data-testid="best-months">{planner(peak, monsoon)}</p>
        </GlassCard>
      )}

      <Venues key={`v-${city.name}`} city={city.name} />
      {intel ? <Restaurants key={`r-${city.name}`} city={city.name} counts={intel.venue_counts_by_type ?? {}} /> : null}
    </div>
  );
}

const SCORE_DIMS: { key: keyof MarketCity['scores']; label: string }[] = [
  { key: 'composite', label: 'Composite' }, { key: 'music_market', label: 'Music' }, { key: 'nightlife', label: 'Nightlife' },
  { key: 'comedy_market', label: 'Comedy' }, { key: 'sports_affinity', label: 'Sports' }, { key: 'arts_culture', label: 'Arts & culture' },
];

function CompareView({ cities, a, b, setA, setB }: { cities: MarketCity[]; a: string; b: string; setA: (v: string) => void; setB: (v: string) => void }) {
  const A = cities.find(c => c.name === a), B = cities.find(c => c.name === b);
  const rows: { label: string; va: number | null; vb: number | null; fmt: (n: number | null) => string }[] = [
    ...SCORE_DIMS.map(d => ({ label: d.label, va: A?.scores[d.key] ?? null, vb: B?.scores[d.key] ?? null, fmt: (n: number | null) => (n == null ? '—' : n.toFixed(d.key === 'composite' ? 1 : 0)) })),
    { label: 'Metro population', va: A?.metro_population ?? A?.population ?? null, vb: B?.metro_population ?? B?.population ?? null, fmt: (n: number | null) => compact(n) },
    { label: 'Avg monthly income', va: A?.avg_monthly_income ?? null, vb: B?.avg_monthly_income ?? null, fmt: (n: number | null) => inrCompact(n) },
    { label: 'Youth share', va: A?.youth_population_pct ?? null, vb: B?.youth_population_pct ?? null, fmt: (n: number | null) => (n == null ? '—' : `${n}%`) },
  ];
  const wins = rows.reduce((acc, r) => { if (r.va != null && r.vb != null && r.va !== r.vb) acc[r.va > r.vb ? 0 : 1]++; return acc; }, [0, 0]);
  const opt = cities.map(c => <option key={c.name} value={c.name}>{c.name}</option>);
  return (
    <div className={styles.detail} data-testid="compare-view">
      <div><h2 className={styles.cityHead}>Compare markets</h2><p className={styles.sub}>Side-by-side demand scores, size and income.</p></div>
      <div className={styles.cmpPick}>
        <select className={`input ${styles.sel}`} aria-label="First city" value={a} onChange={e => setA(e.target.value)}>{opt}</select>
        <select className={`input ${styles.sel}`} aria-label="Second city" value={b} onChange={e => setB(e.target.value)}>{opt}</select>
      </div>
      {A && B && a === b ? <GlassCard className={styles.card}><EmptyState title="Pick two different cities" message="Choose a second city to compare against." /></GlassCard> : A && B && (
        <>
          <GlassCard className={styles.card}>
            <div className={styles.cmpRow} style={{ borderBottom: 0 }}>
              <div className={styles.cmpSide}><b className={styles.cityHead} style={{ fontSize: '1.25rem' }}>{A.name}</b><span className={styles.sub}>{tierName(A.tier)} · {A.active_on_district ? 'Live' : 'Target'}{isDerived(A) && ' · Derived'}</span></div>
              <span className={styles.cmpLabel} data-testid="cmp-wins">{wins[0]} : {wins[1]}</span>
              <div className={`${styles.cmpSide} ${styles.right}`}><b className={styles.cityHead} style={{ fontSize: '1.25rem' }}>{B.name}</b><span className={styles.sub}>{tierName(B.tier)} · {B.active_on_district ? 'Live' : 'Target'}{isDerived(B) && ' · Derived'}</span></div>
            </div>
          </GlassCard>
          <GlassCard className={styles.card}>
            {rows.map(r => {
              const aw = r.va != null && r.vb != null && r.va > r.vb, bw = r.va != null && r.vb != null && r.vb > r.va;
              const max = Math.max(r.va ?? 0, r.vb ?? 0, 1);
              return (
                <div key={r.label} className={styles.cmpRow} data-testid={`cmp-${r.label}`}>
                  <div className={styles.cmpSide}><span className={`${styles.cmpVal} num-rounded ${aw ? styles.cmpWin : ''}`}>{r.fmt(r.va)}</span><Meter value={r.va != null ? (r.va / max) * 100 : 0} color={aw ? 'var(--text-primary)' : 'var(--text-tertiary)'} /></div>
                  <span className={styles.cmpLabel}>{r.label}</span>
                  <div className={`${styles.cmpSide} ${styles.right}`}><span className={`${styles.cmpVal} num-rounded ${bw ? styles.cmpWin : ''}`}>{r.fmt(r.vb)}</span><Meter value={r.vb != null ? (r.vb / max) * 100 : 0} color={bw ? 'var(--text-primary)' : 'var(--text-tertiary)'} /></div>
                </div>
              );
            })}
          </GlassCard>
        </>
      )}
    </div>
  );
}

function ExpansionView({ cities, onOpen }: { cities: MarketCity[]; onOpen: (name: string) => void }) {
  const gaps = useSWR('expansion-gaps', getExpansionGaps);
  const byName = useMemo(() => new Map(cities.map(c => [c.name, c])), [cities]);
  const avg = useMemo(() => {
    const out: Partial<Record<keyof MarketCity['scores'], number>> = {};
    for (const d of SCORE_DIMS) { const v = cities.map(c => c.scores[d.key]).filter((x): x is number => x != null); if (v.length) out[d.key] = v.reduce((a, b) => a + b, 0) / v.length; }
    return out;
  }, [cities]);
  const drivers = (c?: MarketCity) => !c ? [] : SCORE_DIMS.filter(d => d.key !== 'composite').map(d => ({ label: d.label, delta: (c.scores[d.key] ?? 0) - (avg[d.key] ?? 0) })).sort((x, y) => y.delta - x.delta).slice(0, 2).filter(d => d.delta > 0);
  return (
    <div className={styles.detail} data-testid="expansion-view">
      <div><h2 className={styles.cityHead}>Expansion scorecard</h2><p className={styles.sub}>Cities where District is not live, ranked by opportunity.</p>
        <p className={styles.sub} style={{ display: 'flex', alignItems: 'center', gap: 6 }} data-testid="basis-note">Basis: mostly derived market scores and state-level income <InfoSheet title="Scorecard basis"><DerivedExplain /></InfoSheet></p></div>
      <GlassCard className={styles.card}>
        {gaps.error && !gaps.data ? <ErrorState onRetry={() => gaps.mutate()} />
          : !gaps.data ? <SkeletonRows rows={5} />
          : gaps.data.gaps.length === 0 ? <EmptyState title="No expansion targets" message="District is live in every tracked city with a strong market score." />
          : gaps.data.gaps.map(g => {
            const c = byName.get(g.city); const dr = drivers(c);
            return (
              <button key={g.city} type="button" className={styles.expRow} data-testid={`exp-${g.city}`} onClick={() => onOpen(g.city)}>
                <span className={styles.rank}>{g.rank}</span>
                <div style={{ minWidth: 0 }}>
                  <p className={styles.rowTitle} style={{ fontWeight: 600 }}>{g.city} <span className={styles.sub}>· {g.state} · {tierName(g.tier)}</span></p>
                  <p className={styles.sub}>{byName.get(g.city) && isDerived(byName.get(g.city)!) ? 'Derived market score ~' : 'Market score '}{g.composite_market_score} · {compact(g.population)} people · {inrCompact(g.avg_monthly_income)} avg income</p>
                  <div className={styles.chips}>{dr.length ? dr.map(d => <span key={d.label} className={styles.chipSm}>{d.label} +{d.delta.toFixed(0)} vs avg</span>) : <span className={styles.chipSm}>Close to the average</span>}</div>
                </div>
                <div style={{ textAlign: 'right' }}><span className="num-rounded" style={{ fontSize: '1.375rem', fontWeight: 600 }}>{g.opportunity_score.toFixed(0)}</span><p className={styles.sub}>opportunity</p></div>
              </button>
            );
          })}
        {gaps.data && <p className={styles.sub}>{gaps.data.methodology}. Opportunity = market score x metro population (per 10M). Drivers show the two dimensions furthest above the all-city average.</p>}
      </GlassCard>
    </div>
  );
}

type Mode = 'explore' | 'compare' | 'expansion';

function MarketsInner() {
  const { data, error, isLoading, mutate } = useSWR('market-cities', getMarketCities);
  const params = useSearchParams();   // deep link: /markets?city=Pune
  const [sel, setSel] = useState<string | null>(() => params.get('city'));
  const [mobileDetail, setMobileDetail] = useState(() => !!params.get('city'));
  const [q, setQ] = useState('');
  const [tier, setTier] = useState('all');
  const [status, setStatus] = useState<'all' | 'live' | 'target'>('all');
  const [group, setGroup] = useState<'tier' | 'rank'>('tier');
  const [mode, setMode] = useState<Mode>('explore');
  const [cmp, setCmp] = useState<[string, string]>(['', '']);

  useEffect(() => { if (sel) window.history.replaceState(null, '', `?city=${encodeURIComponent(sel)}`); }, [sel]);

  const cities = useMemo(() => [...(data?.cities ?? [])].sort((a, b) => (b.scores?.composite ?? 0) - (a.scores?.composite ?? 0) || a.name.localeCompare(b.name)), [data]);
  const rankOf = useMemo(() => new Map(cities.map((c, i) => [c.name, i + 1])), [cities]);
  const tiers = useMemo(() => [...new Set(cities.map(c => c.tier ?? 0))].sort((a, b) => (a || 99) - (b || 99)), [cities]);
  const filtered = cities.filter(c =>
    (tier === 'all' || String(c.tier ?? 0) === tier) &&
    (status === 'all' || (status === 'live') === c.active_on_district) &&
    (!q.trim() || `${c.name} ${c.state}`.toLowerCase().includes(q.trim().toLowerCase())));
  const sections = useMemo(() => {
    if (group === 'rank') return [{ key: 'all', title: null as string | null, items: filtered }];
    return tiers.map(t => ({ key: String(t), title: tierName(t), items: filtered.filter(c => (c.tier ?? 0) === t) })).filter(s => s.items.length);
  }, [filtered, group, tiers]);
  const selected = cities.find(c => c.name.toLowerCase() === sel?.toLowerCase()) ?? (cities[0] ?? null);
  const targets = cities.filter(c => !c.active_on_district).length;
  const a = cmp[0] || cities[0]?.name || '', b = cmp[1] || cities[1]?.name || '';

  return (
    <Page fill title="City Markets" subtitle={cities.length ? `${cities.length} Indian cities · ${targets} expansion targets` : 'Demand, venues and restaurant partnerships'}>
      <div className={`${styles.layout} ${mobileDetail ? styles.showDetail : ''}`}>
        <aside className={styles.listPane}>
          <div className={styles.listTop}>
            <div className={styles.searchWrap}>
              <Search size={15} strokeWidth={1.75} className={styles.searchIcon} />
              <input className={`input ${styles.search}`} placeholder="Search cities" aria-label="Search cities" value={q} onChange={e => setQ(e.target.value)} />
            </div>
            <div className={styles.filters}>
              <div style={{ width: '100%' }} role="group" aria-label="Tier"><ChipRow value={tier} onChange={setTier} options={[{ value: 'all', label: 'All tiers' }, ...tiers.map(t => ({ value: String(t), label: tierName(t) }))]} /></div>
              <Segmented value={status} onChange={setStatus} ariaLabel="Status" options={[{ value: 'all', label: 'Any' }, { value: 'live', label: 'Live' }, { value: 'target', label: 'Targets' }]} />
              <Segmented value={group} onChange={setGroup} ariaLabel="Sort" options={[{ value: 'tier', label: 'By tier' }, { value: 'rank', label: 'Ranked' }]} />
            </div>
            <div className={styles.filters}>
              <Segmented value={mode} onChange={m => { setMode(m); setMobileDetail(m !== 'explore' || mobileDetail); }} ariaLabel="View" options={[{ value: 'explore', label: 'Explore' }, { value: 'compare', label: 'Compare' }, { value: 'expansion', label: 'Expansion' }]} />
            </div>
          </div>
          <div className={styles.list}>
            {error && !data ? <ErrorState message="Couldn’t load the cities." onRetry={() => mutate()} />
              : isLoading && !data ? Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} height={56} radius={12} />)
              : filtered.length === 0 ? <EmptyState icon={<Building2 size={32} strokeWidth={1.5} />} title="No cities match" message="Try a different search or filter." />
              : <>{sections.map(sec => (
                <div key={sec.key} data-testid={`section-${sec.key}`}>
                  {sec.title && <div className={styles.sectionHead}><span>{sec.title}</span><span>{sec.items.length}</span></div>}
                  {sec.items.map(c => (
                    <CityRow key={c.name} c={c} rank={rankOf.get(c.name) ?? 0} active={mode === 'explore' && selected?.name === c.name} onSelect={() => { setSel(c.name); setMode('explore'); setMobileDetail(true); }} />
                  ))}
                </div>
              ))}
              {cities.some(isDerived) && <p className={styles.sub} style={{ padding: '10px 14px 18px' }} data-testid="derived-legend">{group === 'rank' ? 'Ranked mixes editorial and derived (~, italic) scores, which are not equally precise. ' : '~ and Derived mark scores estimated from public counts. '}<span style={{ display: 'inline-flex', verticalAlign: 'middle' }}><InfoSheet title="Derived scores" label="About derived scores"><DerivedExplain /></InfoSheet></span></p>}</>}
          </div>
        </aside>
        <section className={styles.detailPane} aria-live="polite">
          {mode !== 'explore' && <button className={styles.back} onClick={() => { setMobileDetail(false); setMode('explore'); }}><ArrowLeft size={16} strokeWidth={1.75} /> Markets</button>}
          {mode === 'compare' && cities.length > 1 ? <CompareView cities={cities} a={a} b={b} setA={v => setCmp([v, b])} setB={v => setCmp([a, v])} />
            : mode === 'expansion' ? <ExpansionView cities={cities} onOpen={n => { setSel(n); setMode('explore'); setMobileDetail(true); }} />
            : selected
            ? <AnimatePresence mode="wait"><motion.div key={selected.name} initial={{ opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ type: 'spring', stiffness: 260, damping: 30 }}>
              <CityDetail city={selected} onBack={() => setMobileDetail(false)} />
            </motion.div></AnimatePresence>
            : isLoading ? <Skeleton height={300} radius={22} /> : <EmptyState icon={<MapPin size={36} strokeWidth={1.5} />} title="Select a market" message="Pick a city to see demand, venues and partnership candidates." />}
        </section>
      </div>
    </Page>
  );
}

export default function MarketsPage() {
  return <Suspense fallback={null}><MarketsInner /></Suspense>;
}
