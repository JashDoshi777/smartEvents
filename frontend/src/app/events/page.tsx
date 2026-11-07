'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { Ticket, Info, Calculator } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { motion } from 'framer-motion';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { getDashboardSummary, type UpcomingEvent } from '@/lib/api';
import { dateIN, inr, inrCompact, num } from '@/lib/format';
import styles from './page.module.css';

const DAY = 86_400_000;
function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.ceil((t - Date.now()) / DAY);
}
function price(e: UpcomingEvent) {
  const { min_price: a, max_price: b } = e;
  if (a == null && b == null) return '—';
  if (a != null && b != null && a !== b) return `${inr(a)} – ${inr(b)}`;
  return inr(a ?? b);
}
function sourceLabel(s: string | null) {
  if (!s) return 'Platform';
  return s === 'predicthq' ? 'PredictHQ' : s.charAt(0).toUpperCase() + s.slice(1);
}
function whenLabel(e: UpcomingEvent) {
  const d = daysUntil(e.event_date);
  if (d == null) return { text: '—', warn: false };
  if (d < 0) return { text: 'Past', warn: false };
  if (d === 0) return { text: 'Today', warn: true };
  return { text: d === 1 ? 'Tomorrow' : `In ${d} days`, warn: d <= 14 };
}

function GlassTip({ active, payload }: { active?: boolean; payload?: { payload: { name: string; value: number } }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="glass-card" style={{ padding: '8px 12px', fontSize: '.8125rem' }}>
      <div style={{ fontWeight: 600 }}>{p.name}</div>
      <div className="text-secondary tnum">{inr(p.value)}</div>
    </div>
  );
}

export default function EventsPage() {
  const { data, error, isLoading, mutate } = useSWR('dashboard/events', getDashboardSummary, { refreshInterval: 60000 });
  const events = data?.upcoming_events ?? [];
  const totalEvents = data?.hero.total_events;
  const priced = events.filter(e => e.min_price != null || e.max_price != null);
  const upcoming = events.filter(e => { const d = daysUntil(e.event_date); return d != null && d >= 0; }).length;
  const within30 = events.filter(e => { const d = daysUntil(e.event_date); return d != null && d >= 0 && d <= 30; }).length;
  const noVenue = events.filter(e => !e.venue && !e.city).length;
  const cities = [...(data?.city_heat ?? [])].sort((a, b) => (b.music_score ?? 0) + (b.nightlife_score ?? 0) - (a.music_score ?? 0) - (a.nightlife_score ?? 0)).slice(0, 8);
  const chart = priced.map(e => ({ name: e.name.length > 26 ? e.name.slice(0, 25) + '…' : e.name, value: (e.min_price ?? e.max_price) as number }));

  return (
    <Page
      title="Fill-Rate Monitor"
      subtitle="Events, ticket pricing and sell-through readiness"
      actions={<Link href="/events/model" className="btn btn-tinted btn-sm" style={{ textDecoration: 'none' }}><Calculator size={14} /> Deal modeler</Link>}
    >
      {error && !data ? (
        <GlassCard><ErrorState message="Couldn’t load events. Check that the API is reachable." onRetry={() => mutate()} /></GlassCard>
      ) : isLoading && !data ? (
        <div className={styles.bento}>
          <div className={styles.s5}><SkeletonCard lines={2} height={240} /></div>
          <div className={styles.s7}><SkeletonCard lines={4} height={240} /></div>
          <div className={styles.s12}><SkeletonCard lines={5} height={300} /></div>
        </div>
      ) : (
        <div className={styles.bento}>
          <GlassCard className={`${styles.hero} ${styles.s5}`}>
            <span className={styles.eyebrow}>Events tracked</span>
            <div className={styles.big}>{num(totalEvents)}</div>
            <div className={styles.heroStats}>
              <div><b>{events.length ? upcoming : '—'}</b><span>upcoming</span></div>
              <div><b>{events.length ? within30 : '—'}</b><span>within 30 days</span></div>
              <div><b>{num(data?.hero.active_cities)}<small>/{num(data?.hero.total_cities)}</small></b><span>live cities</span></div>
            </div>
          </GlassCard>

          <GlassCard className={`${styles.pad} ${styles.s7}`} delay={.04}>
            <div className={styles.head}><h2 className="t-headline">Entry ticket price</h2><span className="t-footnote text-tertiary">lowest tier per event</span></div>
            {chart.length === 0 ? (
              <EmptyState title="No pricing yet" message="None of these events list a ticket price." />
            ) : (
              <div className={styles.chartBox}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ top: 6, right: 4, left: -8, bottom: 0 }}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="name" tick={false} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={v => inrCompact(v)} axisLine={false} tickLine={false} width={56} />
                    <Tooltip content={<GlassTip />} cursor={{ fill: 'var(--fill-quaternary)' }} />
                    <Bar dataKey="value" fill="var(--c1)" radius={[9, 9, 3, 3]} maxBarSize={44} animationDuration={700} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </GlassCard>

          <GlassCard className={`${styles.listCard} ${styles.s7}`} delay={.08}>
            <div className={styles.listHead}><h2 className="t-headline">Events on record</h2><span className="t-footnote text-tertiary">earliest first</span></div>
            {events.length === 0 ? (
              <EmptyState icon={<Ticket size={34} strokeWidth={1.4} />} title="No events yet" message="Events appear here once the District and PredictHQ sync workers have run." />
            ) : events.map(e => {
              const w = whenLabel(e);
              return (
                <div key={e.id} className={styles.erow}>
                  <div style={{ minWidth: 0 }}>
                    <div className={styles.evName} title={e.name}>{e.name}</div>
                    <div className={styles.evSub}>{[e.venue, e.city].filter(Boolean).join(', ') || 'Venue to be announced'} · {dateIN(e.event_date, { day: 'numeric', month: 'short' })}{w.text !== '—' && <> · <span style={{ color: w.warn ? 'var(--warning)' : undefined }}>{w.text}</span></>}</div>
                  </div>
                  <div className={styles.eRight}>
                    <b className="tnum">{price(e)}</b>
                    <span className={styles.tag}>{sourceLabel(e.source)}{e.category ? ` · ${e.category}` : ''}</span>
                  </div>
                </div>
              );
            })}
          </GlassCard>

          <GlassCard className={`${styles.pad} ${styles.s5}`} delay={.12}>
            <div className={styles.head}><h2 className="t-headline">City demand</h2><span className="t-footnote text-tertiary">music + nightlife, 0 to 100</span></div>
            {cities.length === 0 ? <EmptyState title="No city scores" /> : cities.map(c => {
              const sc = ((c.music_score ?? 0) + (c.nightlife_score ?? 0)) / 2;
              return (
                <div key={c.city} className={styles.cityRow}>
                  <span style={{ width: 88, fontWeight: 500, fontSize: '.9375rem' }}>{c.city}</span>
                  <div className={styles.bar}><motion.div className={styles.barFill} initial={{ width: 0 }} animate={{ width: `${Math.min(100, sc)}%` }} transition={{ type: 'spring', stiffness: 80, damping: 18 }} style={{ background: c.active_on_district ? 'var(--accent)' : 'var(--text-tertiary)' }} /></div>
                  <span className="tnum" style={{ width: 28, textAlign: 'right', fontSize: '.875rem', fontFamily: 'ui-rounded, var(--font-sans)', fontWeight: 600 }}>{sc ? sc.toFixed(0) : '—'}</span>
                </div>
              );
            })}
            <p className="t-caption text-tertiary" style={{ marginTop: 10 }}>Blue: live on District. Gray: expansion opportunity.</p>
          </GlassCard>

          <p className={`${styles.note} ${styles.s12}`}><Info size={14} /> Live sell-through isn’t reported by the ticketing sources yet, so fill rate is not shown rather than estimated. Use the <Link href="/events/model" style={{ color: 'var(--accent)' }}>deal modeler</Link> for a predicted fill rate on a proposed booking.{noVenue > 0 && <> {noVenue} of these events have no venue or city on record.</>}</p>
        </div>
      )}
    </Page>
  );
}
