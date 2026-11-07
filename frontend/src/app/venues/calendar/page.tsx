'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { CalendarDays, ChevronDown, AlertCircle, Info } from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getCities, getCityVenues, getVenueCalendar, VenueCalendarResponse } from '@/lib/api';
import styles from './page.module.css';

export default function VenueCalendarPage() {
  const [city, setCity] = useState('');
  const [venueId, setVenueId] = useState('');
  const [months, setMonths] = useState('3');
  const [result, setResult] = useState<VenueCalendarResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: citiesData } = useSWR('cities/venue-calendar', () => getCities(), { shouldRetryOnError: false });
  const { data: venuesData } = useSWR(
    city ? `venues/${city}` : null,
    () => getCityVenues(city),
    { shouldRetryOnError: false }
  );

  const cities = citiesData?.cities ?? [];
  const venues = (venuesData?.venues ?? []).filter(
    (v): v is typeof v & { id: string } => v.id !== null
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!venueId) {
      setError('Select a venue to view its calendar.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await getVenueCalendar(venueId, Number(months) || 3);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load calendar. Ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Venue Availability Calendar" subtitle="Weekend-by-weekend booked/open view, built from real tracked events" />

      <div className={styles.page}>
        <GlassCard className={styles.formCard} delay={0.04}>
          <div className={styles.formHeader}>
            <CalendarDays size={18} color="var(--accent)" />
            <div>
              <h2 className="t-headline text-primary">Select a Venue</h2>
              <p className="t-footnote text-tertiary">Choose a city, then a venue, to see its real booked/open weekends</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className={styles.form}>
            <div className={styles.formGrid}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="cal-city">City</label>
                <div className={styles.selectWrap}>
                  <select
                    id="cal-city" className={`input ${styles.select}`} value={city}
                    onChange={e => { setCity(e.target.value); setVenueId(''); setResult(null); }}
                    required disabled={cities.length === 0}
                  >
                    <option value="">{cities.length > 0 ? 'Select city...' : 'Cities unavailable'}</option>
                    {cities.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="cal-venue">Venue</label>
                <div className={styles.selectWrap}>
                  <select
                    id="cal-venue" className={`input ${styles.select}`} value={venueId}
                    onChange={e => setVenueId(e.target.value)}
                    required disabled={!city || venues.length === 0}
                  >
                    <option value="">{!city ? 'Select a city first' : venues.length === 0 ? 'No venues on file' : 'Select venue...'}</option>
                    {venues.map(v => (
                      <option key={v.id} value={v.id}>{v.name} ({v.capacity?.toLocaleString('en-IN') ?? '—'} cap)</option>
                    ))}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="cal-months">Months Ahead</label>
                <div className={styles.selectWrap}>
                  <select id="cal-months" className={`input ${styles.select}`} value={months} onChange={e => setMonths(e.target.value)}>
                    {[1, 2, 3, 6, 12].map(m => <option key={m} value={m}>{m} month{m > 1 ? 's' : ''}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>
            </div>

            {error && (
              <div className={styles.errorBox}>
                <AlertCircle size={16} color="var(--negative)" />
                <span className="t-callout" style={{ color: 'var(--negative)' }}>{error}</span>
              </div>
            )}

            <button type="submit" className="btn btn-primary" disabled={loading} style={{ alignSelf: 'flex-start' }}>
              {loading ? 'Loading calendar...' : 'View Calendar'}
            </button>
          </form>
        </GlassCard>

        {result && (
          <motion.div className={styles.resultWrap} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <GlassCard style={{ padding: 22 }} delay={0}>
              <h2 className="t-title2 text-primary" style={{ fontWeight: 800, marginBottom: 4 }}>{result.venue.name}</h2>
              <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>
                {result.venue.city} · {result.venue.capacity?.toLocaleString('en-IN') ?? '—'} capacity · {result.range.start} to {result.range.end}
              </p>
              <div className={styles.summaryRow}>
                <div className={styles.summaryChip}>
                  <span className="t-title2 text-primary" style={{ fontWeight: 800 }}>{result.summary.booked_weekends}</span>
                  <span className="t-caption text-tertiary">Booked weekends</span>
                </div>
                <div className={styles.summaryChip}>
                  <span className="t-title2" style={{ fontWeight: 800, color: 'var(--positive)' }}>{result.summary.open_weekends}</span>
                  <span className="t-caption text-tertiary">Open weekends</span>
                </div>
                <div className={styles.summaryChip}>
                  <span className="t-title2 text-primary" style={{ fontWeight: 800 }}>{result.summary.total_tracked_events}</span>
                  <span className="t-caption text-tertiary">Tracked weekend events</span>
                </div>
              </div>
            </GlassCard>

            <GlassCard style={{ padding: 22 }} delay={0.05}>
              <h3 className="t-headline text-primary" style={{ marginBottom: 14 }}>Week-by-Week</h3>
              <div className={styles.weekGrid}>
                {result.weeks.map(w => (
                  <div key={w.week_start} className={`${styles.weekCell} ${w.is_weekend_booked ? styles.weekCellBooked : styles.weekCellOpen}`}>
                    <span className={styles.weekLabel}>{new Date(w.week_start).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}</span>
                    <span className={styles.weekStatus} style={{ color: w.is_weekend_booked ? 'var(--negative)' : 'var(--positive)' }}>
                      {w.is_weekend_booked ? 'Booked' : 'Open'}
                    </span>
                    {w.weekend_events.slice(0, 1).map(ev => (
                      <span key={ev.id} className={styles.weekEventTitle} title={ev.title}>{ev.title}</span>
                    ))}
                  </div>
                ))}
              </div>
            </GlassCard>

            <GlassCard style={{ padding: 18 }} delay={0.1}>
              <div className={styles.noteBox}>
                <Info size={15} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: 1 }} />
                <p className="t-caption text-tertiary" style={{ lineHeight: 1.6 }}>{result.data_note}</p>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {!result && !loading && (
          <GlassCard className={styles.placeholder} delay={0.1}>
            <CalendarDays size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Select a venue above to see its availability calendar</p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
