'use client';

import useSWR from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import {
  TrendingUp, MapPin, Flame, Music2, ChevronRight,
  Mic2, ArrowUpRight, Calendar, Globe, Users,
  AlertCircle, Info, Zap, Clock
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import {
  getDashboardSummary, getDashboardAlerts, getBriefing,
  DashboardAlert, TrendingEntity, CityHeatItem, UpcomingEvent
} from '@/lib/api';
import styles from './page.module.css';
import Link from 'next/link';

// ── Helpers ──────────────────────────────────────────────────────────────────

function scoreColor(score: number | null): string {
  if (!score) return 'var(--text-tertiary)';
  if (score >= 70) return 'var(--positive)';
  if (score >= 45) return 'var(--accent)';
  return 'var(--warning)';
}

function alertIcon(type: DashboardAlert['type']) {
  switch (type) {
    case 'breakout':    return <TrendingUp size={13} />;
    case 'buzz':        return <Flame size={13} />;
    case 'opportunity': return <Zap size={13} />;
    default:            return <Info size={13} />;
  }
}

function alertColor(type: DashboardAlert['type']): string {
  switch (type) {
    case 'breakout':    return 'var(--positive)';
    case 'buzz':        return 'var(--accent)';
    case 'opportunity': return 'var(--warning)';
    default:            return 'var(--text-tertiary)';
  }
}

function formatDate(iso: string | null): { month: string; day: string } {
  if (!iso) return { month: '—', day: '—' };
  const d = new Date(iso);
  return {
    month: d.toLocaleString('en-IN', { month: 'short' }).toUpperCase(),
    day:   String(d.getDate()),
  };
}

// ── Empty states ─────────────────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div className={styles.emptyState}>
      <p className="t-callout text-tertiary">{message}</p>
    </div>
  );
}

function SkeletonRow({ count = 4 }: { count?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 44, borderRadius: 10 }} />
      ))}
    </div>
  );
}

// ── PIE chart colours ────────────────────────────────────────────────────────
const PIE_COLORS = [
  'hsl(211,100%,58%)',
  'hsl(142,68%,45%)',
  'hsl(38,90%,58%)',
  'hsl(4,88%,60%)',
  'hsl(190,80%,50%)',
  'hsl(210,15%,60%)',
];

// ═══════════════════════════════════════════════════════════════════════════════
// Dashboard Page
// ═══════════════════════════════════════════════════════════════════════════════

export default function DashboardPage() {
  const { data: summary, isLoading: loadingSum } = useSWR(
    'dashboard/summary', getDashboardSummary,
    { refreshInterval: 90000, shouldRetryOnError: false }
  );
  const { data: alertsData, isLoading: loadingAlerts } = useSWR(
    'dashboard/alerts', getDashboardAlerts,
    { refreshInterval: 120000, shouldRetryOnError: false }
  );
  const { data: briefing, isLoading: loadingBriefing } = useSWR(
    'executive/briefing', getBriefing,
    { refreshInterval: 0, revalidateOnFocus: false, shouldRetryOnError: false }
  );

  const hero      = summary?.hero;
  const entities  = summary?.trending_entities ?? [];
  const cities    = summary?.city_heat ?? [];
  const events    = summary?.upcoming_events ?? [];
  const cats      = summary?.category_breakdown ?? [];
  const alerts    = alertsData?.alerts ?? [];
  const backendUp = !(!summary && !loadingSum);

  const now = new Date();
  const greeting =
    now.getHours() < 12 ? 'Good morning'
    : now.getHours() < 17 ? 'Good afternoon'
    : 'Good evening';

  return (
    <div className={styles.page}>
      <Topbar
        title="LiveIQ"
        subtitle={`${greeting} — ${backendUp ? 'live data from your backend' : 'backend offline — start the FastAPI server'}`}
      />

      <div className={styles.content}>

        {/* ── Offline banner ── */}
        {!loadingSum && !summary && (
          <motion.div
            className={styles.offlineBanner}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <AlertCircle size={14} />
            <span className="t-callout">
              Backend not running — start it with{' '}
              <code>uvicorn main:app --reload</code> from the{' '}
              <code>backend/</code> directory. Dashboard will populate automatically.
            </span>
          </motion.div>
        )}

        {/* ── Hero strip ── */}
        <motion.div
          className={styles.heroStrip}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
        >
          {[
            { num: hero?.total_entities,    label: 'Artists & acts\nbeing tracked',    loading: loadingSum },
            { num: hero?.total_cities,      label: 'Cities with\nlive intelligence',   loading: loadingSum },
            { num: hero?.active_cities,     label: 'Active District\nmarkets',          loading: loadingSum },
            { num: hero?.total_events,      label: 'Events synced\nfrom platforms',    loading: loadingSum },
            { num: hero?.international_acts,label: 'International\nacts tracked',       loading: loadingSum },
          ].map(({ num, label, loading }, i) => (
            <div key={i} className={styles.heroStat}>
              {loading ? (
                <div className="skeleton" style={{ width: 60, height: 40, borderRadius: 8 }} />
              ) : (
                <span className={styles.heroNumber}>{num ?? '—'}</span>
              )}
              <span className={styles.heroLabel}>{label}</span>
              {i < 4 && <div className={styles.heroDivider} />}
            </div>
          ))}
        </motion.div>

        {/* ── Alert strip ── */}
        <GlassCard className={styles.alertsCard} delay={0.06}>
          <div className={styles.cardHead}>
            <div className={styles.row}>
              <Flame size={14} color="var(--negative)" />
              <span className="t-headline text-primary">Live Alerts</span>
            </div>
            <Link href="/intelligence" className={styles.textLink}>View intelligence</Link>
          </div>

          {loadingAlerts ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[1, 2, 3].map(i => (
                <div key={i} className="skeleton" style={{ height: 36, borderRadius: 8 }} />
              ))}
            </div>
          ) : alerts.length === 0 ? (
            <EmptyState message="No alerts yet — run the entity metrics worker to generate breakout and opportunity signals." />
          ) : (
            <div className={styles.alertList}>
              {alerts.map((a, i) => (
                <motion.div
                  key={i}
                  className={styles.alertItem}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.08 + i * 0.055, ease: [0.25, 0.46, 0.45, 0.94] }}
                >
                  <div className={styles.alertIcon} style={{ color: alertColor(a.type) }}>
                    {alertIcon(a.type)}
                  </div>
                  <div className={styles.alertBody}>
                    <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{a.title}</span>
                    <span className="t-footnote text-tertiary">{a.message}</span>
                  </div>
                  <span className={styles.alertBadge} style={{
                    background: a.severity === 'high' ? 'var(--negative-dim)' : a.severity === 'medium' ? 'var(--accent-dim)' : 'var(--glass-fill)',
                    color:      a.severity === 'high' ? 'var(--negative)' : a.severity === 'medium' ? 'var(--accent)' : 'var(--text-tertiary)',
                  }}>
                    {a.severity}
                  </span>
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>

        {/* ── Main 3-col grid ── */}
        <div className={styles.mainGrid}>

          {/* Col 1: Trending entities */}
          <GlassCard className={styles.trendingCard} delay={0.1}>
            <div className={styles.cardHead}>
              <div className={styles.row}>
                <Mic2 size={15} color="var(--accent)" />
                <h2 className="t-headline text-primary">Trending Artists & Acts</h2>
              </div>
              <Link href="/intelligence" className={styles.textLink}>All</Link>
            </div>

            {loadingSum ? <SkeletonRow count={5} /> :
             entities.length === 0 ? (
               <EmptyState message="No entity metrics yet. Run the Celery worker to populate scores." />
             ) : (
              <div className={styles.artistList}>
                {entities.slice(0, 7).map((e: TrendingEntity, i) => (
                  <motion.div
                    key={e.id}
                    className={styles.artistRow}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.12 + i * 0.05, ease: [0.25, 0.46, 0.45, 0.94] }}
                  >
                    <div className={styles.artistAvatar}>
                      <span>{e.name.charAt(0).toUpperCase()}</span>
                      {e.composite_score >= 70 && <div className={styles.hotDot} />}
                    </div>
                    <div className={styles.artistInfo}>
                      <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{e.name}</span>
                      <span className="t-footnote text-tertiary">
                        {e.category ?? e.type}
                        {e.is_international && ' · International'}
                      </span>
                    </div>
                    <div className={styles.artistRight}>
                      <span style={{ fontSize: '1.1rem', fontWeight: 700, letterSpacing: '-0.03em', color: scoreColor(e.composite_score) }}>
                        {e.composite_score}
                      </span>
                      {e.google_trend != null && e.google_trend > e.composite_score && (
                        <span className={styles.trendUp}>
                          <ArrowUpRight size={11} />
                          Trending
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </GlassCard>

          {/* Col 2: Category breakdown chart */}
          <GlassCard className={styles.chartCard} delay={0.14}>
            <div className={styles.cardHead}>
              <div className={styles.row}>
                <TrendingUp size={15} color="var(--accent)" />
                <h2 className="t-headline text-primary">Portfolio by Category</h2>
              </div>
              <Link href="/intelligence" className={styles.textLink}>Intelligence</Link>
            </div>

            {loadingSum ? (
              <div className="skeleton" style={{ height: 190, borderRadius: 12 }} />
            ) : cats.length === 0 ? (
              <EmptyState message="No category data yet." />
            ) : (
              <>
                <ResponsiveContainer width="100%" height={190}>
                  <BarChart data={cats} margin={{ top: 8, right: 4, left: -20, bottom: 0 }} barSize={22}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--divider)" vertical={false} />
                    <XAxis
                      dataKey="category"
                      tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                      axisLine={false} tickLine={false}
                      interval={0}
                      tickFormatter={(v: string) => v.length > 9 ? v.slice(0, 8) + '…' : v}
                    />
                    <YAxis tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 12 }}
                      cursor={{ fill: 'var(--glass-fill)' }}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {cats.map((_, idx) => (
                        <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className={styles.chartFooter}>
                  <span className="t-footnote text-tertiary">
                    {summary?.hero.total_entities ?? 0} entities across {cats.length} categories
                  </span>
                </div>
              </>
            )}
          </GlassCard>

          {/* Col 3: City heat */}
          <GlassCard className={styles.cityCard} delay={0.18}>
            <div className={styles.cardHead}>
              <div className={styles.row}>
                <MapPin size={15} color="var(--accent)" />
                <h2 className="t-headline text-primary">City Heat Index</h2>
              </div>
              <Link href="/markets" className={styles.textLink}>Markets</Link>
            </div>

            {loadingSum ? <SkeletonRow count={6} /> :
             cities.length === 0 ? (
               <EmptyState message="No city data. Seed cities with seed_cities.py." />
             ) : (
              <div className={styles.cityList}>
                {cities.map((c: CityHeatItem, i) => {
                  const score = c.music_score ?? 0;
                  return (
                    <motion.div
                      key={c.city}
                      className={styles.cityRow}
                      initial={{ opacity: 0, x: 8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.2 + i * 0.045, ease: [0.25, 0.46, 0.45, 0.94] }}
                    >
                      <div className={styles.cityMeta}>
                        <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{c.city}</span>
                        <span className="t-caption" style={{ color: c.active_on_district ? 'var(--positive)' : 'var(--text-tertiary)' }}>
                          {c.active_on_district ? 'Active' : `T${c.tier} · Expansion`}
                        </span>
                      </div>
                      <div className={styles.cityBar}>
                        <motion.div
                          className={styles.cityFill}
                          initial={{ width: 0 }}
                          animate={{ width: `${score}%` }}
                          transition={{ duration: 0.7, delay: 0.28 + i * 0.05, ease: [0.25, 0.46, 0.45, 0.94] }}
                          style={{ background: scoreColor(score) }}
                        />
                      </div>
                      <span style={{ fontSize: '0.9rem', fontWeight: 700, color: scoreColor(score), minWidth: 28, textAlign: 'right' }}>
                        {score}
                      </span>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </GlassCard>
        </div>

        {/* ── Bottom row ── */}
        <div className={styles.bottomGrid}>

          {/* Upcoming events */}
          <GlassCard className={styles.eventsCard} delay={0.24}>
            <div className={styles.cardHead}>
              <div className={styles.row}>
                <Music2 size={15} color="var(--accent)" />
                <h2 className="t-headline text-primary">Events on Platforms</h2>
              </div>
              <Link href="/events" className={styles.textLink}>Monitor all</Link>
            </div>

            {loadingSum ? <SkeletonRow count={4} /> :
             events.length === 0 ? (
               <EmptyState message="No events synced yet. The event sync worker pulls from Ticketmaster and Insider every 4 hours." />
             ) : (
              <div className={styles.eventList}>
                {events.map((e: UpcomingEvent, i) => {
                  const { month, day } = formatDate(e.event_date);
                  return (
                    <motion.div
                      key={e.id}
                      className={styles.eventRow}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.28 + i * 0.05, ease: [0.25, 0.46, 0.45, 0.94] }}
                    >
                      <div className={styles.eventDate}>
                        <span style={{ fontSize: '0.625rem', fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.05em' }}>{month}</span>
                        <span style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>{day}</span>
                      </div>
                      <div className={styles.eventInfo}>
                        <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{e.name}</span>
                        <span className="t-footnote text-tertiary">
                          {[e.venue, e.city].filter(Boolean).join(' · ')}
                          {e.source && ` · ${e.source}`}
                        </span>
                      </div>
                      {(e.min_price != null || e.max_price != null) && (
                        <div className={styles.eventPrice}>
                          <span className="t-caption text-tertiary">from</span>
                          <span className="t-callout text-primary" style={{ fontWeight: 700 }}>
                            {e.min_price != null ? `₹${e.min_price.toLocaleString('en-IN')}` : '—'}
                          </span>
                        </div>
                      )}
                    </motion.div>
                  );
                })}
              </div>
            )}
          </GlassCard>

          {/* Entity type breakdown */}
          <GlassCard className={styles.typeCard} delay={0.28}>
            <div className={styles.cardHead}>
              <div className={styles.row}>
                <Users size={15} color="var(--accent)" />
                <h2 className="t-headline text-primary">Portfolio Mix</h2>
              </div>
              <span className="t-footnote text-tertiary">{hero?.total_entities ?? 0} total</span>
            </div>

            {loadingSum ? (
              <div className="skeleton" style={{ height: 160, borderRadius: 12 }} />
            ) : (summary?.type_breakdown ?? []).length === 0 ? (
              <EmptyState message="No entity data yet." />
            ) : (
              <>
                <ResponsiveContainer width="100%" height={150}>
                  <PieChart>
                    <Pie
                      data={summary!.type_breakdown}
                      dataKey="count"
                      nameKey="type"
                      cx="50%"
                      cy="50%"
                      innerRadius={42}
                      outerRadius={68}
                      paddingAngle={3}
                      strokeWidth={0}
                    >
                      {summary!.type_breakdown.map((_, idx) => (
                        <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 12 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className={styles.legendGrid}>
                  {summary!.type_breakdown.map((t, idx) => (
                    <div key={t.type} className={styles.legendItem}>
                      <div className={styles.legendDot} style={{ background: PIE_COLORS[idx % PIE_COLORS.length] }} />
                      <span className="t-caption text-secondary">{t.type}</span>
                      <span className="t-caption text-primary" style={{ fontWeight: 700, marginLeft: 'auto' }}>{t.count}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </GlassCard>

          {/* AI briefing */}
          <GlassCard className={styles.briefingCard} delay={0.32}>
            <div className={styles.cardHead}>
              <div>
                <h2 className="t-headline text-primary">AI Briefing</h2>
                <p className="t-footnote text-tertiary" style={{ marginTop: 2 }}>
                  {briefing
                    ? `Updated ${new Date(briefing.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                    : 'Groq Llama 3.3 70B'}
                </p>
              </div>
              <span className="badge badge-blue" style={{ fontSize: '0.7rem' }}>AI</span>
            </div>

            <div className={styles.briefingBody}>
              {loadingBriefing ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {[95, 85, 100, 70, 88, 60].map((w, i) => (
                    <div key={i} className="skeleton" style={{ height: 12, width: `${w}%` }} />
                  ))}
                </div>
              ) : briefing ? (
                <p className="t-callout text-secondary" style={{ lineHeight: 1.72 }}>{briefing.briefing}</p>
              ) : (
                <p className="t-callout text-tertiary" style={{ lineHeight: 1.6 }}>
                  AI briefing is unavailable. The backend may be offline, or entity metrics have not been collected yet. Run the metrics worker and ensure the Groq API key is set.
                </p>
              )}
            </div>

            <div className={styles.briefingActions}>
              <Link href="/executive" className={styles.cta}>
                Executive Suite <ChevronRight size={13} />
              </Link>
              <Link href="/copilot" className={styles.ctaSecondary}>
                Ask AI Copilot <ChevronRight size={13} />
              </Link>
            </div>
          </GlassCard>
        </div>

        {/* ── Footer timestamp ── */}
        {summary && (
          <motion.p
            className="t-caption text-tertiary"
            style={{ textAlign: 'center', paddingBottom: 8 }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            Last refreshed: {new Date(summary.generated_at).toLocaleString('en-IN')} · Auto-refreshes every 90s
          </motion.p>
        )}
      </div>
    </div>
  );
}
