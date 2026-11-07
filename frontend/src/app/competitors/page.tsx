'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts';
import {
  Eye, TrendingUp, MapPin, AlertTriangle, ChevronDown,
  Zap, Info, Globe
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getCompetitorIntel, getCompetitorGaps, getActivityFeed, getCities } from '@/lib/api';
import styles from './page.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

const PLATFORM_COLORS: Record<string, string> = {
  ticketmaster: 'hsl(4,88%,60%)',
  bookmyshow:   'hsl(38,90%,58%)',
  insider:      'hsl(211,100%,58%)',
  paytm:        'hsl(142,68%,45%)',
  zomato:       'hsl(4,88%,60%)',
};

function platColor(name: string) {
  const key = Object.keys(PLATFORM_COLORS).find(k => name.toLowerCase().includes(k));
  return key ? PLATFORM_COLORS[key] : 'var(--text-tertiary)';
}

// ─────────────────────────────────────────────────────────────────────────────
// Competitor Intelligence Page
// ─────────────────────────────────────────────────────────────────────────────

export default function CompetitorsPage() {
  const [city, setCity] = useState('Mumbai');

  const { data: citiesData } = useSWR('cities/competitors', () => getCities(), { shouldRetryOnError: false });
  const cities = citiesData?.cities ?? [];

  const { data: intel, isLoading: loadingIntel } = useSWR(
    `competitor-intel-${city}`,
    () => getCompetitorIntel(city),
    { refreshInterval: 120000, shouldRetryOnError: false }
  );

  const { data: gaps, isLoading: loadingGaps } = useSWR(
    'competitor-gaps', getCompetitorGaps,
    { refreshInterval: 180000, shouldRetryOnError: false }
  );

  const { data: feed, isLoading: loadingFeed } = useSWR(
    'activity-feed', getActivityFeed,
    { refreshInterval: 60000, shouldRetryOnError: false }
  );

  const platforms    = intel?.platforms ?? [];
  const eventActivity = intel?.event_activity ?? {};
  const gapList      = gaps?.gaps ?? [];
  const activities   = feed?.activities ?? feed?.items ?? [];

  // Platform event volume for bar chart
  const platformChart = platforms.map((p: any) => ({
    name: p.platform ?? p.name,
    events: p.event_count ?? p.active_events ?? 0,
  }));

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Competitor Intelligence" subtitle="Platform activity, market gaps, and competitive pricing" />

      <div className={styles.page}>

        {/* City selector */}
        <GlassCard className={styles.selectorCard} delay={0.04}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <MapPin size={16} color="var(--accent)" />
            <p className="t-headline text-primary">Analysing market:</p>
            <div className={styles.selectWrap}>
              <select
                className={`input ${styles.select}`}
                value={city}
                onChange={e => setCity(e.target.value)}
                disabled={cities.length === 0}
              >
                {cities.length > 0
                  ? cities.map(c => <option key={c.id ?? c.name} value={c.name}>{c.name}</option>)
                  : <option value="">Cities unavailable</option>
                }
              </select>
              <ChevronDown size={13} className={styles.selectIcon} />
            </div>
          </div>
          {cities.length === 0 && (
            <p className="t-caption text-tertiary" style={{ marginTop: 8 }}>Backend offline — start FastAPI to load cities</p>
          )}
        </GlassCard>

        <div className={styles.mainGrid}>
          {/* Platform activity */}
          <GlassCard className={styles.platformCard} delay={0.08}>
            <div className={styles.cardHead}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Globe size={15} color="var(--accent)" />
                <h2 className="t-headline text-primary">Platform Activity in {city}</h2>
              </div>
            </div>

            {loadingIntel ? (
              <div className="skeleton" style={{ height: 180, borderRadius: 12 }} />
            ) : platforms.length === 0 ? (
              <div className={styles.empty}>
                <Info size={20} color="var(--text-tertiary)" strokeWidth={1.5} />
                <p className="t-callout text-tertiary" style={{ marginTop: 10, textAlign: 'center' }}>
                  No competitor data yet. The competitor worker pulls from Ticketmaster and NewsAPI every 30 minutes.
                </p>
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={170}>
                  <BarChart data={platformChart} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barSize={30}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--divider)" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 12 }}
                      cursor={{ fill: 'var(--glass-fill)' }}
                    />
                    <Bar dataKey="events" radius={[4, 4, 0, 0]} name="Active events">
                      {platformChart.map((p: any, i: number) => (
                        <Cell key={i} fill={platColor(p.name)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>

                <div className={styles.platformList}>
                  {platforms.map((p: any, i: number) => (
                    <motion.div
                      key={i}
                      className={styles.platformRow}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.12 + i * 0.05 }}
                    >
                      <div className={styles.platDot} style={{ background: platColor(p.platform ?? p.name) }} />
                      <span className="t-callout text-primary" style={{ fontWeight: 600, flex: 1 }}>
                        {p.platform ?? p.name}
                      </span>
                      {p.event_count != null && (
                        <span className="t-callout text-primary" style={{ fontWeight: 700 }}>{p.event_count} events</span>
                      )}
                      {p.avg_price != null && (
                        <span className="t-caption text-tertiary">avg ₹{p.avg_price.toLocaleString('en-IN')}</span>
                      )}
                    </motion.div>
                  ))}
                </div>
              </>
            )}
          </GlassCard>

          {/* Market gaps */}
          <GlassCard className={styles.gapsCard} delay={0.12}>
            <div className={styles.cardHead}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Zap size={15} color="var(--positive)" />
                <h2 className="t-headline text-primary">Market Gaps</h2>
              </div>
              <span className="t-caption text-tertiary">District opportunities</span>
            </div>

            {loadingGaps ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 56, borderRadius: 10 }} />)}
              </div>
            ) : gapList.length === 0 ? (
              <div className={styles.empty}>
                <p className="t-callout text-tertiary" style={{ textAlign: 'center' }}>
                  Gap analysis runs when competitor data is available. Start the competitor worker.
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {gapList.map((g: any, i: number) => (
                  <motion.div
                    key={i}
                    className={styles.gapRow}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.14 + i * 0.05 }}
                  >
                    <div className={styles.gapIndicator} />
                    <div style={{ flex: 1 }}>
                      <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{g.city ?? g.market}</p>
                      <p className="t-caption text-tertiary">{g.gap_description ?? g.description}</p>
                    </div>
                    {g.opportunity_score != null && (
                      <span style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--positive)' }}>
                        {g.opportunity_score}
                      </span>
                    )}
                  </motion.div>
                ))}
              </div>
            )}
          </GlassCard>
        </div>

        {/* Live activity feed */}
        <GlassCard className={styles.feedCard} delay={0.18}>
          <div className={styles.cardHead}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Eye size={15} color="var(--accent)" />
              <h2 className="t-headline text-primary">Live Activity Feed</h2>
            </div>
            <span className="t-caption text-tertiary">Refreshes every 60s</span>
          </div>

          {loadingFeed ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[1, 2, 3, 4, 5].map(i => <div key={i} className="skeleton" style={{ height: 52, borderRadius: 10 }} />)}
            </div>
          ) : activities.length === 0 ? (
            <div className={styles.empty}>
              <AlertTriangle size={20} color="var(--text-tertiary)" strokeWidth={1.5} />
              <p className="t-callout text-tertiary" style={{ marginTop: 10, textAlign: 'center' }}>
                Activity feed is empty. The competitor activity worker pulls event announcements, ticket launches, and pricing changes from Ticketmaster and BookMyShow every hour.
              </p>
            </div>
          ) : (
            <div className={styles.feedList}>
              {activities.map((a: any, i: number) => (
                <motion.div
                  key={i}
                  className={styles.feedRow}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                >
                  <div className={styles.feedDot} style={{ background: platColor(a.platform ?? '') }} />
                  <div style={{ flex: 1 }}>
                    <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{a.title ?? a.event_name}</p>
                    <p className="t-caption text-tertiary">
                      {a.platform && `${a.platform} · `}
                      {a.city && `${a.city} · `}
                      {a.timestamp
                        ? new Date(a.timestamp).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
                        : 'Recent'}
                    </p>
                  </div>
                  {a.price != null && (
                    <span className="t-callout text-primary" style={{ fontWeight: 700, flexShrink: 0 }}>
                      ₹{a.price.toLocaleString('en-IN')}
                    </span>
                  )}
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
