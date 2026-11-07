'use client';

import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, Building2, MapPin, Search } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented, ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { compact, inr, inrCompact, num } from '@/lib/format';
import { Ring } from '@/components/insights/Ring';
import { CityIntelDetail, MarketCity, getCityRestaurants, getCityVenuesStrict, getMarketCities, getMarketCityIntel } from '@/lib/api';
import styles from './page.module.css';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const tone = (s: number | null | undefined) => (s == null ? 'var(--text-tertiary)' : 'var(--text-primary)');
const tierLabel = (t: number) => `Tier ${t}`;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

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
      <div className={styles.cityName}>
        <p className={styles.cityTitle}>{c.name}{!c.active_on_district && <i className={styles.dot} aria-label="Expansion target" title="Expansion target" />}</p>
        <p className={styles.sub}>{c.state} · Tier {c.tier} · {c.active_on_district ? 'Live' : 'Expansion target'}</p>
      </div>
      <span className={`${styles.cityScore} num-rounded`}>{comp != null ? comp.toFixed(1) : '—'}</span>
    </motion.button>
  );
}

function Restaurants({ city, counts }: { city: string; counts: Record<string, number> }) {
  const [type, setType] = useState('all');
  const [q, setQ] = useState('');
  const [shown, setShown] = useState(40);
  useEffect(() => { setType('all'); setQ(''); setShown(40); }, [city]);
  const { data, error, isLoading, mutate } = useSWR(['restaurants', city, type], () => getCityRestaurants(city, { venue_type: type === 'all' ? undefined : type, limit: 200 }));
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const needle = q.trim().toLowerCase();
  const rows = useMemo(() => (data?.restaurants ?? []).filter(r =>
    !needle || r.name.toLowerCase().includes(needle) || r.cuisines.some(c => c.toLowerCase().includes(needle)) || (r.address ?? '').toLowerCase().includes(needle)), [data, needle]);
  const typeTotal = type === 'all' ? total : counts[type] ?? 0;
  const opts = [{ value: 'all', label: 'All', count: total }, ...['restaurant', 'cafe', 'bar', 'nightclub'].filter(t => (counts[t] ?? 0) > 0).map(t => ({ value: t, label: cap(t) + 's', count: counts[t] }))];

  return (
    <GlassCard className={styles.card} delay={0.1}>
      <div className={styles.cardHead}>
        <h3 className={styles.title}>Restaurant partnership engine</h3>
        <span className={styles.sub}>{num(total)} venues in {city}</span>
      </div>
      <p className={styles.sub}>Dining and nightlife venues from Foursquare and OpenStreetMap, candidates for event cross-promotion.</p>
      <ChipRow value={type} onChange={t => { setType(t); setShown(40); }} options={opts} />
      <div className={styles.searchWrap}>
        <Search size={15} strokeWidth={1.75} className={styles.searchIcon} />
        <input className={`input ${styles.search}`} placeholder="Search name, cuisine or area" aria-label="Search venues" value={q} onChange={e => { setQ(e.target.value); setShown(40); }} />
      </div>
      {error && !data ? <ErrorState onRetry={() => mutate()} />
        : isLoading && !data ? <SkeletonRows rows={5} />
        : rows.length === 0 ? <EmptyState title="No venues found" message={needle ? `Nothing matches “${q}” in the first ${data?.restaurants.length ?? 0} listings.` : 'No venues synced for this filter.'} />
        : (
          <>
            <div className={styles.restList} data-testid="restaurant-list">
              {rows.slice(0, shown).map(r => (
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
              <span className={styles.sub}>Showing {Math.min(shown, rows.length)} of {num(rows.length)}{!needle && typeTotal > rows.length ? ` loaded (${num(typeTotal)} total, alphabetical)` : ''}</span>
              {shown < rows.length && <button className="btn btn-tinted btn-sm" onClick={() => setShown(s => s + 40)}>Show more</button>}
            </div>
          </>
        )}
    </GlassCard>
  );
}

function Venues({ city }: { city: string }) {
  const { data, error, isLoading, mutate } = useSWR(['city-venues', city], () => getCityVenuesStrict(city));
  const venues = data?.venues ?? [];
  return (
    <GlassCard className={styles.card} delay={0.06}>
      <div className={styles.cardHead}><h3 className={styles.title}>Recommended venues</h3>{data && <span className={styles.sub}>{venues.length} venues</span>}</div>
      {error && !data ? <ErrorState onRetry={() => mutate()} />
        : isLoading && !data ? <SkeletonRows rows={3} />
        : venues.length === 0 ? <EmptyState icon={<Building2 size={32} strokeWidth={1.5} />} title="No venues on file" message={`No venues are tracked for ${city} yet.`} />
        : <div>
          {venues.map((v, i) => (
            <motion.div key={v.id ?? v.name} className={styles.venueRow} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <div style={{ minWidth: 0 }}>
                <p className={styles.rowTitle}>{v.name}</p>
                <p className={styles.sub}>{[v.type?.replace(/_/g, ' '), ...(v.categories ?? []).slice(0, 2)].filter(Boolean).join(' · ') || '—'}</p>
              </div>
              <div className={styles.venueStat}><p className="num-rounded" style={{ fontWeight: 600 }}>{num(v.capacity)}</p><p className={styles.sub}>capacity</p></div>
              <div className={`${styles.venueStat} ${styles.hideSm}`}><p className="num-rounded" style={{ fontWeight: 600 }}>{v.avg_fill_rate != null ? `${Math.round(v.avg_fill_rate * 100)}%` : '—'}</p><p className={styles.sub}>avg fill</p></div>
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
  const peak = new Set(fm?.high_demand ?? []);
  const low = new Set(fm?.low_demand ?? []);
  const s = city.scores;
  const scoreRows: [string, number | null][] = [['Music', s.music_market], ['Nightlife', s.nightlife], ['Comedy', s.comedy_market], ['Sports', s.sports_affinity], ['Arts & culture', s.arts_culture]];

  return (
    <div className={styles.detail}>
      <button className={`${styles.back}`} onClick={onBack}><ArrowLeft size={16} strokeWidth={1.75} /> Markets</button>
      <div>
        <h2 className={styles.cityHead} data-testid="detail-title">{city.name}</h2>
        <p className={styles.sub}>{city.state} · Tier {city.tier} · {city.active_on_district ? 'District live' : 'Expansion target'}</p>
      </div>

      <GlassCard className={styles.stats}>
        <div className={styles.statRing}>
          <Ring value={s.composite} size={96} stroke={11} color="var(--text-primary)"><span className={`${styles.ringNum} num-rounded`}>{s.composite != null ? s.composite.toFixed(1) : '—'}</span></Ring>
          <span className={styles.sub}>Composite</span>
        </div>
        {[
          { l: 'Metro population', v: compact(city.metro_population ?? city.population) },
          { l: 'Avg monthly income', v: inrCompact(city.avg_monthly_income) },
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
        <h3 className={styles.title}>Demand</h3>
        <div className={styles.scoreGrid}>
          {scoreRows.map(([l, v], i) => (
            <div key={l} className={styles.scoreRow}>
              <div className={styles.scoreTop}><span className={styles.body}>{l}</span><span className="num-rounded" style={{ fontWeight: 600 }}>{v ?? '—'}</span></div>
              <Meter value={v} color="var(--text-primary)" delay={i * 0.06} />
            </div>
          ))}
        </div>
        {(city.top_categories ?? []).length > 0 && <p className={styles.sub}>Top categories: {city.top_categories!.map(c => c.replace(/_/g, ' ')).join(' · ')}</p>}
      </GlassCard>

      {intel && (
        <GlassCard className={styles.card} delay={0.05}>
          <div className={styles.cardHead}><h3 className={styles.title}>Seasonality</h3><span className={styles.sub}>{intel.income_tier} income · {intel.youth_index} youth index</span></div>
          <div className={styles.months} aria-label="Demand by month">
            {MONTHS.map((m, i) => (
              <div key={m} className={styles.monthCol}>
                <i className={`${styles.monthBar} ${peak.has(i + 1) ? styles.monthHigh : low.has(i + 1) ? styles.monthLow : ''}`} />
                <span>{m[0]}</span>
              </div>
            ))}
          </div>
          <p className={styles.sub}>Highlighted months are peak demand, faint months are low. {intel.monsoon_risk.replace(/[\[\]']/g, '')}</p>
        </GlassCard>
      )}

      <Venues city={city.name} />
      {intel ? <Restaurants city={city.name} counts={intel.venue_counts_by_type ?? {}} /> : null}
    </div>
  );
}

export default function MarketsPage() {
  const { data, error, isLoading, mutate } = useSWR('market-cities', getMarketCities);
  const [sel, setSel] = useState<string | null>(null);
  const [mobileDetail, setMobileDetail] = useState(false);
  const [q, setQ] = useState('');
  const [tier, setTier] = useState('all');
  const [status, setStatus] = useState<'all' | 'live' | 'target'>('all');

  const cities = useMemo(() => [...(data?.cities ?? [])].sort((a, b) => (b.scores?.composite ?? 0) - (a.scores?.composite ?? 0)), [data]);
  const filtered = cities.filter(c =>
    (tier === 'all' || String(c.tier) === tier) &&
    (status === 'all' || (status === 'live') === c.active_on_district) &&
    (!q.trim() || `${c.name} ${c.state}`.toLowerCase().includes(q.trim().toLowerCase())));
  const selected = cities.find(c => c.name === sel) ?? (cities[0] ?? null);
  const targets = cities.filter(c => !c.active_on_district).length;

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
              <Segmented value={tier} onChange={setTier} ariaLabel="Tier" options={[{ value: 'all', label: 'All' }, { value: '1', label: 'Tier 1' }, { value: '2', label: 'Tier 2' }, { value: '3', label: 'Tier 3' }]} />
              <Segmented value={status} onChange={setStatus} ariaLabel="Status" options={[{ value: 'all', label: 'Any' }, { value: 'live', label: 'Live' }, { value: 'target', label: 'Targets' }]} />
            </div>
          </div>
          <div className={styles.list}>
            {error && !data ? <ErrorState message="Couldn’t load the cities." onRetry={() => mutate()} />
              : isLoading && !data ? Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} height={56} radius={12} />)
              : filtered.length === 0 ? <EmptyState icon={<Building2 size={32} strokeWidth={1.5} />} title="No cities match" message="Try a different search or filter." />
              : <AnimatePresence initial={false}>{filtered.map(c => (
                <CityRow key={c.name} c={c} rank={cities.indexOf(c) + 1} active={selected?.name === c.name} onSelect={() => { setSel(c.name); setMobileDetail(true); }} />
              ))}</AnimatePresence>}
          </div>
        </aside>
        <section className={styles.detailPane} aria-live="polite">
          {selected
            ? <AnimatePresence mode="wait"><motion.div key={selected.name} initial={{ opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ type: 'spring', stiffness: 260, damping: 30 }}>
              <CityDetail city={selected} onBack={() => setMobileDetail(false)} />
            </motion.div></AnimatePresence>
            : isLoading ? <Skeleton height={300} radius={22} /> : <EmptyState icon={<MapPin size={36} strokeWidth={1.5} />} title="Select a market" message="Pick a city to see demand, venues and partnership candidates." />}
        </section>
      </div>
    </Page>
  );
}
