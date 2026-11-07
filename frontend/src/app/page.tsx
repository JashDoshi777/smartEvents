'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { Ring } from '@/components/dashboard/Ring';
import { CountUp } from '@/components/dashboard/CountUp';
import { getDashboardSummaryScoped, getDashboardAlerts, getBriefing } from '@/lib/api';
import { inrCompact, num, greeting, dateIN, timeAgo } from '@/lib/format';
import styles from './page.module.css';

const TIP = { background: 'var(--glass-fill-strong)', border: 'none', borderRadius: 12, fontSize: 13, color: 'var(--text-primary)' };
const ALERT_LABEL = { breakout: 'Breakout', buzz: 'In the news', opportunity: 'Market gap', info: 'Info' } as const;

function Head({ title, href, cta }: { title: string; href?: string; cta?: string }) {
  return (
    <div className={styles.head}>
      <h2 className={styles.title}>{title}</h2>
      {href && <Link href={href} className={styles.link}>{cta ?? 'See all'}</Link>}
    </div>
  );
}

export default function DashboardPage() {
  const { scope, isIndia } = useMarketScope();
  const sum = useSWR(['dashboard/summary', scope], () => getDashboardSummaryScoped(scope), { refreshInterval: 90000 });
  const al = useSWR('dashboard/alerts', getDashboardAlerts, { refreshInterval: 120000 });
  const br = useSWR('executive/briefing', getBriefing, { revalidateOnFocus: false });
  const [allAlerts, setAllAlerts] = useState(false);

  const s = sum.data;
  const hero = s?.hero;
  const loading = !s && !sum.error;
  const alerts = al.data?.alerts ?? [];
  const cats = s?.category_breakdown ?? [];
  const types = s?.type_breakdown ?? [];
  const label = isIndia ? 'Indian' : 'international';
  const shown = allAlerts ? alerts : alerts.slice(0, 4);

  return (
    <Page title="Dashboard" subtitle={`${greeting()}. ${isIndia ? 'India market snapshot' : 'Global market snapshot'}`}>
      {sum.error && !s && <GlassCard><ErrorState message="Couldn’t reach the LiveIQ backend." onRetry={() => sum.mutate()} /></GlassCard>}

      <div className={styles.bento}>
        <GlassCard className={`${styles.tile} ${styles.hero}`}>
          <h2 className={styles.title}>{isIndia ? 'India' : 'Global'} portfolio</h2>
          {loading ? <Skeleton height={190} radius={16} /> : (<>
            <div className={styles.heroTop}>
              <div>
                <div className={`num-rounded ${styles.big}`}><CountUp value={hero?.total_entities} /></div>
                <p className="t-body text-secondary" style={{ marginTop: 10 }}>{label} acts tracked</p>
                {types.length > 0 && <p className="t-footnote text-tertiary" style={{ marginTop: 2 }}>{types.slice(0, 4).map(t => `${num(t.count)} ${t.type.replace('_', ' ')}`).join(' · ')}</p>}
              </div>
              <Ring value={hero?.avg_composite_score} size={112} stroke={12} color="var(--accent)">
                <div><div className="num-rounded" style={{ fontSize: '1.7rem', fontWeight: 700 }}>{hero?.avg_composite_score ?? '—'}</div><div className="t-caption text-tertiary">avg score</div></div>
              </Ring>
            </div>
            <div className={styles.cols}>
              <div className={styles.col}><span className={`num-rounded ${styles.colVal}`}>{num(hero?.entities_with_metrics)}</span><span className="t-footnote text-secondary">Scored</span></div>
              <div className={styles.col}><span className={`num-rounded ${styles.colVal}`}>{num(hero?.active_cities)}</span><span className="t-footnote text-secondary">Cities live · {num(hero?.expansion_targets)} to open</span></div>
              <div className={styles.col}><span className={`num-rounded ${styles.colVal}`}>{num(hero?.total_events)}</span><span className="t-footnote text-secondary">Events synced</span></div>
            </div>
          </>)}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.brief}`} delay={0.04}>
          <Head title="AI briefing" href="/executive" cta="Executive suite" />
          {br.isLoading && !br.data ? <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>{[95, 85, 100, 70, 88, 60].map((w, i) => <Skeleton key={i} height={12} width={`${w}%`} />)}</div>
            : br.data ? (<>
              <p className={`t-body text-secondary ${styles.briefing}`}>{br.data.briefing}</p>
              <p className="t-footnote text-tertiary" style={{ marginTop: 'auto' }}>Updated {timeAgo(br.data.generated_at)} · <Link href="/copilot" className={styles.link} style={{ fontSize: 'inherit' }}>Ask Copilot</Link></p>
            </>) : <ErrorState message="Briefing unavailable right now." onRetry={() => br.mutate()} />}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.alerts}`} delay={0.06}>
          <Head title="Live alerts" href="/intelligence" cta="Intelligence" />
          {al.isLoading && !al.data ? <SkeletonRows rows={3} /> : al.error && !al.data ? <ErrorState onRetry={() => al.mutate()} /> :
            alerts.length === 0 ? <EmptyState title="No alerts right now" message="Breakout and opportunity signals will appear here." /> : (
            <div className={styles.list}>
              {shown.map((a, i) => (
                <motion.div key={`${a.type}-${a.title}-${i}`} className={styles.alertRow} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
                  <span className={`${styles.dot} ${a.type === 'breakout' ? styles.dotAccent : ''}`} />
                  <div className={styles.info} style={{ padding: 0 }}>
                    <span className="t-body" style={{ fontWeight: 600 }}>{a.title}</span>
                    <span className="t-footnote text-secondary">{a.message}</span>
                  </div>
                  <span className="t-footnote text-tertiary" style={{ flexShrink: 0, paddingTop: 3 }}>{ALERT_LABEL[a.type]}</span>
                </motion.div>
              ))}
              {alerts.length > 4 && <button className="btn" style={{ alignSelf: 'flex-start', color: 'var(--accent)', background: 'none', padding: '10px 0 0' }} onClick={() => setAllAlerts(v => !v)}>{allAlerts ? 'Show less' : `Show all ${alerts.length}`}</button>}
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.trending}`} delay={0.08}>
          <Head title={`Top ${label} acts`} href="/intelligence" />
          {loading ? <SkeletonRows rows={5} /> : (s?.trending_entities.length ?? 0) === 0 ? <EmptyState title="No scored acts yet" message="Scores appear once metrics are collected." /> : (
            <div className={styles.list}>
              {s!.trending_entities.slice(0, 6).map((e, i) => (
                <motion.div key={`${e.id}-${i}`} className={styles.row} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 + i * 0.03 }}>
                  <div className={styles.avatar}>{e.name.charAt(0).toUpperCase()}</div>
                  <div className={styles.info}>
                    <span className={`t-body ${styles.ellip}`} style={{ fontWeight: 500 }}>{e.name}</span>
                    <span className={`t-footnote text-secondary ${styles.ellip}`}>{e.category ?? e.type}</span>
                  </div>
                  <span className={`num-rounded ${styles.val}`}>{e.composite_score}</span>
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.cities}`} delay={0.1}>
          <Head title="City heat" href="/markets" cta="Markets" />
          {loading ? <SkeletonRows rows={6} /> : (s?.city_heat.length ?? 0) === 0 ? <EmptyState title="No city data" /> : (
            <div className={styles.list}>
              {s!.city_heat.map((c, i) => {
                const v = c.music_score ?? 0;
                return (
                  <div key={c.city} className={styles.cityRow}>
                    <div className={styles.cityTop}>
                      <span className="t-body" style={{ fontWeight: 500 }}>{c.city} <span className="t-footnote text-tertiary" style={{ marginLeft: 4 }}>{c.active_on_district ? 'Live' : `Tier ${c.tier}`}</span></span>
                      <span className={`num-rounded ${styles.val}`} style={{ fontSize: '.9375rem' }}>{c.music_score ?? '—'}</span>
                    </div>
                    <div className={styles.bar}><motion.div className={styles.fill} initial={{ width: 0 }} animate={{ width: `${Math.min(100, v)}%` }} transition={{ duration: 0.8, delay: 0.15 + i * 0.05, ease: [0.22, 1, 0.36, 1] }} /></div>
                  </div>
                );
              })}
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.cats}`} delay={0.12}>
          <Head title="Acts by category" />
          {loading ? <Skeleton height={240} radius={14} /> : cats.length === 0 ? <EmptyState title="No category data" /> : (
            <div style={{ flex: 1, minHeight: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={cats} layout="vertical" margin={{ top: 0, right: 28, left: 0, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="category" width={92} tick={{ fontSize: 12, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={TIP} cursor={{ fill: 'var(--fill-quaternary)' }} />
                  <Bar dataKey="count" name="Acts" radius={6} barSize={14} label={{ position: 'right', fontSize: 12, fill: 'var(--text-secondary)' }}>
                    {cats.map((c, i) => <Cell key={c.category} fill={i === 0 ? 'var(--accent)' : 'var(--text-tertiary)'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.events}`} delay={0.14}>
          <Head title="Upcoming events" href="/events" cta="Monitor" />
          {loading ? <SkeletonRows rows={4} /> : (s?.upcoming_events.length ?? 0) === 0 ? <EmptyState title="No events synced yet" message="Events from ticketing platforms show up here." /> : (
            <div className={styles.list}>
              {s!.upcoming_events.slice(0, 5).map((e, i) => (
                <div key={`${e.id}-${i}`} className={styles.row}>
                  <div className={styles.date}>
                    <div className="t-caption text-tertiary" style={{ fontWeight: 600 }}>{dateIN(e.event_date, { month: 'short' })}</div>
                    <div className="num-rounded" style={{ fontSize: '1.2rem', fontWeight: 700 }}>{dateIN(e.event_date, { day: 'numeric' })}</div>
                  </div>
                  <div className={styles.info}>
                    <span className={`t-body ${styles.ellip}`} style={{ fontWeight: 500 }}>{e.name}</span>
                    <span className={`t-footnote text-secondary ${styles.ellip}`}>{[e.venue, e.city].filter(Boolean).join(' · ') || '—'}</span>
                  </div>
                  {e.min_price != null && <span className="t-footnote text-secondary num-rounded" style={{ flexShrink: 0 }}>{inrCompact(e.min_price)}</span>}
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      {s && <p className={`t-caption text-tertiary ${styles.foot}`}>Refreshed {timeAgo(s.generated_at)} · updates every 90s</p>}
    </Page>
  );
}
