'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Ticket, Info, Calculator, ChevronDown } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Segmented } from '@/components/ui/Controls';
import { CountUp } from '@/components/intel/CountUp';
import { getDashboardSummary, getEvents, type EventRow } from '@/lib/api';
import { dateIN, inr, num } from '@/lib/format';
import styles from './page.module.css';

const PAGE = 12;
const DAY = 86_400_000;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function price(e: EventRow) {
  const { ticket_price_min: a, ticket_price_max: b } = e;
  if (a == null && b == null) return '—';
  if (a != null && b != null && a !== b) return `${inr(a)} – ${inr(b)}`;
  return inr(a ?? b);
}
const sourceLabel = (s: string | null) => !s ? 'Platform' : s === 'predicthq' ? 'PredictHQ' : s.charAt(0).toUpperCase() + s.slice(1);
const cap = (s: string | null) => s ? s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ') : '';
function whenLabel(e: EventRow) {
  if (!e.event_date) return null;
  const d = Math.ceil((new Date(e.event_date).getTime() - Date.now()) / DAY);
  if (e.status === 'completed') return 'Past';
  if (d < 0) return null;
  if (d === 0) return 'Today';
  return d === 1 ? 'Tomorrow' : `In ${d} days`;
}

function GlassTip({ active, payload }: { active?: boolean; payload?: { payload: { name: string; value: number } }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="glass-card" style={{ padding: '8px 12px', fontSize: '.8125rem', boxShadow: '0 8px 30px rgba(0,0,0,.35)' }}>
      <div style={{ fontWeight: 600 }}>{p.name}</div>
      <div className="text-secondary tnum">{p.value} event{p.value === 1 ? '' : 's'}</div>
    </div>
  );
}

export default function EventsPage() {
  const [src, setSrc] = useState('all');
  const [shown, setShown] = useState(PAGE);
  const { data, error, isLoading, mutate } = useSWR('events/all', () => getEvents({ limit: 100 }), { refreshInterval: 120000 });
  const { data: dash } = useSWR('dashboard/events', getDashboardSummary);

  const all = data?.events ?? [];
  const list = useMemo(() => (src === 'all' ? all : all.filter(e => e.source === src)), [all, src]);
  const sources = useMemo(() => [...new Set(all.map(e => e.source).filter(Boolean))] as string[], [all]);
  const upcoming = all.filter(e => e.status != null && e.status !== 'completed' && e.status !== 'cancelled').length;
  const within30 = all.filter(e => { if (!e.event_date) return false; const d = (new Date(e.event_date).getTime() - Date.now()) / DAY; return d >= 0 && d <= 30; }).length;
  const noVenue = all.filter(e => !e.venue && !e.city).length;
  const tracked = all.filter(e => e.fill_rate != null).length;

  const byMonth = useMemo(() => {
    const m = new Map<string, { key: string; name: string; value: number }>();
    for (const e of all) {
      if (!e.event_date) continue;
      const d = new Date(e.event_date); const key = `${d.getFullYear()}-${String(d.getMonth()).padStart(2, '0')}`;
      const cur = m.get(key) ?? { key, name: `${MONTHS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`, value: 0 };
      cur.value++; m.set(key, cur);
    }
    return [...m.values()].sort((a, b) => a.key.localeCompare(b.key));
  }, [all]);
  const byCat = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of all) m.set(e.category ?? 'other', (m.get(e.category ?? 'other') ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [all]);
  const cities = [...(dash?.city_heat ?? [])].sort((a, b) => (b.music_score ?? 0) + (b.nightlife_score ?? 0) - (a.music_score ?? 0) - (a.nightlife_score ?? 0)).slice(0, 6);
  const maxCat = byCat[0]?.[1] ?? 1;
  const visible = list.slice(0, shown);

  return (
    <Page
      title="Fill-Rate Monitor"
      subtitle="Every event on record, with pricing and sell-through"
      actions={<Link href="/events/model" className="btn btn-tinted" style={{ textDecoration: 'none', minHeight: 44 }}><Calculator size={16} strokeWidth={1.7} /> Deal modeler</Link>}
    >
      {error && !data ? (
        <GlassCard><ErrorState message="Couldn’t load events. Check that the API is reachable." onRetry={() => mutate()} /></GlassCard>
      ) : isLoading && !data ? (
        <div className={styles.bento}>
          <div className={styles.s5}><SkeletonCard lines={2} height={260} /></div>
          <div className={styles.s7}><SkeletonCard lines={4} height={260} /></div>
          <div className={styles.s12}><SkeletonCard lines={5} height={320} /></div>
        </div>
      ) : (
        <div className={styles.bento}>
          <GlassCard className={`${styles.hero} ${styles.s5}`}>
            <h2 className={styles.title}>Events tracked</h2>
            <div className={styles.big}><CountUp value={data?.total ?? 0} format={v => num(Math.round(v))} /></div>
            <div className={styles.heroStats}>
              <div><b>{upcoming}</b><span>upcoming</span></div>
              <div><b>{within30}</b><span>next 30 days</span></div>
              <div><b>{tracked}</b><span>with live fill rate</span></div>
            </div>
          </GlassCard>

          <GlassCard className={`${styles.pad} ${styles.s7}`} delay={.04}>
            <div className={styles.head}><h2 className={styles.title}>Events by month</h2><span className="t-footnote text-tertiary">{all.length} events</span></div>
            {byMonth.length === 0 ? <EmptyState title="No dated events" /> : (
              <div className={styles.chartBox}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={byMonth} margin={{ top: 6, right: 4, left: -22, bottom: 0 }}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} interval="preserveStartEnd" />
                    <YAxis axisLine={false} tickLine={false} allowDecimals={false} width={44} />
                    <Tooltip content={<GlassTip />} cursor={{ fill: 'var(--fill-quaternary)' }} />
                    <Bar dataKey="value" fill="var(--text-primary)" fillOpacity={.85} radius={[8, 8, 3, 3]} maxBarSize={40} animationDuration={700} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </GlassCard>

          <GlassCard className={`${styles.listCard} ${styles.s7}`} delay={.08}>
            <div className={styles.listHead}>
              <h2 className={styles.title}>All events</h2>
              <Segmented ariaLabel="Source" value={src} onChange={v => { setSrc(v); setShown(PAGE); }} options={[{ value: 'all', label: 'All' }, ...sources.map(x => ({ value: x, label: sourceLabel(x) }))]} />
            </div>
            {visible.length === 0 ? (
              <EmptyState icon={<Ticket size={34} strokeWidth={1.4} />} title="No events" message="Events appear here once the sync workers have run." />
            ) : visible.map((e, i) => {
              const w = whenLabel(e);
              return (
                <motion.div key={e.id} className={styles.erow} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * .025, duration: .28 }}>
                  <div style={{ minWidth: 0 }}>
                    <div className={styles.evName} title={e.title}>{e.title}</div>
                    <div className={styles.evSub}>{[e.venue, e.city].filter(Boolean).join(', ') || 'Venue to be announced'} · {dateIN(e.event_date, { day: 'numeric', month: 'short' })}{w && <> · {w}</>}</div>
                  </div>
                  <div className={styles.eRight}>
                    <b className="tnum">{price(e)}</b>
                    <span className={styles.tag}>{e.fill_rate != null ? `${Math.round(e.fill_rate * (e.fill_rate <= 1 ? 100 : 1))}% sold · ` : ''}{sourceLabel(e.source)} · {cap(e.category)}</span>
                  </div>
                </motion.div>
              );
            })}
            {list.length > shown && (
              <button type="button" className={styles.more} onClick={() => setShown(n => n + PAGE)}>Show more <span className="text-tertiary">({list.length - shown} left)</span> <ChevronDown size={16} strokeWidth={1.7} /></button>
            )}
          </GlassCard>

          <div className={`${styles.stack} ${styles.s5}`}>
            <GlassCard className={styles.pad} delay={.12}>
              <div className={styles.head}><h2 className={styles.title}>By category</h2></div>
              {byCat.map(([c, n]) => (
                <div key={c} className={styles.cityRow}>
                  <span style={{ width: 88, fontSize: '.9375rem' }}>{cap(c)}</span>
                  <div className={styles.bar}><motion.div className={styles.barFill} initial={{ width: 0 }} animate={{ width: `${(n / maxCat) * 100}%` }} transition={{ type: 'spring', stiffness: 80, damping: 18 }} style={{ background: 'var(--text-primary)', opacity: .85 }} /></div>
                  <span className="tnum" style={{ width: 28, textAlign: 'right', fontSize: '.9375rem', fontFamily: 'ui-rounded, var(--font-sans)', fontWeight: 600 }}>{n}</span>
                </div>
              ))}
            </GlassCard>
            <GlassCard className={styles.pad} delay={.16}>
              <div className={styles.head}><h2 className={styles.title}>City demand</h2><span className="t-footnote text-tertiary">0 to 100</span></div>
              {cities.length === 0 ? <EmptyState title="No city scores" /> : cities.map(c => {
                const sc = ((c.music_score ?? 0) + (c.nightlife_score ?? 0)) / 2;
                return (
                  <div key={c.city} className={styles.cityRow}>
                    <span style={{ width: 88, fontSize: '.9375rem' }}>{c.city}</span>
                    <div className={styles.bar}><motion.div className={styles.barFill} initial={{ width: 0 }} animate={{ width: `${Math.min(100, sc)}%` }} transition={{ type: 'spring', stiffness: 80, damping: 18 }} style={{ background: 'var(--text-primary)', opacity: c.active_on_district ? .85 : .3 }} /></div>
                    <span className="tnum" style={{ width: 28, textAlign: 'right', fontSize: '.9375rem', fontFamily: 'ui-rounded, var(--font-sans)', fontWeight: 600 }}>{sc ? sc.toFixed(0) : '—'}</span>
                  </div>
                );
              })}
              <p className="t-caption text-tertiary" style={{ marginTop: 10 }}>Bright bars are cities live on District; dim bars are expansion opportunities.</p>
            </GlassCard>
          </div>

          <p className={`${styles.note} ${styles.s12}`}><Info size={14} strokeWidth={1.7} /> {tracked === 0 ? 'Live sell-through isn’t reported by the ticketing sources yet, so fill rate is not shown rather than estimated. ' : ''}Use the <Link href="/events/model" style={{ color: 'var(--accent)' }}>deal modeler</Link> for a predicted fill rate on a proposed booking.{noVenue > 0 && <> {noVenue} of {all.length} events have no venue or city on record.</>}</p>
        </div>
      )}
    </Page>
  );
}
