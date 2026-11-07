'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChevronRight, Globe2 } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Ring, StackBar } from '@/components/dashboard/Ring';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { getDashboardSummaryScoped, getDashboardAlerts, getBriefing, DashboardAlert } from '@/lib/api';
import { inrCompact, num, greeting, dateIN, timeAgo } from '@/lib/format';
import styles from './page.module.css';

const CHART_COLORS = ['var(--accent)', 'var(--text-secondary)', 'var(--text-tertiary)', 'var(--fill-tertiary)'];
const TIP = { background: 'var(--glass-fill-strong)', border: '1px solid var(--glass-border)', borderRadius: 12, fontSize: 12, backdropFilter: 'blur(20px)', color: 'var(--text-primary)' };

const scoreColor = (_s?: number | null) => 'var(--accent)';
const alertMeta = (t: DashboardAlert['type']) => ({ c: t === 'breakout' ? 'var(--accent)' : 'var(--text-tertiary)', bg: 'var(--fill-tertiary)' });

function CardHead({ title, eyebrow, href, cta }: { title: string; eyebrow?: string; href?: string; cta?: string }) {
  return (
    <div className={styles.head}>
      <div>{eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}<h2 className="t-title3" style={{ fontWeight: 700 }}>{title}</h2></div>
      {href && <Link href={href} className={styles.link}>{cta ?? 'See all'}<ChevronRight size={14} /></Link>}
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
  const maxScore = Math.max(1, ...(s?.trending_entities ?? []).map(e => e.composite_score));

  return (
    <Page title="Dashboard" subtitle={`${greeting()} — ${isIndia ? 'India market snapshot' : 'Global market snapshot'}`}>
      {sum.error && !s && <GlassCard><ErrorState message="Couldn’t reach the LiveIQ backend." onRetry={() => sum.mutate()} /></GlassCard>}

      <div className={styles.bento}>
        <GlassCard className={`${styles.tile} ${styles.hero}`}>
          <div className={styles.eyebrow}>{isIndia ? 'India' : 'Global'} portfolio</div>
          {loading ? <Skeleton height={150} radius={22} /> : (<>
            <div className={styles.heroRow}>
              <div>
                <div className={`${styles.rounded} ${styles.big}`}>{num(hero?.total_entities)}</div>
                <div className="t-callout text-secondary" style={{ marginTop: 8 }}>{label} acts tracked · {num(hero?.entities_with_metrics)} scored</div>
              </div>
              <Ring value={hero?.avg_composite_score} size={116} stroke={13} color="var(--accent)">
                <div><div className={`${styles.rounded}`} style={{ fontSize: '1.7rem', fontWeight: 700 }}>{hero?.avg_composite_score ?? '—'}</div><div className="t-caption text-tertiary">avg score</div></div>
              </Ring>
            </div>
            {types.length > 0 && <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <StackBar parts={types.map((t, i) => ({ label: t.type, value: t.count, color: CHART_COLORS[i % CHART_COLORS.length] }))} />
              <div className={styles.legend}>{types.map((t, i) => (
                <span key={t.type} className={styles.legendItem}><span className={styles.dot} style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} /><span className="t-caption text-secondary" style={{ textTransform: 'capitalize' }}>{t.type.replace('_', ' ')} {num(t.count)}</span></span>
              ))}</div>
            </div>}
            <div className={styles.miniStats}>
              <div className={styles.mini}><span className={`${styles.rounded} ${styles.miniVal}`}>{num(hero?.active_cities)}</span><span className="t-caption text-tertiary">Cities live on District · {num(hero?.expansion_targets)} to open</span></div>
              <div className={styles.mini}><span className={`${styles.rounded} ${styles.miniVal}`}>{num(hero?.total_events)}</span><span className="t-caption text-tertiary">Events synced from platforms</span></div>
            </div>
          </>)}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.alerts}`} delay={0.05}>
          <CardHead eyebrow="Signals" title="Live alerts" href="/intelligence" cta="Intelligence" />
          {al.isLoading && !al.data ? <SkeletonRows rows={3} /> : al.error && !al.data ? <ErrorState onRetry={() => al.mutate()} /> :
            alerts.length === 0 ? <EmptyState title="No alerts right now" message="Breakout and opportunity signals will appear here." /> : (
            <div className={styles.list}>
              {shown.map((a, i) => {
                const m = alertMeta(a.type);
                return (
                  <motion.div key={`${a.type}-${a.title}-${i}`} className={styles.alertRow} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
                    <span className={styles.dotSev} style={{ background: m.c }} />
                    <div className={styles.info}>
                      <span className="t-callout" style={{ fontWeight: 600 }}>{a.title}</span>
                      <span className="t-footnote text-secondary">{a.message}</span>
                    </div>
                    <span className={styles.tag} style={{ background: m.bg, color: 'var(--text-secondary)' }}>{a.type === 'opportunity' ? 'Gap' : a.type === 'breakout' ? 'Breakout' : a.type === 'buzz' ? 'Buzz' : 'Info'}</span>
                  </motion.div>
                );
              })}
              {alerts.length > 4 && <button className="btn btn-ghost btn-sm" style={{ alignSelf: 'center', marginTop: 8 }} onClick={() => setAllAlerts(v => !v)}>{allAlerts ? 'Show less' : `Show all ${alerts.length}`}</button>}
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.trending}`} delay={0.08}>
          <CardHead eyebrow="Demand" title={`Top ${label} acts`} href="/intelligence" />
          {loading ? <SkeletonRows rows={5} /> : (s?.trending_entities.length ?? 0) === 0 ? <EmptyState title="No scored acts yet" message="Scores appear once metrics are collected." /> : (
            <div className={styles.list}>
              {s!.trending_entities.slice(0, 7).map((e, i) => (
                <motion.div key={`${e.id}-${i}`} className={styles.row} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 + i * 0.03 }}>
                  <span className={styles.rank}>{i + 1}</span>
                  <div className={styles.info}>
                    <span className={`t-callout ${styles.ellip}`} style={{ fontWeight: 600 }}>{e.name}</span>
                    <span className={`t-caption text-tertiary ${styles.ellip}`}>{e.category ?? e.type}</span>
                    <div className={styles.bar} style={{ marginTop: 6 }}><motion.div className={styles.fill} style={{ background: scoreColor(e.composite_score) }} initial={{ width: 0 }} animate={{ width: `${(e.composite_score / maxScore) * 100}%` }} transition={{ duration: 0.8, delay: 0.1 + i * 0.04, ease: [0.22, 1, 0.36, 1] }} /></div>
                  </div>
                  <span className={styles.scoreVal}>{e.composite_score}</span>
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.cities}`} delay={0.11}>
          <CardHead eyebrow="Markets" title="City heat" href="/markets" cta="Markets" />
          {loading ? <SkeletonRows rows={6} /> : (s?.city_heat.length ?? 0) === 0 ? <EmptyState title="No city data" /> : (
            <div className={styles.list}>
              {s!.city_heat.map((c, i) => {
                const v = c.music_score ?? 0;
                return (
                  <div key={c.city} className={styles.cityRow}>
                    <div className={styles.cityTop}>
                      <span className="t-callout" style={{ fontWeight: 600 }}>{c.city} <span className="t-caption" style={{ color: 'var(--text-tertiary)', fontWeight: 500, marginLeft: 4 }}>{c.active_on_district ? 'Live' : `Tier ${c.tier}`}</span></span>
                      <span className={styles.scoreVal} style={{ fontSize: '.95rem' }}>{c.music_score ?? '—'}</span>
                    </div>
                    <div className={styles.bar}><motion.div className={styles.fill} initial={{ width: 0 }} animate={{ width: `${Math.min(100, v)}%` }} transition={{ duration: 0.8, delay: 0.15 + i * 0.05, ease: [0.22, 1, 0.36, 1] }} style={{ background: scoreColor(v) }} /></div>
                  </div>
                );
              })}
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.cats}`} delay={0.14}>
          <CardHead eyebrow="Mix" title="Acts by category" />
          {loading ? <Skeleton height={210} radius={14} /> : cats.length === 0 ? <EmptyState title="No category data" /> : (
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={cats} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="category" width={96} tick={{ fontSize: 12, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={TIP} cursor={{ fill: 'var(--fill-quaternary)' }} />
                  <Bar dataKey="count" name="Acts" radius={8} barSize={18} label={{ position: 'right', fontSize: 11, fill: 'var(--text-tertiary)' }}>
                    {cats.map((c, i) => <Cell key={c.category} fill={i === 0 ? 'var(--accent)' : 'var(--fill-tertiary)'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.events}`} delay={0.17}>
          <CardHead eyebrow="Calendar" title="Upcoming events" href="/events" cta="Monitor" />
          {loading ? <SkeletonRows rows={4} /> : (s?.upcoming_events.length ?? 0) === 0 ? <EmptyState title="No events synced yet" message="Events from ticketing platforms show up here." /> : (
            <div className={styles.list}>
              {s!.upcoming_events.map((e, i) => (
                <div key={`${e.id}-${i}`} className={styles.row}>
                  <div className={styles.date}>
                    <div style={{ fontSize: '.625rem', fontWeight: 700, color: 'var(--text-tertiary)', letterSpacing: '.06em' }}>{dateIN(e.event_date, { month: 'short' }).toUpperCase()}</div>
                    <div className={styles.rounded} style={{ fontSize: '1.45rem', fontWeight: 700 }}>{dateIN(e.event_date, { day: 'numeric' })}</div>
                  </div>
                  <div className={styles.info}>
                    <span className={`t-callout ${styles.ellip}`} style={{ fontWeight: 600 }}>{e.name}</span>
                    <span className={`t-footnote text-tertiary ${styles.ellip}`}>{[e.venue, e.city].filter(Boolean).join(' · ') || '—'}</span>
                  </div>
                  {e.min_price != null && <span className={`${styles.rounded} t-callout`} style={{ fontWeight: 600 }}>{inrCompact(e.min_price)}<span className="t-caption text-tertiary"> onwards</span></span>}
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard className={`${styles.tile} ${styles.brief}`} delay={0.2}>
          <CardHead eyebrow="Copilot" title="AI briefing" />
          {br.isLoading && !br.data ? <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>{[95, 85, 100, 70, 88, 60].map((w, i) => <Skeleton key={i} height={12} width={`${w}%`} />)}</div>
            : br.data ? (<>
              <p className={`t-callout text-secondary ${styles.briefing}`}>{br.data.briefing}</p>
              <p className="t-caption text-tertiary">Updated {timeAgo(br.data.generated_at)}</p>
            </>) : <ErrorState message="Briefing unavailable right now." onRetry={() => br.mutate()} />}
          <div className={styles.ctaRow}>
            <Link href="/executive" className="btn btn-tinted btn-sm">Executive suite <ChevronRight size={14} /></Link>
            <Link href="/copilot" className="btn btn-ghost btn-sm">Ask Copilot</Link>
          </div>
        </GlassCard>
      </div>

      {s && <p className={`t-caption text-tertiary ${styles.foot}`}><Globe2 size={11} style={{ verticalAlign: -1 }} /> Refreshed {timeAgo(s.generated_at)} · auto-updates every 90s</p>}
    </Page>
  );
}
