'use client';

import { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { AnimatePresence, motion } from 'framer-motion';
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, Info, MapPin } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Sheet } from '@/components/ui/Sheet';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton } from '@/components/ui/Skeleton';
import { dateIN, num } from '@/lib/format';
import { Ring, ROUNDED } from '@/components/insights/Ring';
import { VenueCalendarEvent, getCityVenuesStrict, getMarketCities, getVenueCalendarStrict } from '@/lib/api';
import styles from './page.module.css';

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const IST = 'Asia/Kolkata';
const pad = (n: number) => String(n).padStart(2, '0');
const keyOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;
const istKey = (iso: string) => new Date(iso).toLocaleDateString('en-CA', { timeZone: IST });
const MONTH_FMT = new Intl.DateTimeFormat('en-IN', { month: 'long' });

function todayKey() { return new Date().toLocaleDateString('en-CA', { timeZone: IST }); }

export default function VenueCalendarPage() {
  const [city, setCity] = useState('Mumbai');
  const [venueId, setVenueId] = useState('');
  const today = todayKey();
  const [ty, tm] = today.split('-').map(Number);
  const [view, setView] = useState({ y: ty, m: tm - 1 });
  const [selected, setSelected] = useState<string | null>(null);

  const { data: citiesData } = useSWR('market-cities', getMarketCities);
  const venuesRes = useSWR(['cal-venues', city], () => getCityVenuesStrict(city));
  const venues = useMemo(() => (venuesRes.data?.venues ?? []).filter((v): v is typeof v & { id: string } => !!v.id), [venuesRes.data]);

  // Auto-pick the first venue when the city (or its venue list) changes.
  useEffect(() => {
    if (venues.length === 0) { setVenueId(''); return; }
    if (!venues.some(v => v.id === venueId)) setVenueId(venues[0].id);
  }, [venues, venueId]);

  const cal = useSWR(venueId ? ['venue-cal', venueId] : null, () => getVenueCalendarStrict(venueId, 12));

  const eventsByDay = useMemo(() => {
    const map = new Map<string, VenueCalendarEvent[]>();
    for (const w of cal.data?.weeks ?? []) for (const e of w.events_this_week) {
      const k = istKey(e.event_date);
      map.set(k, [...(map.get(k) ?? []), e]);
    }
    return map;
  }, [cal.data]);
  const bookedWeekendDays = useMemo(() => {
    const s = new Set<string>();
    for (const w of cal.data?.weeks ?? []) if (w.is_weekend_booked) {
      const start = new Date(`${w.week_start}T00:00:00Z`);
      for (const off of [4, 5, 6]) s.add(new Date(start.getTime() + off * 86400000).toISOString().slice(0, 10));
    }
    return s;
  }, [cal.data]);
  const upcoming = useMemo(() => [...eventsByDay.entries()].sort(([a], [b]) => a.localeCompare(b)).filter(([k]) => k >= today).flatMap(([, v]) => v), [eventsByDay, today]);

  const cells = useMemo(() => {
    const first = new Date(Date.UTC(view.y, view.m, 1));
    const lead = (first.getUTCDay() + 6) % 7;
    const dim = new Date(Date.UTC(view.y, view.m + 1, 0)).getUTCDate();
    const total = Math.ceil((lead + dim) / 7) * 7;
    return Array.from({ length: total }, (_, i) => {
      const d = new Date(Date.UTC(view.y, view.m, 1 - lead + i));
      return { key: keyOf(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()), day: d.getUTCDate(), inMonth: d.getUTCMonth() === view.m, col: i % 7 };
    });
  }, [view]);

  const range = cal.data?.range;
  const step = (n: number) => setView(v => { const d = new Date(Date.UTC(v.y, v.m + n, 1)); return { y: d.getUTCFullYear(), m: d.getUTCMonth() }; });
  const goToday = () => { setView({ y: ty, m: tm - 1 }); setSelected(today); };
  const selEvents = selected ? eventsByDay.get(selected) ?? [] : [];
  const cityOptions = (citiesData?.cities ?? []).map(c => c.name);
  const venue = cal.data?.venue;

  return (
    <Page title="Venue Calendar" subtitle="Weekend availability by venue across Indian cities">
      <div className={styles.pickers}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="cal-city">City</label>
          <div className={styles.selectWrap}>
            <select id="cal-city" className={`input ${styles.select}`} value={city} onChange={e => { setCity(e.target.value); setVenueId(''); setSelected(null); }}>
              {(cityOptions.length ? cityOptions : [city]).map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <ChevronDown size={14} className={styles.selectIcon} />
          </div>
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="cal-venue">Venue</label>
          <div className={styles.selectWrap}>
            <select id="cal-venue" className={`input ${styles.select}`} value={venueId} disabled={venues.length === 0} onChange={e => { setVenueId(e.target.value); setSelected(null); }}>
              {venues.length === 0 && <option value="">{venuesRes.isLoading ? 'Loading venues…' : 'No venues on file'}</option>}
              {venues.map(v => <option key={v.id} value={v.id}>{v.name} · {num(v.capacity)} cap</option>)}
            </select>
            <ChevronDown size={14} className={styles.selectIcon} />
          </div>
        </div>
      </div>

      {venuesRes.error && !venuesRes.data ? (
        <GlassCard><ErrorState message="Couldn’t load venues for this city." onRetry={() => venuesRes.mutate()} /></GlassCard>
      ) : venuesRes.data && venues.length === 0 ? (
        <GlassCard><EmptyState icon={<MapPin size={34} strokeWidth={1.5} />} title={`No venues tracked in ${city}`} message="Pick another city — venues come from the venue database." /></GlassCard>
      ) : (
        <div className={styles.main}>
          <GlassCard className={styles.calCard}>
            <div className={styles.calHead}>
              <h2 className={styles.monthTitle} data-testid="month-title">{MONTH_FMT.format(new Date(Date.UTC(view.y, view.m, 1)))} <span>{view.y}</span></h2>
              <button className="btn btn-tinted btn-sm" onClick={goToday}>Today</button>
              <button className="btn btn-icon" aria-label="Previous month" onClick={() => step(-1)}><ChevronLeft size={16} strokeWidth={1.75} /></button>
              <button className="btn btn-icon" aria-label="Next month" onClick={() => step(1)}><ChevronRight size={16} strokeWidth={1.75} /></button>
            </div>
            <div className={styles.dow}>{DOW.map((d, i) => <span key={d} className={i >= 4 ? styles.dowWknd : ''}>{d}</span>)}</div>
            {cal.isLoading && !cal.data ? (
              <div className={styles.grid}>{Array.from({ length: 35 }).map((_, i) => <Skeleton key={i} height={52} radius={14} />)}</div>
            ) : cal.error && !cal.data ? (
              <ErrorState message="Couldn’t load this venue’s calendar." onRetry={() => cal.mutate()} />
            ) : (
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={`${view.y}-${view.m}`} className={styles.grid} role="grid" aria-label="Month" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: .2 }}>
                  {cells.map(c => {
                    const evs = eventsByDay.get(c.key) ?? [];
                    const isToday = c.key === today;
                    const cls = [styles.day, !c.inMonth && styles.dayOut, c.key < today && styles.dayPast, c.col >= 4 && !bookedWeekendDays.has(c.key) && styles.dayWknd, bookedWeekendDays.has(c.key) && styles.dayBooked, isToday && styles.dayToday, selected === c.key && styles.daySel].filter(Boolean).join(' ');
                    return (
                      <button key={c.key} type="button" role="gridcell" className={cls} onClick={() => setSelected(c.key)}
                        aria-label={`${dateIN(c.key, { weekday: 'long', day: 'numeric', month: 'long' })}${evs.length ? `, ${evs.length} event${evs.length > 1 ? 's' : ''}` : ''}`}>
                        <span className={styles.dayNum}>{c.day}</span>
                        <span className={styles.dots}>{evs.slice(0, 3).map(e => <i key={e.id} className={styles.dot} />)}{evs.length > 3 && <span className={styles.dotMore}>+</span>}</span>
                      </button>
                    );
                  })}
                </motion.div>
              </AnimatePresence>
            )}
            <div className={styles.legend}>
                            <span className={styles.legendItem}><i className={styles.swatch} style={{ background: 'var(--fill-tertiary)' }} /> Booked weekend</span>
              <span className={styles.legendItem}><i className={styles.dot} /> Event</span>
            </div>
            {range && <p className={styles.note}>Data covers {dateIN(range.start)} to {dateIN(range.end)}. Dates outside this window have no tracked data.</p>}
          </GlassCard>

          <div className={styles.side}>
            <GlassCard className={styles.summary}>
              <div className={styles.sumRing}>
                <Ring value={cal.data ? Math.round((cal.data.summary.open_weekends / Math.max(1, cal.data.summary.total_weeks)) * 100) : 0} size={76} stroke={8} color="var(--text-primary)"><span style={{ fontFamily: ROUNDED, fontSize: '.875rem', fontWeight: 700 }}>{cal.data ? cal.data ? Math.round((cal.data.summary.open_weekends / Math.max(1, cal.data.summary.total_weeks)) * 100) : 0 : '—'}%</span></Ring>
                <span className={styles.sub}>Weekends<br />open</span>
              </div>
              {[{ l: 'Booked', v: cal.data?.summary.booked_weekends }, { l: 'Open', v: cal.data?.summary.open_weekends }, { l: 'Events', v: cal.data?.summary.total_tracked_events }].map(t => (
                <div key={t.l} className={styles.sumCol}><span className={styles.sumVal}>{t.v != null ? t.v : '—'}</span><span className={styles.sub}>{t.l}</span></div>
              ))}
            </GlassCard>
            <GlassCard className={styles.card} delay={0.08}>
              <div>
                <h3 className={styles.headline}>{venue?.name ?? 'Select a venue'}</h3>
                <p className={styles.sub}>{venue ? `${venue.city} · ${num(venue.capacity)} capacity` : '—'}</p>
              </div>
              <h4 className={styles.headline} style={{ marginTop: 4 }}>Upcoming events</h4>
              {!cal.data ? <Skeleton height={56} radius={14} /> : upcoming.length === 0 ? (
                <EmptyState icon={<CalendarDays size={30} strokeWidth={1.5} />} title="No tracked events" message="Every weekend shows as open — this reflects data coverage, not a confirmed availability check." />
              ) : <div>{upcoming.slice(0, 8).map(e => (
                <button key={e.id} className={`${styles.evRow} ${styles.evBtn}`} onClick={() => { const k = istKey(e.event_date); const [y, m] = k.split('-').map(Number); setView({ y, m: m - 1 }); setSelected(k); }}>
                  <div className={styles.evDate}><div className={styles.evDay}>{new Date(e.event_date).toLocaleDateString('en-IN', { day: 'numeric', timeZone: IST })}</div><div className={styles.evMon}>{new Date(e.event_date).toLocaleDateString('en-IN', { month: 'short', timeZone: IST })}</div></div>
                  <div style={{ minWidth: 0 }}><p className="t-callout" style={{ fontWeight: 600 }}>{e.title}</p><p className="t-caption text-tertiary">{[e.status, e.source].filter(Boolean).join(' · ') || '—'}</p></div>
                </button>))}</div>}
            </GlassCard>
            {cal.data?.data_note && (
              <div style={{ display: 'flex', gap: 10, padding: '0 6px' }}><Info size={14} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: 2 }} /><p className={styles.note}>{cal.data.data_note}</p></div>
            )}
          </div>
        </div>
      )}

      <Sheet open={!!selected} onClose={() => setSelected(null)} title={selected ? dateIN(selected, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : ''}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="day-sheet">
          {selEvents.length === 0 ? (
            <EmptyState icon={<CalendarDays size={30} strokeWidth={1.5} />} title="No tracked events" message={selected && range && (selected < range.start || selected > range.end) ? 'This date is outside the tracked window.' : `${venue?.name ?? 'This venue'} has no tracked event on this day.`} />
          ) : selEvents.map(e => (
            <div key={e.id} className={styles.sheetEv}>
              <p className="t-callout" style={{ fontWeight: 650 }}>{e.title}</p>
              <p className="t-caption text-tertiary">{new Date(e.event_date).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: IST })} · {[e.status, e.source].filter(Boolean).join(' · ') || '—'}</p>
            </div>
          ))}
        </div>
      </Sheet>
    </Page>
  );
}
