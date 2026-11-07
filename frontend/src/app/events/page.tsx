'use client';

import useSWR from 'swr';
import { motion } from 'framer-motion';
import {
  Ticket, TrendingUp, AlertCircle, CheckCircle,
  Info, Music2
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getDashboardSummary } from '@/lib/api';
import styles from './page.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fillColor(pct: number | null) {
  if (!pct) return 'var(--text-tertiary)';
  if (pct >= 70) return 'var(--positive)';
  if (pct >= 50) return 'var(--accent)';
  return 'var(--negative)';
}

function fillStatus(pct: number | null) {
  if (!pct) return { label: 'No data', icon: <Info size={13} />, color: 'var(--text-tertiary)' };
  if (pct >= 70) return { label: 'On track', icon: <CheckCircle size={13} />, color: 'var(--positive)' };
  if (pct >= 50) return { label: 'Monitor', icon: <AlertCircle size={13} />, color: 'var(--accent)' };
  return { label: 'Action needed', icon: <AlertCircle size={13} />, color: 'var(--negative)' };
}

function fmtPrice(min: number | null, max: number | null) {
  if (!min && !max) return '—';
  if (min && max && min !== max) return `₹${min.toLocaleString('en-IN')} – ₹${max.toLocaleString('en-IN')}`;
  return `₹${(min ?? max)!.toLocaleString('en-IN')}`;
}

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

// ── Deal Modeler inputs ───────────────────────────────────────────────────────
// No hardcoded values — the modeler is shown as a form placeholder that sends to pricing endpoint

// ═══════════════════════════════════════════════════════════════════════════════
// Events / Fill Rate Monitor Page
// ═══════════════════════════════════════════════════════════════════════════════

export default function EventsPage() {
  const { data: summary, isLoading } = useSWR(
    'dashboard/events', getDashboardSummary,
    { refreshInterval: 60000, shouldRetryOnError: false }
  );

  const events = summary?.upcoming_events ?? [];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Event Fill Rate Monitor" subtitle="Sales velocity, ticket inventory, and action triggers" />

      <div className={styles.page}>

        {/* Summary banner */}
        <motion.div
          className={styles.banner}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          {[
            { label: 'Events tracked', value: events.length || '—', sub: 'from Ticketmaster & Insider' },
            { label: 'On sale now', value: events.filter(e => e.min_price !== null).length || '—', sub: 'with ticket pricing' },
            { label: 'This month', value: events.filter(e => {
              const d = daysUntil(e.event_date);
              return d !== null && d >= 0 && d <= 30;
            }).length || '—', sub: 'within 30 days' },
          ].map(({ label, value, sub }, i) => (
            <div key={label} className={styles.bannerStat}>
              <span style={{ fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.05em', color: 'var(--text-primary)', lineHeight: 1 }}>{value}</span>
              <span className="t-label text-primary" style={{ fontWeight: 600 }}>{label}</span>
              <span className="t-caption text-tertiary">{sub}</span>
            </div>
          ))}
        </motion.div>

        {/* Events list with fill rate monitor */}
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="skeleton" style={{ height: 200, borderRadius: 20 }} />
            ))}
          </div>
        ) : events.length === 0 ? (
          <GlassCard style={{ padding: 48, textAlign: 'center' }} delay={0.1}>
            <Music2 size={36} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>No events synced yet</p>
            <p className="t-callout text-tertiary" style={{ marginTop: 8, maxWidth: 360, margin: '8px auto 0', lineHeight: 1.65 }}>
              The event sync worker pulls from Ticketmaster and Insider every 4 hours. Start the worker, or add events manually via the admin API.
            </p>
          </GlassCard>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {events.map((e, i) => {
              const days = daysUntil(e.event_date);
              // Fill rate is not tracked yet — the fill-rate worker (Sprint 6A)
              // will populate Event.fill_rate from real ticket sales. Until then
              // we show "no data" rather than a fabricated estimate.
              const simFill: number | null = null;
              const status = fillStatus(simFill);

              return (
                <GlassCard key={e.id} delay={0.08 + i * 0.06}>
                  <div className={styles.eventCard}>
                    {/* Left: meta */}
                    <div className={styles.eventMeta}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <Ticket size={14} color="var(--accent)" />
                        <p className="t-callout" style={{ fontWeight: 700, color: 'var(--accent)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          {e.source ?? 'Platform'}
                        </p>
                      </div>
                      <h3 className="t-title2 text-primary" style={{ fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.2 }}>
                        {e.name}
                      </h3>
                      <p className="t-callout text-tertiary" style={{ marginTop: 6 }}>
                        {[e.venue, e.city].filter(Boolean).join(' · ')}
                      </p>
                      {e.event_date && (
                        <p className="t-footnote text-secondary" style={{ marginTop: 4 }}>
                          {new Date(e.event_date).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' })}
                          {days !== null && days >= 0 && <span style={{ color: days <= 14 ? 'var(--warning)' : 'var(--text-tertiary)' }}> · {days} days away</span>}
                        </p>
                      )}
                      <p className="t-callout text-primary" style={{ fontWeight: 700, marginTop: 10 }}>
                        {fmtPrice(e.min_price, e.max_price)}
                      </p>
                    </div>

                    {/* Center: fill rate ring + status */}
                    <div className={styles.fillCenter}>
                      <div className={styles.fillRing}>
                        <svg width={90} height={90} viewBox="0 0 90 90" style={{ transform: 'rotate(-90deg)' }}>
                          <circle cx={45} cy={45} r={38} fill="none" stroke="var(--divider)" strokeWidth={6} />
                          {simFill !== null && (
                            <motion.circle
                              cx={45} cy={45} r={38} fill="none"
                              stroke={fillColor(simFill)} strokeWidth={6}
                              strokeDasharray={`${(simFill / 100) * 238.76} 238.76`}
                              strokeLinecap="round"
                              initial={{ strokeDasharray: '0 238.76' }}
                              animate={{ strokeDasharray: `${(simFill / 100) * 238.76} 238.76` }}
                              transition={{ duration: 0.8, delay: 0.2 + i * 0.1, ease: [0.25, 0.46, 0.45, 0.94] }}
                            />
                          )}
                        </svg>
                        <div className={styles.fillLabel}>
                          <span style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.04em', color: fillColor(simFill) }}>
                            {simFill !== null ? `${simFill}%` : '—'}
                          </span>
                          <span className="t-caption text-tertiary" style={{ fontSize: '0.625rem' }}>projected</span>
                        </div>
                      </div>
                      <div className={styles.statusBadge} style={{ color: status.color, background: status.color + '18', borderColor: status.color + '30' }}>
                        {status.icon} {status.label}
                      </div>
                    </div>

                    {/* Right: sales velocity (not yet tracked) */}
                    <div className={styles.velocityWrap}>
                      <p className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem', marginBottom: 8 }}>
                        Sales Velocity
                      </p>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, height: 90 }}>
                        <Info size={13} color="var(--text-tertiary)" />
                        <span className="t-caption text-tertiary">Not tracked yet — pending fill-rate worker</span>
                      </div>

                      {/* Action buttons — contextual */}
                      <div className={styles.actions}>
                        <button className={styles.actionBtn}>
                          <TrendingUp size={12} /> Price optimizer
                        </button>
                      </div>
                    </div>
                  </div>
                </GlassCard>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
