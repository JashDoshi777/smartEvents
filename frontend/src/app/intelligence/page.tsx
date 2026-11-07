'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Search, Brain, Star, Check, GitCompareArrows, Sparkles, Gauge, X } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented, ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton } from '@/components/ui/Skeleton';
import { Sheet } from '@/components/ui/Sheet';
import { useToast } from '@/components/ui/Toast';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { ScoreRing } from '@/components/intel/ScoreRing';
import { scoreColor, verdictFor, typeLabel, initials, useScopedPortfolio } from '@/components/intel/entity-utils';
import { getWatchlist, addToWatchlist, removeFromWatchlist, getEntityScore, getEntityCities, compareEntities, PortfolioEntity } from '@/lib/api';
import { compact, num, dateIN } from '@/lib/format';
import styles from './page.module.css';

const TYPE_OPTIONS = [
  { value: 'all', label: 'All' }, { value: 'artist', label: 'Artists' }, { value: 'comedian', label: 'Comedy' },
  { value: 'sports_team', label: 'Sports' }, { value: 'movie', label: 'Film' }, { value: 'theatre_group', label: 'Theatre' },
];

function useIsMobile() {
  const [m, setM] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)');
    const f = () => setM(mq.matches);
    f(); mq.addEventListener('change', f);
    return () => mq.removeEventListener('change', f);
  }, []);
  return m;
}

function VerdictBadge({ score }: { score: number | null }) {
  const v = verdictFor(score);
  const cls = v.tone === 'accent' ? 'badge-blue' : 'badge-neutral';
  return <span className={`badge ${cls}`}>{v.label}</span>;
}

// ── Detail panel ────────────────────────────────────────────────
function EntityDetail({ entity, watched, onToggleWatch, onCompare, onClose, inSheet }: {
  entity: PortfolioEntity; watched: boolean; onToggleWatch: () => void; onCompare: () => void; onClose: () => void; inSheet?: boolean;
}) {
  const score = useSWR(['entity-score', entity.id], () => getEntityScore(entity.id));
  const cities = useSWR(['entity-cities', entity.id], () => getEntityCities(entity.id));
  const s = score.data?.signals;
  const composite = score.data?.composite_score ?? entity.composite_score;
  const v = verdictFor(composite);
  const topCities = (cities.data?.cities ?? []).slice(0, 5);

  const bars: { label: string; value: number | null | undefined; text: string }[] = [
    { label: 'Composite score', value: composite, text: composite != null ? composite.toFixed(1) : '—' },
    { label: 'Google Trends', value: s?.google_trend_score ?? entity.google_trend_score, text: (s?.google_trend_score ?? entity.google_trend_score) != null ? String(s?.google_trend_score ?? entity.google_trend_score) : '—' },
    { label: 'Data completeness', value: s?.data_completeness != null ? s.data_completeness * (s.data_completeness <= 1 ? 100 : 1) : null,
      text: s?.data_completeness != null ? `${Math.round(s.data_completeness * (s.data_completeness <= 1 ? 100 : 1))}%` : '—' },
  ];

  return (
    <div className={styles.panel} style={inSheet ? { padding: 0, overflow: 'visible' } : undefined}>
      <div className={styles.pHead}>
        <div className={styles.pAvatar}>{initials(entity.name)}</div>
        <div className={styles.pTitle}>
          <h2 className="t-title3">{entity.name}</h2>
          <p className="t-footnote text-tertiary">{entity.category ?? typeLabel(entity.type)} · {typeLabel(entity.type)}{entity.country ? ` · ${entity.country}` : ''}</p>
        </div>
        <div className={styles.pBtns}>
          <button className="btn btn-icon" onClick={onToggleWatch} aria-pressed={watched} aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'} title={watched ? 'Remove from watchlist' : 'Add to watchlist'}>
            <Star size={18} fill={watched ? 'var(--warning)' : 'none'} color={watched ? 'var(--warning)' : 'currentColor'} />
          </button>
          {!inSheet && <button className="btn btn-icon" onClick={onClose} aria-label="Close details"><X size={18} /></button>}
        </div>
      </div>

      <div className={styles.verdictRow}>
        <ScoreRing score={composite} size={96} />
        <div className={styles.verdictBox} style={{ background: 'var(--fill-quaternary)' }}>
          <p style={{ fontWeight: 600, fontSize: '1rem' }}>{v.label}</p>
          <p className="t-footnote text-secondary" style={{ marginTop: 3 }}>{v.blurb}</p>
        </div>
      </div>

      <div className={styles.sect}>
        <p className={styles.sectTitle}>Signal breakdown</p>
        {score.isLoading && !score.data ? (
          <div style={{ display: 'grid', gap: 12 }}><Skeleton height={34} /><Skeleton height={34} /><Skeleton height={34} /></div>
        ) : score.error ? (
          <p className="t-footnote text-tertiary">Couldn’t load live signals for this entity.</p>
        ) : (
          bars.map((b, i) => (
            <div key={b.label} className={styles.sig}>
              <div className={styles.sigMeta}><span className="t-footnote text-secondary">{b.label}</span><span className="t-footnote tnum" style={{ fontWeight: 600 }}>{b.text}</span></div>
              <div className={styles.track}>
                <motion.div className={styles.fill} style={{ background: scoreColor(b.value) }} initial={{ width: 0 }}
                  animate={{ width: `${Math.max(0, Math.min(b.value ?? 0, 100))}%` }} transition={{ duration: 0.7, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }} />
              </div>
            </div>
          ))
        )}
        {s && (
          <div className={styles.kv}>
            {[
              ['Last.fm listeners', compact(s.lastfm_listeners)], ['YouTube subs', compact(s.youtube_subscribers)],
              ['YouTube views (30d)', compact(s.youtube_views_30d)], ['News mentions (7d)', s.news_mentions_7d != null ? num(s.news_mentions_7d) : '—'],
            ].map(([k, val]) => (
              <div key={k} className={styles.kvItem}><span className="t-caption text-tertiary">{k}</span><span className="tnum" style={{ fontWeight: 600 }}>{val}</span></div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.sect}>
        <p className={styles.sectTitle}>Where demand is strongest</p>
        {cities.isLoading && !cities.data ? <Skeleton height={80} /> : topCities.length === 0 ? (
          <p className="t-footnote text-tertiary">No city demand data for this category yet.</p>
        ) : topCities.map((c, i) => (
          <div key={c.city} className={styles.cityRow}>
            <span className={styles.cityName}>{c.city}{c.is_home_city ? ' ⌂' : ''}</span>
            <div className={styles.track} style={{ flex: 1 }}>
              <motion.div className={styles.fill} style={{ background: 'var(--accent)' }} initial={{ width: 0 }} animate={{ width: `${c.demand_score}%` }} transition={{ duration: 0.7, delay: 0.1 + i * 0.06, ease: [0.22, 1, 0.36, 1] }} />
            </div>
            <span className="t-footnote tnum" style={{ width: 28, textAlign: 'right', fontWeight: 600 }}>{Math.round(c.demand_score)}</span>
          </div>
        ))}
      </div>

      <p className="t-caption text-tertiary">Updated {dateIN(score.data?.last_updated ?? entity.last_updated)}{score.data?.data_sources?.length ? ` · ${score.data.data_sources.slice(0, 4).join(', ')}` : ''}</p>

      <div className={styles.actions}>
        <Link className="btn btn-primary" href={`/recommendations?entity=${entity.id}`}><Gauge size={15} /> Sign verdict</Link>
        <Link className="btn btn-tinted" href={`/psychology?entity=${entity.id}`}><Brain size={15} /> Psychology</Link>
        <button className="btn btn-tinted" onClick={onCompare}><GitCompareArrows size={15} /> Compare</button>
        <Link className="btn btn-tinted" href={`/listening?entity=${entity.id}`}><Sparkles size={15} /> Listening</Link>
      </div>
    </div>
  );
}

// ── Compare sheet ───────────────────────────────────────────────
function CompareSheet({ ids, onClose }: { ids: string[]; onClose: () => void }) {
  const { data, error, isLoading, mutate: retry } = useSWR(ids.length >= 2 ? ['compare', ...ids] : null, () => compareEntities(ids));
  const rows: [string, (p: NonNullable<typeof data>['entities'][number]) => string][] = [
    ['Score', p => (p.composite_score != null ? String(p.composite_score) : '—')],
    ['Trend', p => (p.trend_direction === 'pending' ? '—' : p.trend_direction)],
    ['Listeners', p => compact(p.listeners)],
    ['Category', p => p.category ?? '—'],
    ['Home city', p => p.home_city ?? '—'],
    ['Market', p => p.primary_market ?? (p.is_international ? 'Global' : 'India')],
    ['Venue size', p => (p.typical_venue_capacity_min != null ? `${num(p.typical_venue_capacity_min)}–${num(p.typical_venue_capacity_max)}` : '—')],
  ];
  return (
    <Sheet open onClose={onClose} title="Compare">
      {isLoading ? <div style={{ display: 'grid', gap: 10 }}><Skeleton height={36} /><Skeleton height={36} /><Skeleton height={36} /></div>
        : error ? <ErrorState message="Couldn’t compare these entities." onRetry={() => retry()} />
        : data && (
          <div className={styles.cmpGrid}>
            <table className={styles.cmpTable}>
              <thead><tr><th />{data.entities.map(p => <th key={p.id}>{p.name}</th>)}</tr></thead>
              <tbody>{rows.map(([k, f]) => <tr key={k}><th>{k}</th>{data.entities.map(p => <td key={p.id} className="tnum" style={{ textTransform: k === 'Trend' ? 'capitalize' : undefined }}>{f(p)}</td>)}</tr>)}</tbody>
            </table>
          </div>
        )}
    </Sheet>
  );
}

// ── Page ────────────────────────────────────────────────────────
function Hub() {
  const params = useSearchParams();
  const toast = useToast();
  const isMobile = useIsMobile();
  const { scope, isIndia } = useMarketScope();
  const { all, scoped, isLoading, error, mutate: reload } = useScopedPortfolio();

  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const [sort, setSort] = useState<'score' | 'name'>('score');
  const pending = useRef(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [cmp, setCmp] = useState<string[]>([]);
  const [cmpOpen, setCmpOpen] = useState(false);

  const { data: wl, mutate: mutateWl } = useSWR('watchlist', () => getWatchlist());
  const watched = useMemo(() => new Set((wl?.watchlist ?? []).map(w => w.id)), [wl]);

  const deepLink = params.get('entity');
  useEffect(() => { if (deepLink) setSelectedId(deepLink); }, [deepLink]);

  const selected = all.find(e => e.id === selectedId) ?? null;

  async function toggleWatch(e: PortfolioEntity) {
    if (pending.current) return;
    pending.current = true;
    const on = watched.has(e.id);
    const next = { watchlist: on ? (wl?.watchlist ?? []).filter(w => w.id !== e.id) : [...(wl?.watchlist ?? []), { id: e.id, name: e.name, category: e.category, is_international: e.is_international, watched_since: new Date().toISOString() }], total: 0 };
    try {
      await mutateWl(async () => { if (on) await removeFromWatchlist(e.id); else await addToWatchlist(e.id); return next; }, { optimisticData: next, revalidate: true, rollbackOnError: true });
      toast(on ? `Removed ${e.name} from watchlist` : `Added ${e.name} to watchlist`, 'success');
    } catch { toast('Couldn’t update watchlist', 'error'); } finally { pending.current = false; }
  }

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: scoped.length };
    scoped.forEach(e => { c[e.type] = (c[e.type] ?? 0) + 1; });
    return c;
  }, [scoped]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = scoped.filter(e => (type === 'all' || e.type === type) && (!q || e.name.toLowerCase().includes(q) || (e.category ?? '').toLowerCase().includes(q)));
    return sort === 'name' ? [...list].sort((a, b) => a.name.localeCompare(b.name)) : [...list].sort((a, b) => (b.composite_score ?? -1) - (a.composite_score ?? -1));
  }, [scoped, query, type, sort]);

  const scored = scoped.filter(e => e.composite_score != null);
  const avg = scored.length ? scored.reduce((a, e) => a + (e.composite_score ?? 0), 0) / scored.length : null;
  const stats = [
    { label: isIndia ? 'India tracked' : 'Global tracked', value: num(scoped.length) },
    { label: 'Sign-ready', value: num(scored.filter(e => (e.composite_score ?? 0) >= 70).length) },
    { label: 'Avg score', value: avg != null ? avg.toFixed(1) : '—' },
    { label: 'Needs data', value: num(scoped.length - scored.length) },
  ];

  function pick(e: PortfolioEntity) {
    if (compareMode) setCmp(c => (c.includes(e.id) ? c.filter(x => x !== e.id) : c.length >= 4 ? (toast('Compare up to 4 at a time', 'info'), c) : [...c, e.id]));
    else setSelectedId(selectedId === e.id && !isMobile ? null : e.id);
  }

  const detail = selected && (
    <EntityDetail key={selected.id} entity={selected} watched={watched.has(selected.id)} inSheet={isMobile}
      onToggleWatch={() => toggleWatch(selected)} onClose={() => setSelectedId(null)}
      onCompare={() => { setCompareMode(true); setCmp(c => (c.includes(selected.id) ? c : [...c, selected.id].slice(0, 4))); if (isMobile) setSelectedId(null); toast('Pick one or more to compare', 'info'); }} />
  );

  return (
    <Page title="Intelligence Hub" subtitle={isIndia ? 'Indian artists, comics, teams and films, scored' : 'Global acts, scored'} fill>
      <div className={styles.layout}>
        <div className={styles.listPane}>
          <GlassCard className={styles.stats} delay={0.02}>
            {stats.map(s => (
              <div key={s.label} className={styles.stat}>
                <span className={`${styles.statVal} tnum`} >{isLoading && !all.length ? '…' : s.value}</span>
                <span className="t-caption text-tertiary">{s.label}</span>
              </div>
            ))}
          </GlassCard>

          <div className={styles.toolbar}>
            <div className={styles.toolRow}>
              <div className={styles.searchWrap}>
                <Search size={15} className={styles.searchIcon} />
                <input className={`input ${styles.searchInput}`} type="search" placeholder="Search by name or category" aria-label="Search entities" value={query} onChange={e => setQuery(e.target.value)} />
              </div>
              <Segmented ariaLabel="Sort" value={sort} onChange={setSort} options={[{ value: 'score', label: 'Top score' }, { value: 'name', label: 'A–Z' }]} />
              <button className={`btn btn-sm ${compareMode ? 'btn-primary' : 'btn-tinted'}`} aria-pressed={compareMode} onClick={() => { setCompareMode(m => !m); setCmp([]); }}>
                <GitCompareArrows size={14} /> {compareMode ? 'Done' : 'Compare'}
              </button>
            </div>
            <ChipRow value={type} onChange={setType} options={TYPE_OPTIONS.filter(o => o.value === 'all' || counts[o.value]).map(o => ({ ...o, count: counts[o.value] }))} />
          </div>

          <GlassCard className={styles.listCard}>
            <div className={styles.listHead}>
              <span className="t-footnote text-secondary">{filtered.length} {filtered.length === 1 ? 'result' : 'results'}</span>
              <span className="t-caption text-tertiary">{compareMode ? `${cmp.length}/4 selected` : 'Score out of 100'}</span>
            </div>
            <div className={styles.rows} role="listbox" aria-label="Entities">
              {isLoading && !all.length ? (
                <div style={{ display: 'grid', gap: 8, padding: 6 }}>{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} height={56} radius={12} />)}</div>
              ) : error && !all.length ? (
                <ErrorState message="Couldn’t load the entity portfolio." onRetry={() => reload()} />
              ) : filtered.length === 0 ? (
                <EmptyState title={query ? 'No matches' : `No ${isIndia ? 'Indian' : 'global'} entities here`} message={query ? `Nothing matches “${query}” in ${scope === 'india' ? 'India' : 'Global'}. Try the other market from the toggle above.` : 'Try a different filter.'} />
              ) : filtered.map((e, i) => {
                const on = cmp.includes(e.id);
                return (
                  <motion.button key={e.id} type="button" role="option" aria-selected={compareMode ? on : selectedId === e.id} className={styles.row}
                    onClick={() => pick(e)} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} whileTap={{ scale: 0.985 }}
                    transition={{ duration: 0.28, delay: Math.min(i, 12) * 0.025, ease: [0.22, 1, 0.36, 1] }}>
                  {compareMode ? <span className={styles.check} data-on={on}>{on && <Check size={13} />}</span> : <span className={`${styles.rank} tnum`}>{sort === 'score' ? i + 1 : ''}</span>}
                    <span className={styles.avatar}>{initials(e.name)}</span>
                    <span className={styles.rowMain}>
                      <span className={styles.rowName}>{watched.has(e.id) && <Star size={12} fill="var(--warning)" color="var(--warning)" style={{ flexShrink: 0 }} />}<span>{e.name}</span></span>
                      <span className="t-caption text-tertiary" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.category ?? typeLabel(e.type)} · {typeLabel(e.type)}</span>
                    </span>
                    <span className={styles.scoreCol}>
                      <span className={`${styles.score} tnum`} style={{ color: scoreColor(e.composite_score) }}>{e.composite_score != null ? e.composite_score.toFixed(1) : '—'}</span>
                      <span className={styles.mini}><i style={{ width: `${e.composite_score ?? 0}%`, background: scoreColor(e.composite_score) }} /></span>
                    </span>
                    <span className={styles.badge}><VerdictBadge score={e.composite_score} /></span>
                  </motion.button>
                );
              })}
            </div>
          </GlassCard>
        </div>

        <div className={styles.panelPane}>
          {selected && !isMobile ? (
            <GlassCard className={styles.panel} style={{ padding: 0 }}>{detail}</GlassCard>
          ) : (
            <GlassCard className={styles.empty}>
              <Brain size={38} strokeWidth={1.4} />
              <p className="t-headline text-secondary" style={{ marginTop: 14 }}>Select an entity</p>
              <p className="t-callout" style={{ maxWidth: 240, marginTop: 6 }}>See the score, live signals, strongest cities and a signing verdict.</p>
            </GlassCard>
          )}
        </div>
      </div>

      {isMobile && selected && !compareMode && <Sheet open onClose={() => setSelectedId(null)} title={selected.name}>{detail}</Sheet>}
      {compareMode && cmp.length > 0 && (
        <motion.div className={styles.compareBar} initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
          <span className="t-callout" style={{ fontWeight: 600 }}>{cmp.length} selected</span>
          <button className="btn btn-primary btn-sm" disabled={cmp.length < 2} onClick={() => setCmpOpen(true)}>Compare</button>
          <button className="btn btn-icon" aria-label="Clear selection" onClick={() => setCmp([])}><X size={16} /></button>
        </motion.div>
      )}
      {cmpOpen && cmp.length >= 2 && <CompareSheet ids={cmp} onClose={() => setCmpOpen(false)} />}
    </Page>
  );
}

export default function IntelligencePage() {
  return <Suspense fallback={null}><Hub /></Suspense>;
}
