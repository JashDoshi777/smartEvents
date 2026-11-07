'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChevronDown, ExternalLink, MapPin, Newspaper, Rocket, Target, TrendingUp } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented, ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { compact, dateIN, num } from '@/lib/format';
import {
  CompetitorGapItem, CompetitorPlatform, getCompetitorFeed, getCompetitorGapList,
  getCompetitorIntelligence, getMarketCities,
} from '@/lib/api';
import styles from './page.module.css';

const PLAT_COLOR: Record<string, string> = {
  district: 'var(--accent)', bookmyshow: 'var(--text-secondary)', insider: 'var(--text-tertiary)', ticketmaster_india: 'var(--text-disabled)',
};
const PLAT_LABEL: Record<string, string> = {
  district: 'District', bookmyshow: 'BookMyShow', insider: 'Insider (Paytm)', ticketmaster_india: 'Ticketmaster India',
};
const PLAT_ORDER = ['district', 'bookmyshow', 'insider', 'ticketmaster_india'];

function feedColor(p: string) {
  const k = p.toLowerCase();
  if (k.includes('district')) return PLAT_COLOR.district;
  if (k.includes('bookmyshow')) return PLAT_COLOR.bookmyshow;
  if (k.includes('insider')) return PLAT_COLOR.insider;
  return PLAT_COLOR.ticketmaster_india;
}
const prioBadge = (p: string) => (p === 'HIGH' ? 'badge-blue' : 'badge-neutral');
const scoreTone = (_s: number) => 'var(--accent)';

function PlatformCard({ id, p, city, index, maxMentions }: { id: string; p: CompetitorPlatform; city: string; index: number; maxMentions: number }) {
  const events = p.live_events_count ?? p.estimated_events;
  return (
    <motion.div
      className={`glass-card ${styles.plat} ${id === 'district' ? styles.platHero : id === 'ticketmaster_india' ? styles.platWide : ''}`}
      initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      data-testid={`platform-${id}`}
    >
      <div className={styles.platHead}>
        <span className={styles.platDot} style={{ background: PLAT_COLOR[id] ?? 'var(--neutral)' }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <p className="t-headline">{PLAT_LABEL[id] ?? p.name}</p>
          <p className="t-caption text-tertiary">{p.parent} · est. {p.founded}</p>
        </div>
        <span className={`badge badge-neutral`}>{p.active_in_city ? 'Active' : 'Not active'}</span>
      </div>
      <div>
        <div className={styles.stat}>
          <span className="t-footnote text-secondary">News mentions (7d)</span>
          <span className={`${styles.big} ${id === 'district' ? styles.bigHero : ''}`}>{num(p.news_mentions_7d)}</span>
        </div>
        <div className={styles.meter} style={{ marginTop: 8 }}>
          <motion.div className={styles.meterFill} style={{ background: PLAT_COLOR[id] }} initial={{ width: 0 }}
            animate={{ width: `${maxMentions > 0 ? Math.max(4, (p.news_mentions_7d / maxMentions) * 100) : 0}%` }} transition={{ duration: .6, ease: [0.22, 1, 0.36, 1] }} />
        </div>
      </div>
      <div className={styles.stat}>
        <span className="t-footnote text-secondary">{id === 'ticketmaster_india' ? 'Live events listed' : id === 'district' ? 'District events' : 'Event count'}</span>
        <span className={events != null ? styles.big2 : 't-callout text-tertiary'}>{events != null ? num(events) : 'Not measured'}</span>
      </div>
      <p className="t-footnote text-secondary">{p.market_position.replace(/\s*\(.*\)$/, '')}</p>
      <div className={styles.chips}>{p.strengths.map(s => <span key={s} className={styles.tag}>{s}</span>)}</div>
      {id === 'district' ? (
        <div style={{ marginTop: 'auto' }}><p className="t-caption text-tertiary" style={{ marginBottom: 8 }}>Live markets</p><div className={styles.chips}>{p.markets.map(m => <span key={m} className={styles.tag}>{m}</span>)}</div></div>
      ) : <p className="t-caption text-tertiary" style={{ marginTop: 'auto' }}>Coverage: {p.markets.length > 4 ? `${p.markets.slice(0, 4).join(', ')} +${p.markets.length - 4}` : p.markets.join(', ')}</p>}
    </motion.div>
  );
}

function GapRow({ g, i }: { g: CompetitorGapItem; i: number }) {
  return (
    <motion.div className={styles.gapRow} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}>
      <div className={styles.gapTop}>
        <div style={{ minWidth: 0 }}>
          <p className="t-callout" style={{ fontWeight: 650 }}>{g.city}</p>
          <p className="t-caption text-tertiary">{g.state ?? '—'} · Tier {g.tier} · {compact(g.population)} people</p>
        </div>
        <span className={`badge ${prioBadge(g.priority)}`}>{g.priority.charAt(0) + g.priority.slice(1).toLowerCase()} priority</span>
      </div>
      <div className={styles.gapScore}>
        <div className={styles.meter} style={{ flex: 1 }}>
          <motion.div className={styles.meterFill} style={{ background: scoreTone(g.avg_event_market_score) }} initial={{ width: 0 }} animate={{ width: `${g.avg_event_market_score}%` }} transition={{ duration: .6 }} />
        </div>
        <span className="t-callout tnum" style={{ fontWeight: 700, color: scoreTone(g.avg_event_market_score) }}>{g.avg_event_market_score}</span>
      </div>
      <div className={styles.chips}>
        <span className="badge badge-neutral">BookMyShow {g.competitor_presence.bookmyshow.toLowerCase()}</span>
        <span className="badge badge-neutral">Insider {g.competitor_presence.insider.toLowerCase()}</span>
      </div>
    </motion.div>
  );
}

export default function CompetitorsPage() {
  const [city, setCity] = useState('Mumbai');
  const [prio, setPrio] = useState<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'>('ALL');
  const [feedPlat, setFeedPlat] = useState('all');

  const { data: citiesData } = useSWR('market-cities', getMarketCities);
  const intel = useSWR(['comp-intel', city], () => getCompetitorIntelligence(city));
  const gaps = useSWR('comp-gaps', getCompetitorGapList);
  const feed = useSWR('comp-feed', () => getCompetitorFeed(30));

  const cityNames = (citiesData?.cities ?? []).map(c => c.name);
  const options = cityNames.length ? cityNames : [city];

  const platforms = useMemo(() => {
    const p = intel.data?.platforms;
    if (!p || typeof p !== 'object') return [];
    const keys = Object.keys(p);
    const rank = (k: string) => { const i = PLAT_ORDER.indexOf(k); return i < 0 ? 99 : i; };
    keys.sort((a, b) => rank(a) - rank(b));
    return keys.map(k => ({ id: k, p: p[k] }));
  }, [intel.data]);
  const chart = platforms.map(({ id, p }) => ({ id, name: PLAT_LABEL[id] ?? p.name, mentions: p.news_mentions_7d ?? 0 }));
  const maxMentions = Math.max(0, ...chart.map(c => c.mentions));

  const gapList = (gaps.data?.gaps ?? []).filter(g => prio === 'ALL' || g.priority === prio);
  const articles = feed.data?.articles ?? [];
  const feedPlatforms = Array.from(new Set(articles.map(a => a.platform)));
  const shownArticles = articles.filter(a => feedPlat === 'all' || a.platform === feedPlat);
  const opp = intel.data?.district_opportunity;

  return (
    <Page title="Competitors" subtitle="District vs BookMyShow, Insider and Ticketmaster India">
      <div className={styles.cityBar}>
        <div className={styles.cityPick}>
          <MapPin size={16} color="var(--text-secondary)" />
          <span className="t-headline">Market</span>
          <div className={styles.selectWrap}>
            <select className={`input ${styles.select}`} aria-label="City" value={city} onChange={e => setCity(e.target.value)}>
              {options.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <ChevronDown size={14} className={styles.selectIcon} />
          </div>
        </div>
      </div>

      {opp && (
        <motion.div className={styles.oppo} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className={styles.oppoIcon}>{opp.recommendation === 'EXPAND' ? <Rocket size={20} color="var(--saffron)" /> : <TrendingUp size={20} color="var(--text-secondary)" />}</div>
          <div>
            <p className="t-headline">{opp.recommendation === 'EXPAND' ? `Expansion opportunity in ${city}` : `Grow District in ${city}`}</p>
            <p className="t-footnote text-secondary">Tier {opp.city_tier} market · District is {opp.district_active ? 'already live here' : 'not yet live here'}</p>
          </div>
        </motion.div>
      )}

      {intel.error && !intel.data ? (
        <GlassCard><ErrorState message="Couldn’t load platform comparison for this city." onRetry={() => intel.mutate()} /></GlassCard>
      ) : !intel.data ? (
        <div className={styles.platGrid}>{[0, 1, 2, 3].map(i => <div key={i} className={`glass-card ${styles.plat}`}><Skeleton width="60%" height={18} /><Skeleton height={8} /><Skeleton width="80%" /><Skeleton width="70%" height={40} /></div>)}</div>
      ) : platforms.length === 0 ? (
        <GlassCard><EmptyState title="No platform data" message="No competitor platforms are tracked for this city yet." /></GlassCard>
      ) : (
        <>
          <div className={styles.platGrid}>{platforms.map(({ id, p }, i) => <PlatformCard key={id} id={id} p={p} city={city} index={i} maxMentions={maxMentions} />)}</div>
          <GlassCard className={styles.card}>
            <div className={styles.cardHead}>
              <div className={styles.cardTitle}><Newspaper size={16} color="var(--text-secondary)" /><h2 className="t-headline">Press attention in {city}</h2></div>
              <span className="t-caption text-tertiary">News mentions, last 7 days</span>
            </div>
            {maxMentions === 0 ? (
              <p className="t-callout text-secondary">No platform was mentioned in news for {city} in the last 7 days.</p>
            ) : <div className={styles.chartBox}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="var(--divider)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: 'var(--fill-quaternary)' }} contentStyle={{ background: 'var(--glass-fill-strong)', border: '1px solid var(--glass-border)', borderRadius: 12, fontSize: 12, backdropFilter: 'blur(20px)' }} formatter={(v: unknown) => [String(v), 'Mentions']} />
                  <Bar dataKey="mentions" radius={[8, 8, 3, 3]} maxBarSize={56}>{chart.map(c => <Cell key={c.id} fill={PLAT_COLOR[c.id] ?? 'var(--neutral)'} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>}
            {intel.data.note && <p className={styles.note}>{intel.data.note}</p>}
          </GlassCard>
        </>
      )}

      <div className={styles.cols}>
        <GlassCard className={styles.card}>
          <div className={styles.cardHead}>
            <div className={styles.cardTitle}><Target size={16} color="var(--text-secondary)" /><h2 className="t-headline">Market gaps by city</h2>
              {gaps.data && <span className="badge badge-neutral">{gaps.data.high_priority} high priority</span>}</div>
            <Segmented value={prio} onChange={setPrio} ariaLabel="Priority" options={[{ value: 'ALL', label: 'All' }, { value: 'HIGH', label: 'High' }, { value: 'MEDIUM', label: 'Med' }, { value: 'LOW', label: 'Low' }]} />
          </div>
          {gaps.error && !gaps.data ? <ErrorState onRetry={() => gaps.mutate()} />
            : !gaps.data ? <SkeletonRows rows={4} />
            : gapList.length === 0 ? <EmptyState title="No gaps" message={prio === 'ALL' ? 'District is live in every tracked city.' : 'No cities at this priority.'} />
            : <div className={styles.gapList}>{gapList.map((g, i) => <GapRow key={g.city} g={g} i={i} />)}</div>}
          {gaps.data?.insight && <p className={styles.note}>{gaps.data.insight}</p>}
        </GlassCard>

        <GlassCard className={styles.card}>
          <div className={styles.cardHead}>
            <div className={styles.cardTitle}><Newspaper size={16} color="var(--text-secondary)" /><h2 className="t-headline">Activity feed</h2></div>
            <span className="t-caption text-tertiary">Live from news sources</span>
          </div>
          {feedPlatforms.length > 1 && <ChipRow value={feedPlat} onChange={setFeedPlat} options={[{ value: 'all', label: 'All' }, ...feedPlatforms.map(p => ({ value: p, label: p }))]} />}
          {feed.error && !feed.data ? <ErrorState onRetry={() => feed.mutate()} />
            : !feed.data ? <SkeletonRows rows={5} />
            : shownArticles.length === 0 ? <EmptyState icon={<Newspaper size={34} strokeWidth={1.4} />} title="No recent coverage" message="No competitor news was found right now." />
            : <div className={styles.feed}>{shownArticles.map((a, i) => {
              const inner = (
                <>
                  <span className={styles.platDot} style={{ background: 'var(--text-disabled)', marginTop: 7 }} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <p className={`t-callout ${styles.feedTitle}`}>{a.title ?? 'Untitled article'}</p>
                    <div className={styles.feedMeta}>
                      <span className="badge badge-neutral">{a.platform}</span>
                      {a.source && <span className="t-caption text-tertiary">{a.source}</span>}
                      {a.published_at && <span className="t-caption text-tertiary">{dateIN(a.published_at)}</span>}
                    </div>
                  </div>
                  {a.url && <ExternalLink size={14} color="var(--text-tertiary)" style={{ marginTop: 4, flexShrink: 0 }} />}
                </>
              );
              return a.url
                ? <a key={`${a.url}-${i}`} className={styles.feedRow} href={a.url} target="_blank" rel="noopener noreferrer">{inner}</a>
                : <div key={`${i}-${a.title}`} className={styles.feedRow}>{inner}</div>;
            })}</div>}
        </GlassCard>
      </div>
    </Page>
  );
}
