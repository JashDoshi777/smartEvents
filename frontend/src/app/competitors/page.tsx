'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { ChevronDown, ExternalLink, Newspaper } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented, ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { compact, dateIN, num } from '@/lib/format';
import { CompetitorGapItem, CompetitorPlatform, getCompetitorCoverage, getCompetitorFeed, getCompetitorGapList, getCompetitorIntelligence, getMarketCities } from '@/lib/api';
import styles from './page.module.css';

const PLAT_LABEL: Record<string, string> = { district: 'District', bookmyshow: 'BookMyShow', insider: 'Insider (Paytm)', ticketmaster_india: 'Ticketmaster India' };
const PLAT_ORDER = ['district', 'bookmyshow', 'insider', 'ticketmaster_india'];

function PlatformRow({ id, p, i, max, newsOk }: { id: string; p: CompetitorPlatform; i: number; max: number; newsOk: boolean }) {
  const events = p.live_events_count ?? p.estimated_events;
  return (
    <motion.div className={styles.plat} data-testid={`platform-${id}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ type: 'spring', stiffness: 300, damping: 30, delay: i * 0.05 }}>
      <div className={`${styles.cell} ${styles.platFirst}`}>
        <p className={styles.platName}>{id === 'district' && <i className={`${styles.dot} ${styles.dotBlue}`} />}{PLAT_LABEL[id] ?? p.name}</p>
        <p className={styles.sub}>{p.parent} · est. {p.founded} · {p.active_in_city ? 'Active in this city' : 'Not active here'}</p>
        <p className={styles.sub}>{p.strengths.slice(0, 2).join(' · ')}</p>
      </div>
      <div className={`${styles.cell} ${styles.platFirst}`}>
        <p className={styles.sub} style={{ marginBottom: 2 }}>{p.market_position.replace(/\s*\(.*\)$/, '')}</p>
        <p className={styles.sub}>{p.markets.length > 3 ? `${p.markets.slice(0, 3).join(', ')} +${p.markets.length - 3}` : p.markets.join(', ')}</p>
      </div>
      <div className={styles.cell}>
        <p className={`${styles.sub} ${styles.mLabel}`}>News mentions, 7 days</p>
        <p className={`${styles.num} ${id === 'district' ? styles.numMe : ''}`} data-testid={`news-${id}`}>{newsOk ? num(p.news_mentions_7d) : '—'}</p>
        <div className={styles.meter}><motion.div className={styles.meterFill} initial={{ width: 0 }} animate={{ width: `${newsOk && max > 0 ? Math.max(3, (p.news_mentions_7d / max) * 100) : 0}%` }} transition={{ type: 'spring', stiffness: 80, damping: 18 }} /></div>
      </div>
      <div className={styles.cell}>
        <p className={`${styles.sub} ${styles.mLabel}`}>Events listed</p>
        <p className={styles.num} style={{ fontSize: events != null ? undefined : '.9375rem', fontWeight: events != null ? 700 : 400, color: events != null ? undefined : 'var(--text-tertiary)' }}>{events != null ? num(events) : 'Not measured'}</p>
      </div>
    </motion.div>
  );
}

function Coverage({ onPick, current }: { onPick: (c: string) => void; current: string }) {
  const { data, error, mutate } = useSWR('comp-coverage', getCompetitorCoverage);
  const [all, setAll] = useState(false);
  const cities = data?.cities ?? [];
  const shown = all ? cities : cities.slice(0, 12);
  const live = cities.filter(c => c.district_active).length;
  return (
    <GlassCard className={styles.card}>
      <div className={styles.cardHead}><h2 className={styles.headline}>Market strength by city</h2><span className={styles.sub}>{data ? `${live} of ${cities.length} cities live on District` : ' '}</span></div>
      {error && !data ? <ErrorState message="Couldn’t load city coverage." onRetry={() => mutate()} />
        : !data ? <SkeletonRows rows={5} />
        : cities.length === 0 ? <EmptyState title="No cities" message="No tracked cities yet." />
        : <>
          <div role="list" aria-label="Market score ranking" data-testid="coverage">
            {shown.map((c, i) => (
              <button key={c.city} type="button" role="listitem" className={styles.covRow} aria-current={c.city === current} onClick={() => onPick(c.city)} data-testid={`cov-${c.city}`}>
                <span className={styles.covName}>{c.city}</span>
                <span className={styles.covTrack}><motion.span className={styles.covFill} style={{ opacity: c.district_active ? .9 : .32 }} initial={{ width: 0 }} animate={{ width: `${Math.min(100, c.market_score ?? 0)}%` }} transition={{ type: 'spring', stiffness: 80, damping: 18, delay: Math.min(i, 12) * .02 }} /></span>
                <span className={`${styles.num} ${styles.covNum}`}>{c.market_score ?? '—'}</span>
                <span className={styles.covRivals}>{[c.bookmyshow && 'BMS', c.insider && 'Insider', c.ticketmaster_india && 'TM'].filter(Boolean).join(' · ') || 'No rivals'}</span>
              </button>
            ))}
          </div>
          {cities.length > 12 && <button type="button" className="btn btn-tinted btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setAll(a => !a)}>{all ? 'Show top 12' : `Show all ${cities.length}`}</button>}
          <p className={styles.sub}>Bright bars are cities where District is live, dim bars are expansion targets. Rival presence is from configured market coverage, not measured inventory.</p>
        </>}
    </GlassCard>
  );
}

function GapRow({ g, i }: { g: CompetitorGapItem; i: number }) {
  const rivals = [g.competitor_presence.bookmyshow === 'Active' && 'BookMyShow', g.competitor_presence.insider === 'Active' && 'Insider'].filter(Boolean).join(' and ');
  return (
    <motion.div className={styles.gapRow} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}>
      <div className={styles.gapMain}>
        <p className={styles.gapTitle}>{g.city}{g.priority === 'HIGH' && <i className={styles.dot} title="High priority" />}</p>
        <p className={styles.sub}>{g.state ?? '—'} · {g.tier ? `Tier ${g.tier}` : 'Unclassified'} · {compact(g.population)} people</p>
        <p className={styles.sub}>{rivals ? `${rivals} active` : 'No rival presence'} · {g.priority.charAt(0) + g.priority.slice(1).toLowerCase()} priority</p>
      </div>
      <div className={styles.gapScore}><p className={styles.num}>{g.avg_event_market_score || '—'}</p><p className={styles.sub}>market score</p></div>
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

  const options = (citiesData?.cities ?? []).map(c => c.name);
  const platforms = useMemo(() => {
    const p = intel.data?.platforms;
    if (!p || typeof p !== 'object') return [];
    const rank = (k: string) => { const i = PLAT_ORDER.indexOf(k); return i < 0 ? 99 : i; };
    return Object.keys(p).sort((a, b) => rank(a) - rank(b)).map(k => ({ id: k, p: p[k] }));
  }, [intel.data]);
  const max = Math.max(0, ...platforms.map(x => x.p.news_mentions_7d ?? 0));

  const gapList = (gaps.data?.gaps ?? []).filter(g => prio === 'ALL' || g.priority === prio);
  const articles = feed.data?.articles ?? [];
  const feedPlatforms = Array.from(new Set(articles.map(a => a.platform)));
  const shown = articles.filter(a => feedPlat === 'all' || a.platform === feedPlat);
  const opp = intel.data?.district_opportunity;

  return (
    <Page title="Competitors" subtitle="District vs BookMyShow, Insider and Ticketmaster India">
      <div className={styles.top}>
        <div className={styles.selectWrap}>
          <select className={`input ${styles.select}`} aria-label="City" value={city} onChange={e => setCity(e.target.value)}>
            {(options.length ? options : [city]).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <ChevronDown size={14} strokeWidth={1.75} className={styles.selectIcon} />
        </div>
        {opp && <p className={styles.body}>{opp.recommendation === 'EXPAND' && <i className={styles.dot} style={{ marginRight: 8 }} />}
          <b style={{ fontWeight: 600 }}>{opp.recommendation === 'EXPAND' ? `Expansion opportunity in ${city}` : `District is growing in ${city}`}</b>
          <span className="text-secondary"> · {typeof opp.city_tier === 'number' ? `Tier ${opp.city_tier}` : 'Tier unknown'}</span></p>}
      </div>

      <GlassCard className={styles.card}>
        <div className={styles.cardHead}><h2 className={styles.headline}>Platform comparison</h2><span className={styles.sub}>{city}</span></div>
        {intel.error && !intel.data ? <ErrorState message="Couldn’t load the platform comparison." onRetry={() => intel.mutate()} />
          : !intel.data ? <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>{[0, 1, 2, 3].map(i => <Skeleton key={i} height={52} radius={12} />)}</div>
          : platforms.length === 0 ? <EmptyState title="No platform data" message="No competitor platforms are tracked for this city yet." />
          : <div className={styles.table}>
            <div className={`${styles.plat} ${styles.platHead}`}><span>Platform</span><span>Position and coverage</span><span>News mentions, 7 days</span><span>Events listed</span></div>
            {platforms.map(({ id, p }, i) => <PlatformRow key={id} id={id} p={p} i={i} max={max} newsOk={intel.data?.news_available !== false} />)}
          </div>}
        {intel.data?.news_available === false && <p className={styles.sub} role="status" style={{ marginTop: 10 }} data-testid="news-unavailable">News mention counts are unavailable right now because the news source is rate-limited. They show as a dash instead of zero.</p>}
        {intel.data?.note && <p className={styles.sub} style={{ marginTop: 10 }}>{intel.data.note}</p>}
      </GlassCard>

      <Coverage current={city} onPick={setCity} />

      <div className={styles.cols}>
        <GlassCard className={styles.card}>
          <div className={styles.cardHead}><h2 className={styles.headline}>Market gaps</h2>
            <Segmented value={prio} onChange={setPrio} ariaLabel="Priority" options={[{ value: 'ALL', label: 'All' }, { value: 'HIGH', label: 'High' }, { value: 'MEDIUM', label: 'Med' }, { value: 'LOW', label: 'Low' }]} /></div>
          {gaps.error && !gaps.data ? <ErrorState onRetry={() => gaps.mutate()} />
            : !gaps.data ? <SkeletonRows rows={4} />
            : gapList.length === 0 ? <EmptyState title="No gaps" message={prio === 'ALL' ? 'District is live in every tracked city.' : 'No cities at this priority.'} />
            : <div className={styles.list}>{gapList.map((g, i) => <GapRow key={g.city} g={g} i={i} />)}</div>}
          {gaps.data?.insight && <p className={styles.sub} style={{ marginTop: 8 }}>{gaps.data.insight}</p>}
        </GlassCard>

        <GlassCard className={styles.card}>
          <div className={styles.cardHead}><h2 className={styles.headline}>Activity feed</h2><span className={styles.sub}>Live from news sources</span></div>
          {feedPlatforms.length > 1 && <ChipRow value={feedPlat} onChange={setFeedPlat} options={[{ value: 'all', label: 'All' }, ...feedPlatforms.map(p => ({ value: p, label: p }))]} />}
          {feed.error && !feed.data ? <ErrorState onRetry={() => feed.mutate()} />
            : !feed.data ? <SkeletonRows rows={5} />
            : shown.length === 0 ? <EmptyState icon={<Newspaper size={34} strokeWidth={1.5} />} title={feed.data.news_available === false ? 'News is unavailable' : 'No recent coverage'} message={feed.data.news_available === false ? 'The news source is rate-limited right now. Try again in a few minutes.' : 'No competitor news was found right now.'} />
            : <div className={styles.list}>{shown.map((a, i) => {
              const inner = (<>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <p className={styles.feedTitle}>{a.title ?? 'Untitled article'}</p>
                  <p className={styles.sub}>{[a.platform, a.source, a.published_at && dateIN(a.published_at)].filter(Boolean).join(' · ')}</p>
                </div>
                {a.url && <ExternalLink size={15} strokeWidth={1.75} color="var(--text-tertiary)" style={{ marginTop: 3, flexShrink: 0 }} />}
              </>);
              return a.url ? <a key={`${a.url}-${i}`} className={styles.feedRow} href={a.url} target="_blank" rel="noopener noreferrer">{inner}</a>
                : <div key={`${i}-${a.title}`} className={styles.feedRow}>{inner}</div>;
            })}</div>}
        </GlassCard>
      </div>
    </Page>
  );
}
