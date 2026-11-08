'use client';

/* eslint-disable react-hooks/set-state-in-effect -- these effects sync state from external sources (URL params, localStorage, debounced network results), which is the intended use */

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { AnimatePresence, motion } from 'framer-motion';
import { Star, Search, Plus, Check, X, Loader2 } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { getWatchlist, addToWatchlist, removeFromWatchlist, searchEntities, EntitySearchResult, WatchlistResponse } from '@/lib/api';
import { dateIN } from '@/lib/format';
import styles from './page.module.css';

export default function WatchlistPage() {
  const toast = useToast();
  const { data, error, isLoading, mutate } = useSWR('watchlist', () => getWatchlist());
  const [q, setQ] = useState('');
  const [results, setResults] = useState<EntitySearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const list = data?.watchlist ?? [];
  const watched = new Set(list.map(e => e.id));

  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); setSearching(false); return; }
    setSearching(true);
    let cancelled = false;
    const t = setTimeout(async () => {
      try { const r = await searchEntities(q.trim(), 8); if (!cancelled) setResults(r.results); }
      catch { if (!cancelled) setResults([]); }
      finally { if (!cancelled) setSearching(false); }
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q]);

  async function add(e: EntitySearchResult) {
    setBusy(e.id);
    try {
      await addToWatchlist(e.id);
      await mutate();
      toast(`${e.name} added to watchlist`, 'success');
    } catch { toast('Couldn’t add to watchlist', 'error'); }
    finally { setBusy(null); }
  }

  async function remove(id: string, name: string) {
    setBusy(id);
    const prev = data;
    // optimistic
    mutate((cur?: WatchlistResponse) => cur && { watchlist: cur.watchlist.filter(w => w.id !== id), total: cur.total - 1 }, { revalidate: false });
    try {
      await removeFromWatchlist(id);
      toast(`${name} removed`, 'info');
    } catch {
      mutate(prev, { revalidate: false });
      toast('Couldn’t remove — try again', 'error');
    } finally { setBusy(null); mutate(); }
  }

  return (
    <Page title="Watchlist" subtitle="Track acts — their signals surface first in your notifications">
      <div className={styles.wrap}>
        <div className={styles.searchBox}>
          <Search size={16} style={{ position: 'absolute', left: 14, top: 15, color: 'var(--text-tertiary)' }} />
          <input className="input" style={{ paddingLeft: 40, minHeight: 46 }} placeholder="Search artists to add (e.g. Arijit Singh)" value={q} onChange={e => setQ(e.target.value)} aria-label="Search acts to add" />
          {searching && <Loader2 size={16} className="spin" style={{ position: 'absolute', right: 14, top: 15, color: 'var(--text-tertiary)' }} />}
          {q.trim().length >= 2 && !searching && (
            <div className={`list-group ${styles.results}`}>
              {results.length === 0 ? <p className="t-callout text-tertiary" style={{ padding: 16 }}>No acts match “{q.trim()}”.</p> : results.map(r => (
                <div key={r.id} className="list-row">
                  <div className={styles.avatar}>{r.name.charAt(0).toUpperCase()}</div>
                  <div className={styles.info}>
                    <span className={`t-callout ${styles.ellip}`} style={{ fontWeight: 600 }}>{r.name}</span>
                    <span className="t-footnote text-tertiary">{r.category ?? r.entity_type}{r.is_international ? ' · Global' : ' · India'}</span>
                  </div>
                  {watched.has(r.id)
                    ? <span className="badge badge-green"><Check size={12} /> Watching</span>
                    : <button className="btn btn-tinted btn-sm" onClick={() => add(r)} disabled={busy === r.id} aria-label={`Add ${r.name} to watchlist`}>{busy === r.id ? <Loader2 size={13} className="spin" /> : <Plus size={14} />} Watch</button>}
                </div>
              ))}
            </div>
          )}
        </div>

        {isLoading && !data ? <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{[0, 1, 2].map(i => <Skeleton key={i} height={64} radius={18} />)}</div>
          : error && !data ? <ErrorState message="Couldn’t load your watchlist." onRetry={() => mutate()} />
          : list.length === 0 ? <div className="glass-card"><EmptyState icon={<Star size={34} strokeWidth={1.4} />} title="Your watchlist is empty" message="Search above to start tracking artists and acts." /></div>
          : (
            <div className="list-group" aria-label="Watched acts">
              <AnimatePresence initial={false}>
                {list.map(e => (
                  <motion.div key={e.id} layout initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.25 }} style={{ overflow: 'hidden' }}>
                    <div className="list-row" data-testid="watch-row">
                      <div className={styles.avatar}>{e.name.charAt(0).toUpperCase()}</div>
                      <div className={styles.info}>
                        <span className={`t-callout ${styles.ellip}`} style={{ fontWeight: 600 }}>{e.name}</span>
                        <span className="t-footnote text-tertiary">{e.category ?? 'Music'}{e.is_international ? ' · Global' : ' · India'}{e.watched_since ? ` · since ${dateIN(e.watched_since, { day: 'numeric', month: 'short' })}` : ''}</span>
                      </div>
                      {e.composite_score != null && (
                        <Link href={`/intelligence?entity=${e.id}`} style={{ textAlign: 'right', textDecoration: 'none', color: 'inherit', flexShrink: 0 }} aria-label={`${e.name} score ${e.composite_score}`}>
                          <div className="num-rounded t-headline">{e.composite_score.toFixed(1)}</div>
                          {e.score_delta != null && e.score_delta !== 0
                            ? <div className="t-caption num-rounded" style={{ color: e.score_delta > 0 ? 'var(--positive)' : 'var(--negative)' }}>{e.score_delta > 0 ? '+' : ''}{e.score_delta.toFixed(1)} since added</div>
                            : <div className="t-caption text-tertiary">no change</div>}
                        </Link>
                      )}
                      <button className={styles.rm} onClick={() => remove(e.id, e.name)} disabled={busy === e.id} aria-label={`Remove ${e.name} from watchlist`}><X size={17} /></button>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
      </div>
    </Page>
  );
}
