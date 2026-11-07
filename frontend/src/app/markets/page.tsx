'use client';

import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, Building2, CloudRain, Landmark, MapPin, Rocket, Search, Sparkles, Store, Users } from 'lucide-react';
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
const tone = (s: number | null | undefined) => (s == null ? 'var(--text-tertiary)' : 'var(--accent)');
const tierLabel = (t: number) => `Tier ${t}`;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function Meter({ value, color, delay = 0 }: { value: number | null; color: string; delay?: number }) {
  return (
    <div className={styles.meter}>
      <motion.div className={styles.meterFill} style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} transition={{ duration: .7, delay, ease: [0.22, 1, 0.36, 1] }} />
    </div>
  );
}

function CityRow({ c, rank, active, onSelect }: { c: MarketCity; rank: number; active: boolean; onSelect: () => void }) {
  const comp = c.scores?.composite ?? null;
  return (
    <motion.button
      type="button" layout="position" data-testid={`city-${c.name}`} aria-pressed={active}
      className={`${styles.city} ${active ? styles.cityActive : ''} ${!c.active_on_district ? styles.cityTarget : ''}`}
      onClick={onSelect} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .3, delay: Math.min(rank, 10) * 0.025 }}
    >
      <div className={styles.cityTop}>
        <span className={styles.rank}>{rank}</span>
        <div className={styles.cityName}>
          <p className="t-callout" style={{ fontWeight: 650 }}>{c.name}</p>
          <p className="t-caption text-tertiary">{c.state} · {compact(c.metro_population ?? c.population)} metro</p>
        </div>
        <span className={`${styles.cityScore} tnum`} style={{ color: 'var(--text-primary)' }}>{comp != null ? comp.toFixed(1) : '—'}</span>
      </div>
      <Meter value={comp} color={tone(comp)} />
      <div className={styles.cityMeta}>
        <span className="badge badge-neutral">{tierLabel(c.tier)}</span>
        {c.active_on_district
          ? <span className="badge badge-neutral">District live</span>
          : <span className="badge badge-amber"><Rocket size={11} /> Expansion target</span>}
      </div>
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
        <div className={styles.cardTitle}><Store size={16} color="var(--text-secondary)" /><h3 className="t-headline">Restaurant partnership engine</h3></div>
        <span className="badge badge-neutral tnum">{num(total)} venues in {city}</span>
      </div>
      <p className="t-footnote text-secondary">Dining and nightlife venues from Foursquare and OpenStreetMap — candidates for event cross-promotion.</p>
      <ChipRow value={type} onChange={t => { setType(t); setShown(40); }} options={opts} />
      <div className={styles.searchWrap}>
        <Search size={15} className={styles.searchIcon} />
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
                  <div className={styles.avatar} style={{ background: 'var(--fill-tertiary)', color: 'var(--text-secondary)' }}>{r.name.charAt(0).toUpperCase()}</div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <p className="t-callout" style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</p>
                    <p className="t-caption text-tertiary" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {[r.venue_type && cap(r.venue_type), r.cuisines.slice(0, 2).join(', ') || null].filter(Boolean).join(' · ') || '—'}
                    </p>
                  </div>
                  {r.website && <a className="btn btn-ghost btn-sm" href={r.website} target="_blank" rel="noopener noreferrer">Website</a>}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span className={styles.note}>Showing {Math.min(shown, rows.length)} of {num(rows.length)}{!needle && typeTotal > rows.length ? ` loaded (${num(typeTotal)} total, alphabetical)` : ''}</span>
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
      <div className={styles.cardHead}>
        <div className={styles.cardTitle}><Landmark size={16} color="var(--text-secondary)" /><h3 className="t-headline">Recommended venues</h3></div>
        {data && <span className="t-caption text-tertiary">{venues.length} venues</span>}
      </div>
      {error && !data ? <ErrorState onRetry={() => mutate()} />
        : isLoading && !data ? <SkeletonRows rows={3} />
        : venues.length === 0 ? <EmptyState icon={<Landmark size={32} strokeWidth={1.4} />} title="No venues on file" message={`No venues are tracked for ${city} yet.`} />
        : <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {venues.map(v => (
            <div key={v.id ?? v.name} className={styles.venueRow}>
              <div style={{ minWidth: 0 }}>
                <p className="t-callout" style={{ fontWeight: 600 }}>{v.name}</p>
                <p className="t-caption text-tertiary">{[v.type?.replace(/_/g, ' '), ...(v.categories ?? []).slice(0, 2)].filter(Boolean).join(' · ') || '—'}</p>
              </div>
              <div className={styles.venueStat}><p className="t-callout tnum" style={{ fontWeight: 650 }}>{num(v.capacity)}</p><p className="t-caption text-tertiary">capacity</p></div>
              <div className={`${styles.venueStat} ${styles.hideSm}`}><p className="t-callout tnum" style={{ fontWeight: 650 }}>{v.avg_fill_rate != null ? `${Math.round(v.avg_fill_rate * 100)}%` : '—'}</p><p className="t-caption text-tertiary">avg fill</p></div>
              <div className={`${styles.venueStat} ${styles.hideSm}`}><p className="t-callout tnum" style={{ fontWeight: 650 }}>{inr(v.avg_ticket_price)}</p><p className="t-caption text-tertiary">avg ticket</p></div>
            </div>
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
      <button className={`btn btn-ghost btn-sm ${styles.back}`} onClick={onBack}><ArrowLeft size={14} /> All markets</button>
      <div className={styles.dHead}>
        
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 className="t-title1" data-testid="detail-title">{city.name}</h2>
          <p className="t-callout text-secondary">{city.state}, India</p>
        </div>
        <div className={styles.chips}>
          <span className="badge badge-neutral">{tierLabel(city.tier)}</span>
          {city.active_on_district ? <span className="badge badge-neutral">District live</span> : <span className="badge badge-amber">Expansion target</span>}
        </div>
      </div>

      <div className={styles.tiles}>
        <GlassCard className={`${styles.tile} ${styles.tileRing}`}>
          <span className="t-caption text-tertiary">Composite score</span>
          <Ring value={s.composite} size={132} stroke={14} color="var(--accent)"><span className={styles.ringNum}>{s.composite != null ? s.composite.toFixed(1) : '—'}</span></Ring>
          <span className="t-caption text-tertiary">out of 100</span>
        </GlassCard>
        {[
          { l: 'Metro population', v: compact(city.metro_population ?? city.population), a: styles.tilePop },
          { l: 'Youth share', v: city.youth_population_pct != null ? `${city.youth_population_pct}%` : '—', a: styles.tileYouth },
          { l: 'Average monthly income', v: inrCompact(city.avg_monthly_income), a: styles.tileInc },
        ].map((t, i) => (
          <GlassCard key={t.l} className={`${styles.tile} ${t.a}`} delay={(i + 1) * 0.04}>
            <span className="t-caption text-tertiary">{t.l}</span>
            <span className={styles.tileVal}>{t.v}</span>
          </GlassCard>
        ))}
      </div>

      {error && !data ? <GlassCard><ErrorState message="Couldn’t load the intelligence report for this city." onRetry={() => mutate()} /></GlassCard>
        : isLoading && !data ? <><Skeleton height={86} radius={16} /><Skeleton height={180} radius={22} /></>
        : intel && (
          <div className={`${styles.callout} ${city.active_on_district ? '' : styles.calloutTarget}`}>
            {city.active_on_district ? <Sparkles size={18} color="var(--text-secondary)" /> : <Rocket size={18} color="var(--saffron)" />}
            <div><p className="t-headline">{city.active_on_district ? 'District is live' : 'Expansion recommendation'}</p><p className="t-callout text-secondary">{intel.expansion_recommendation}</p></div>
          </div>
        )}

      <GlassCard className={styles.card} delay={0.04}>
        <div className={styles.cardTitle}><Users size={16} color="var(--text-secondary)" /><h3 className="t-headline">Demand scores</h3></div>
        <div className={styles.scoreGrid}>
          {scoreRows.map(([l, v], i) => (
            <div key={l} className={styles.scoreRow}>
              <div className={styles.scoreTop}><span className="t-callout">{l}</span><span className="t-callout tnum" style={{ fontWeight: 700, color: tone(v) }}>{v ?? '—'}</span></div>
              <Meter value={v} color={tone(v)} delay={i * 0.06} />
            </div>
          ))}
        </div>
        {(city.top_categories ?? []).length > 0 && <div className={styles.chips}>{city.top_categories!.map(c => <span key={c} className={styles.tag}>{c.replace(/_/g, ' ')}</span>)}</div>}
      </GlassCard>

      {intel && (
        <GlassCard className={styles.card} delay={0.05}>
          <div className={styles.cardHead}>
            <div className={styles.cardTitle}><CloudRain size={16} color="var(--text-secondary)" /><h3 className="t-headline">Seasonality</h3></div>
            <div className={styles.chips}><span className={styles.tag}>{intel.income_tier} income</span><span className={styles.tag}>{intel.youth_index} youth index</span></div>
          </div>
          <div className={styles.months} aria-label="Demand by month">
            {MONTHS.map((m, i) => <div key={m} className={`${styles.month} ${peak.has(i + 1) ? styles.monthHigh : low.has(i + 1) ? styles.monthLow : ''}`}>{m}</div>)}
          </div>
          <p className="t-footnote text-secondary"><span style={{ color: 'var(--accent)' }}>Blue</span> months are peak demand; dimmed months are low demand. {intel.monsoon_risk.replace(/[\[\]']/g, '')}</p>
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
              <Search size={15} className={styles.searchIcon} />
              <input className={`input ${styles.search}`} placeholder="Search cities" aria-label="Search cities" value={q} onChange={e => setQ(e.target.value)} />
            </div>
            <div className={styles.filters}>
              <Segmented value={tier} onChange={setTier} ariaLabel="Tier" options={[{ value: 'all', label: 'All' }, { value: '1', label: 'Tier 1' }, { value: '2', label: 'Tier 2' }, { value: '3', label: 'Tier 3' }]} />
              <Segmented value={status} onChange={setStatus} ariaLabel="Status" options={[{ value: 'all', label: 'Any' }, { value: 'live', label: 'Live' }, { value: 'target', label: 'Targets' }]} />
            </div>
          </div>
          <div className={styles.list}>
            {error && !data ? <ErrorState message="Couldn’t load the cities." onRetry={() => mutate()} />
              : isLoading && !data ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} height={104} radius={16} />)
              : filtered.length === 0 ? <EmptyState icon={<Building2 size={32} strokeWidth={1.4} />} title="No cities match" message="Try a different search or filter." />
              : <AnimatePresence initial={false}>{filtered.map(c => (
                <CityRow key={c.name} c={c} rank={cities.indexOf(c) + 1} active={selected?.name === c.name} onSelect={() => { setSel(c.name); setMobileDetail(true); }} />
              ))}</AnimatePresence>}
          </div>
        </aside>
        <section className={styles.detailPane} aria-live="polite">
          {selected
            ? <AnimatePresence mode="wait"><motion.div key={selected.name} initial={{ opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: .26, ease: [0.22, 1, 0.36, 1] }}>
              <CityDetail city={selected} onBack={() => setMobileDetail(false)} />
            </motion.div></AnimatePresence>
            : isLoading ? <Skeleton height={300} radius={22} /> : <EmptyState icon={<MapPin size={36} strokeWidth={1.4} />} title="Select a market" message="Pick a city to see demand, venues and partnership candidates." />}
        </section>
      </div>
    </Page>
  );
}
