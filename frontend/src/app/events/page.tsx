'use client';

import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import useSWRInfinite from 'swr/infinite';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Ticket, Info, Calculator, ChevronDown, ChevronLeft, ChevronRight, Download, Search } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Segmented } from '@/components/ui/Controls';
import { useToast } from '@/components/ui/Toast';
import { CountUp } from '@/components/intel/CountUp';
import { getDashboardSummary, getEventsStrict, getEventsSummary, type EventRow, type EventsQuery } from '@/lib/api';
import { inr, num } from '@/lib/format';
import { daysFromToday, istDate, istKey, istToday } from '@/lib/ist';
import styles from './page.module.css';

const PAGE = 20;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

type When = 'all' | 'upcoming' | 'past';

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
  const d = daysFromToday(e.event_date);
  if (d < 0) return 'Past';
  if (d === 0) return 'Today';
  return d === 1 ? 'Tomorrow' : `In ${d} days`;
}
const csvCell = (v: unknown) => { const t = v == null ? '' : String(v); return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t; };

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

function EventRowView({ e, i }: { e: EventRow; i: number }) {
  const w = whenLabel(e);
  return (
    <motion.div className={styles.erow} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * .025, duration: .28 }} data-testid="event-row">
      <div style={{ minWidth: 0 }}>
        <div className={styles.evName} title={e.title}>{e.title}</div>
        <div className={styles.evSub}>{[e.venue, e.city].filter(Boolean).join(', ') || 'Venue to be announced'} · {istDate(e.event_date, { day: 'numeric', month: 'short' })}{w && <> · {w}</>}</div>
      </div>
      <div className={styles.eRight}>
        <b className="tnum">{price(e)}</b>
        <span className={styles.tag}>{e.fill_rate != null ? `${Math.round(e.fill_rate * (e.fill_rate <= 1 ? 100 : 1))}% sold · ` : ''}{sourceLabel(e.source)} · {cap(e.category)}</span>
      </div>
    </motion.div>
  );
}

function MonthCalendar({ filters }: { filters: Omit<EventsQuery, 'limit' | 'offset'> }) {
  const [ty, tm] = istToday().split('-').map(Number);
  const [view, setView] = useState({ y: ty, m: tm - 1 });
  const [day, setDay] = useState<string | null>(null);
  const from = `${view.y}-${String(view.m + 1).padStart(2, '0')}-01`;
  const last = new Date(Date.UTC(view.y, view.m + 1, 0)).getUTCDate();
  const to = `${view.y}-${String(view.m + 1).padStart(2, '0')}-${String(last).padStart(2, '0')}`;
  const { data, error, isLoading, mutate } = useSWR(['events-cal', JSON.stringify(filters), from], () => getEventsStrict({ ...filters, date_from: from, date_to: to, limit: 500 }), { keepPreviousData: true });
  const byDay = useMemo(() => {
    const m = new Map<string, EventRow[]>();
    for (const e of data?.events ?? []) if (e.event_date) { const k = istKey(e.event_date); m.set(k, [...(m.get(k) ?? []), e]); }
    return m;
  }, [data]);
  const cells = useMemo(() => {
    const lead = (new Date(Date.UTC(view.y, view.m, 1)).getUTCDay() + 6) % 7;
    const total = Math.ceil((lead + last) / 7) * 7;
    return Array.from({ length: total }, (_, i) => {
      const d = new Date(Date.UTC(view.y, view.m, 1 - lead + i));
      return { key: d.toISOString().slice(0, 10), n: d.getUTCDate(), inMonth: d.getUTCMonth() === view.m };
    });
  }, [view, last]);
  const step = (n: number) => { setDay(null); setView(v => { const d = new Date(Date.UTC(v.y, v.m + n, 1)); return { y: d.getUTCFullYear(), m: d.getUTCMonth() }; }); };
  const sel = day ? byDay.get(day) ?? [] : [];
  const today = istToday();
  return (
    <div className={styles.calWrap} data-testid="events-calendar">
      <div className={styles.calHead}>
        <h3 className={styles.title} style={{ flex: 1 }} data-testid="cal-month">{MONTHS[view.m]} {view.y}</h3>
        <button type="button" className="btn btn-tinted btn-sm" onClick={() => { setView({ y: ty, m: tm - 1 }); setDay(today); }}>Today</button>
        <button type="button" className="btn btn-icon" aria-label="Previous month" onClick={() => step(-1)}><ChevronLeft size={16} /></button>
        <button type="button" className="btn btn-icon" aria-label="Next month" onClick={() => step(1)}><ChevronRight size={16} /></button>
      </div>
      <div className={styles.dow}>{DOW.map(d => <span key={d}>{d}</span>)}</div>
      {error && !data ? <ErrorState message="Couldn’t load this month." onRetry={() => mutate()} /> : (
        <div className={styles.calGrid} style={{ opacity: isLoading ? .6 : 1 }}>
          {cells.map(c => {
            const n = byDay.get(c.key)?.length ?? 0;
            return (
              <button key={c.key} type="button" className={`${styles.calDay} ${!c.inMonth ? styles.calOut : ''} ${c.key === today ? styles.calToday : ''} ${day === c.key ? styles.calSel : ''}`}
                aria-label={`${istDate(c.key, { weekday: 'long', day: 'numeric', month: 'long' })}, ${n} event${n === 1 ? '' : 's'}`} aria-pressed={day === c.key} onClick={() => setDay(c.key)}>
                <span>{c.n}</span>{n > 0 && c.inMonth && <i className={styles.calCount}>{n}</i>}
              </button>
            );
          })}
        </div>
      )}
      {day && (
        <div className={styles.calList} data-testid="cal-day-list">
          <p className="t-footnote text-secondary" style={{ padding: '6px 20px' }}>{istDate(day, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
          {sel.length === 0 ? <p className="t-callout text-tertiary" style={{ padding: '6px 20px 14px' }}>No events on this day.</p> : sel.map((e, i) => <EventRowView key={e.id} e={e} i={i} />)}
        </div>
      )}
    </div>
  );
}

export default function EventsPage() {
  const toast = useToast();
  const [src, setSrc] = useState('all');
  const [city, setCity] = useState('');
  const [category, setCategory] = useState('');
  const [when, setWhen] = useState<When>('all');
  const [view, setView] = useState<'list' | 'calendar'>('list');
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [exporting, setExporting] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 300); return () => clearTimeout(t); }, [q]);

  const filters = useMemo(() => ({ source: src === 'all' ? undefined : src, city: city || undefined, category: category || undefined, q: dq || undefined, when }), [src, city, category, dq, when]);
  const fkey = JSON.stringify(filters);

  const summary = useSWR(['events-summary', fkey], () => getEventsSummary(filters), { keepPreviousData: true, refreshInterval: 120000 });
  const allSummary = useSWR('events-summary-all', () => getEventsSummary(), { refreshInterval: 120000 });
  const { data: dash } = useSWR('dashboard/events', getDashboardSummary);
  const list = useSWRInfinite(
    i => (view === 'list' ? ['events-list', fkey, i] : null),
    ([, , i]: [string, string, number]) => getEventsStrict({ ...filters, limit: PAGE, offset: i * PAGE, order: when === 'past' ? 'desc' : 'asc' }),
    { keepPreviousData: true },
  );
  const rows = useMemo(() => (list.data ?? []).flatMap(p => p.events), [list.data]);
  const total = list.data?.[0]?.total ?? 0;
  const loadingMore = list.isValidating && list.size > (list.data?.length ?? 0);

  const s = summary.data;
  const facets = allSummary.data?.facets;
  const byMonth = useMemo(() => (s?.by_month ?? []).map(m => { const [y, mo] = m.month.split('-').map(Number); return { key: m.month, name: `${MONTHS[mo - 1]} ${String(y).slice(2)}`, value: m.count }; }), [s]);
  const byCat = s?.by_category ?? [];
  const maxCat = byCat[0]?.count ?? 1;
  const cities = [...(dash?.city_heat ?? [])].sort((a, b) => (b.music_score ?? 0) + (b.nightlife_score ?? 0) - (a.music_score ?? 0) - (a.nightlife_score ?? 0)).slice(0, 6);
  const fatal = summary.error && !summary.data;
  const filtered = !!(filters.source || filters.city || filters.category || filters.q || filters.when !== 'all');

  async function exportCsv() {
    setExporting(true);
    try {
      const all: EventRow[] = [];
      for (let off = 0; off < 20000; off += 500) {
        const page = await getEventsStrict({ ...filters, limit: 500, offset: off });
        all.push(...page.events);
        if (page.events.length < 500) break;
      }
      const head = ['title', 'date_ist', 'city', 'venue', 'category', 'source', 'price_min_inr', 'price_max_inr', 'capacity', 'tickets_sold', 'fill_rate', 'upcoming', 'booking_url'];
      const body = all.map(e => [e.title, e.event_date ? istKey(e.event_date) : '', e.city, e.venue, e.category, e.source, e.ticket_price_min, e.ticket_price_max, e.total_capacity, e.tickets_sold, e.fill_rate, e.event_date ? daysFromToday(e.event_date) >= 0 : '', e.booking_url].map(csvCell).join(','));
      const blob = new Blob([[head.join(','), ...body].join('\r\n')], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `liveiq-events-${istToday()}.csv`; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(`Exported ${num(all.length)} events`, 'success');
    } catch { toast('Couldn’t export events', 'error'); } finally { setExporting(false); }
  }

  return (
    <Page
      title="Fill-Rate Monitor"
      subtitle="Every event on record, with pricing and sell-through"
      actions={<>
        <button type="button" className="btn btn-tinted" style={{ minHeight: 44 }} onClick={exportCsv} disabled={exporting || !s || s.total === 0}><Download size={16} strokeWidth={1.7} /> {exporting ? 'Exporting…' : 'Export CSV'}</button>
        <Link href="/events/model" className="btn btn-tinted" style={{ textDecoration: 'none', minHeight: 44 }}><Calculator size={16} strokeWidth={1.7} /> Deal modeler</Link>
      </>}
    >
      {fatal ? (
        <GlassCard><ErrorState message="Couldn’t load events. Check that the API is reachable." onRetry={() => summary.mutate()} /></GlassCard>
      ) : !s ? (
        <div className={styles.bento}>
          <div className={styles.s5}><SkeletonCard lines={2} height={260} /></div>
          <div className={styles.s7}><SkeletonCard lines={4} height={260} /></div>
          <div className={styles.s12}><SkeletonCard lines={5} height={320} /></div>
        </div>
      ) : (
        <div className={styles.bento}>
          <GlassCard className={`${styles.hero} ${styles.s5}`}>
            <h2 className={styles.title}>{filtered ? 'Matching events' : 'Events tracked'}</h2>
            <div className={styles.big} data-testid="events-total"><CountUp value={s.total} format={v => num(Math.round(v))} /></div>
            {filtered && allSummary.data && <p className="t-footnote text-tertiary">of {num(allSummary.data.total)} on record</p>}
            <div className={styles.heroStats}>
              <div><b data-testid="events-upcoming">{num(s.upcoming)}</b><span>upcoming</span></div>
              <div><b>{num(s.next_30_days)}</b><span>next 30 days</span></div>
              <div><b>{num(s.past)}</b><span>already held</span></div>
              <div><b>{num(s.with_fill_rate)}</b><span>with live fill rate</span></div>
            </div>
          </GlassCard>

          <GlassCard className={`${styles.pad} ${styles.s7}`} delay={.04}>
            <div className={styles.head}><h2 className={styles.title}>Events by month</h2><span className="t-footnote text-tertiary">{num(s.total)} events, India time</span></div>
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
              <Segmented ariaLabel="View" value={view} onChange={setView} options={[{ value: 'list', label: 'List' }, { value: 'calendar', label: 'Calendar' }]} />
            </div>
            <div className={styles.filters}>
              <div className={styles.searchWrap}>
                <Search size={15} strokeWidth={1.75} className={styles.searchIcon} />
                <input className={`input ${styles.search}`} placeholder="Search events" aria-label="Search events" value={q} onChange={e => setQ(e.target.value)} />
              </div>
              <Segmented ariaLabel="When" value={when} onChange={w => setWhen(w)} options={[{ value: 'all', label: 'All' }, { value: 'upcoming', label: 'Upcoming' }, { value: 'past', label: 'Past' }]} />
              <div className={styles.selRow}>
                <select className={`input ${styles.sel}`} aria-label="City" value={city} onChange={e => setCity(e.target.value)}>
                  <option value="">All cities</option>{(facets?.cities ?? []).map(c => <option key={c.key} value={c.key}>{c.key} ({c.count})</option>)}
                </select>
                <select className={`input ${styles.sel}`} aria-label="Category" value={category} onChange={e => setCategory(e.target.value)}>
                  <option value="">All categories</option>{(facets?.categories ?? []).map(c => <option key={c.key} value={c.key}>{cap(c.key)} ({c.count})</option>)}
                </select>
                <select className={`input ${styles.sel}`} aria-label="Source" value={src} onChange={e => setSrc(e.target.value)}>
                  <option value="all">All sources</option>{(facets?.sources ?? []).map(c => <option key={c.key} value={c.key}>{sourceLabel(c.key)} ({c.count})</option>)}
                </select>
              </div>
            </div>
            {view === 'calendar' ? <MonthCalendar filters={filters} /> : list.error && !list.data ? (
              <ErrorState message="Couldn’t load events." onRetry={() => list.mutate()} />
            ) : !list.data ? (
              <div style={{ padding: '4px 20px 16px' }}><SkeletonCard lines={4} height={200} /></div>
            ) : rows.length === 0 ? (
              <EmptyState icon={<Ticket size={34} strokeWidth={1.4} />} title="No events" message={filtered ? 'No event matches these filters. Clear a filter to see more.' : 'Events appear here once the sync workers have run.'} />
            ) : rows.map((e, i) => <EventRowView key={e.id} e={e} i={i} />)}
            {view === 'list' && rows.length > 0 && (
              <div className={styles.foot}>
                <span className="t-footnote text-tertiary" data-testid="events-count">Showing {num(rows.length)} of {num(total)}</span>
                {rows.length < total && <button type="button" className={styles.more} disabled={loadingMore} onClick={() => list.setSize(list.size + 1)}>{loadingMore ? 'Loading…' : <>Show more <span className="text-tertiary">({num(total - rows.length)} left)</span> <ChevronDown size={16} strokeWidth={1.7} /></>}</button>}
              </div>
            )}
          </GlassCard>

          <div className={`${styles.stack} ${styles.s5}`}>
            <GlassCard className={styles.pad} delay={.12}>
              <div className={styles.head}><h2 className={styles.title}>By category</h2></div>
              {byCat.length === 0 ? <p className="t-callout text-tertiary">No categories.</p> : byCat.map(({ key: c, count: n }) => (
                <div key={c} className={styles.cityRow}>
                  <span style={{ width: 88, fontSize: '.9375rem' }}>{cap(c)}</span>
                  <div className={styles.bar}><motion.div className={styles.barFill} initial={{ width: 0 }} animate={{ width: `${(n / maxCat) * 100}%` }} transition={{ type: 'spring', stiffness: 80, damping: 18 }} style={{ background: 'var(--text-primary)', opacity: .85 }} /></div>
                  <span className="tnum" style={{ width: 36, textAlign: 'right', fontSize: '.9375rem', fontFamily: 'ui-rounded, var(--font-sans)', fontWeight: 600 }}>{n}</span>
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

          <p className={`${styles.note} ${styles.s12}`}><Info size={14} strokeWidth={1.7} /> {s.with_fill_rate === 0 ? 'Live sell-through isn’t reported by the ticketing sources yet, so fill rate is not shown rather than estimated. ' : ''}“Upcoming” is based on the event date in India time. Use the <Link href="/events/model" style={{ color: 'var(--accent)' }}>deal modeler</Link> for a predicted fill rate on a proposed booking.{s.without_venue > 0 && <> {num(s.without_venue)} of {num(s.total)} events have no venue linked, so they are missing from the city filter.</>}</p>
        </div>
      )}
    </Page>
  );
}
