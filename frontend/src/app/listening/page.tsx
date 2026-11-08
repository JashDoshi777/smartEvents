'use client';

/* eslint-disable react-hooks/set-state-in-effect -- these effects sync state from external sources (URL params, localStorage, debounced network results), which is the intended use */

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { ShieldCheck, MessageCircle, Hash } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { ChipRow } from '@/components/ui/Controls';
import { Skeleton } from '@/components/ui/Skeleton';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { EntityPicker } from '@/components/intel/EntityPicker';
import { useScopedPortfolio } from '@/components/intel/entity-utils';
import { getSentiment, getTopics, getCrisis } from '@/lib/api';
import { compact, timeAgo } from '@/lib/format';
import k from '@/components/intel/Kit.module.css';
import styles from './page.module.css';

const SEV: Record<string, string> = { critical: 'var(--negative)', high: 'var(--text-primary)', medium: 'var(--text-secondary)' };
const labelColor = (l: string | null) => (l === 'positive' ? 'var(--positive)' : l === 'negative' ? 'var(--negative)' : 'var(--text-tertiary)');
const pct = (v: number | null | undefined) => (v == null ? 0 : v * 100);

function Content() {
  const params = useSearchParams();
  const { isIndia } = useMarketScope();
  const { scoped, all, isLoading: pLoading } = useScopedPortfolio();
  const [entityId, setEntityId] = useState('');

  const deep = params.get('entity');
  useEffect(() => { if (deep) setEntityId(deep); }, [deep]);
  // Listening only samples a rotating subset, so probe the top of the market for entities that actually have data.
  const probeIds = scoped.slice(0, 40).map(e => e.id);
  const probe = useSWR(probeIds.length ? ['social/probe', probeIds.join(',')] : null, async () => {
    const res = await Promise.all(probeIds.map(id => getSentiment(id).catch(() => null)));
    return res.filter((r): r is NonNullable<typeof r> => !!r && r.status === 'ok').map(r => ({ id: r.entity_id, name: r.entity_name, n: r.sentiment.sample_size ?? 0 })).sort((a, b) => b.n - a.n);
  }, { revalidateOnFocus: false });
  const sampled = probe.data ?? [];
  useEffect(() => {
    if (deep) return;
    if (entityId && scoped.some(e => e.id === entityId)) return;
    if (probe.data) setEntityId(probe.data[0]?.id ?? scoped.find(e => e.composite_score != null)?.id ?? scoped[0]?.id ?? '');
  }, [probe.data, scoped]); // eslint-disable-line react-hooks/exhaustive-deps

  const crisis = useSWR('social/crisis', getCrisis, { refreshInterval: 120000 });
  const sent = useSWR(entityId ? ['social/sentiment', entityId] : null, () => getSentiment(entityId));
  const topics = useSWR(entityId ? ['social/topics', entityId] : null, () => getTopics(entityId, 30));

  const s = sent.data?.sentiment;
  const ok = sent.data?.status === 'ok';
  const posts = sent.data?.recent_posts ?? [];
  const tops = topics.data?.topics ?? [];
  const alerts = crisis.data?.alerts ?? [];
  const pickerList = (() => { const x = all.find(e => e.id === entityId); return x && !scoped.some(e => e.id === entityId) ? [x, ...scoped] : scoped; })();
  const segs = [
    { k: 'Positive', v: pct(s?.positive), c: 'var(--positive)' },
    { k: 'Neutral', v: pct(s?.neutral), c: 'var(--text-tertiary)' },
    { k: 'Negative', v: pct(s?.negative), c: 'var(--negative)' },
  ];

  return (
    <Page title="Social Listening" subtitle="Reddit and news sentiment, topics and crisis alerts">
      <div>
        <p className={styles.secH}><span>Crisis alerts</span><span>Negative-sentiment spikes, last 24h vs prior 7 days</span></p>
        <GlassCard className={k.group} delay={0.02}>
          {crisis.isLoading && !crisis.data ? <div style={{ padding: 16 }}><Skeleton height={44} radius={12} /></div>
            : crisis.error && !crisis.data ? <ErrorState message="Couldn’t load crisis alerts." onRetry={() => crisis.mutate()} />
            : alerts.length === 0 ? (
              <div className={styles.alertRow}><ShieldCheck size={20} strokeWidth={1.6} color="var(--text-secondary)" /><div><p style={{ fontSize: '.9375rem', fontWeight: 500 }}>All clear</p><p className="t-footnote text-secondary">No negative-sentiment spikes detected right now.</p></div></div>
            ) : alerts.map((a, i) => (
              <motion.div key={a.entity_id} className={styles.alertRow} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: '.9375rem', fontWeight: 500 }}>{a.entity_name}</p>
                  <p className="t-footnote text-secondary">Negative share {Math.round(a.negative_share_prior_7d * 100)}% to {Math.round(a.negative_share_last_24h * 100)}% (+{a.delta_pct_points} pts, {a.posts_last_24h} posts)</p>
                </div>
                <span className="t-footnote" style={{ color: SEV[a.severity], fontWeight: 600, textTransform: 'capitalize' }}>{a.severity}</span>
              </motion.div>
            ))}
        </GlassCard>
      </div>

      <GlassCard style={{ padding: 20 }} delay={0.06}>
        <h2 className={k.title} style={{ marginBottom: 12 }}>Inspect an act</h2>
        <EntityPicker entities={pickerList} value={entityId} onChange={setEntityId} loading={pLoading} placeholder={`Select ${isIndia ? 'an Indian' : 'a global'} act`} />
        {sampled.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <p className="t-footnote text-secondary" style={{ marginBottom: 8 }}>Recently sampled</p>
            <ChipRow value={entityId} onChange={setEntityId} options={sampled.slice(0, 10).map(x => ({ value: x.id, label: x.name, count: x.n }))} />
          </div>
        )}
      </GlassCard>

      {entityId && (
        <>
          <div className={styles.grid}>
            <GlassCard style={{ padding: 20 }} delay={0.1}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                <h2 className={k.title}>Sentiment</h2>
                {s?.last_collected_at && <span className="t-footnote text-tertiary">Collected {timeAgo(s.last_collected_at)}</span>}
              </div>
              {sent.isLoading && !sent.data ? <Skeleton height={150} radius={14} style={{ marginTop: 16 }} />
                : sent.error && !sent.data ? <ErrorState message="Couldn’t load sentiment." onRetry={() => sent.mutate()} />
                : !ok ? <EmptyState icon={<MessageCircle size={30} strokeWidth={1.5} />} title="No social data yet" message="Listening covers a rotating subset of entities every 30 minutes. This one hasn’t been sampled yet." />
                : (
                  <>
                    <div className={styles.stack} role="img" aria-label="Sentiment split">
                      {segs.map((g, i) => <motion.span key={g.k} style={{ background: g.c, borderRadius: 5 }} initial={{ width: 0 }} animate={{ width: `${g.v}%` }} transition={{ type: 'spring', stiffness: 70, damping: 16, delay: i * 0.06 }} />)}
                    </div>
                    <div className={styles.legend}>
                      {segs.map(g => <div key={g.k}><span className="t-footnote text-secondary"><i className={styles.dot} style={{ background: g.c }} />{g.k}</span><b className="num-rounded">{Math.round(g.v)}%</b></div>)}
                    </div>
                    <p className={styles.meta}>{s?.sample_size ?? 0} posts and articles analysed · {s?.reddit_posts_7d ?? 0} Reddit and {s?.news_mentions_7d ?? 0} news mentions in 7 days{s?.compound != null ? ` · net tone ${s.compound >= 0 ? '+' : ''}${s.compound.toFixed(2)}` : ''}</p>
                  </>
                )}
            </GlassCard>

            <div>
              <p className={styles.secH}><span>Trending topics</span><span>Last 30 days</span></p>
              <GlassCard className={k.group} delay={0.14}>
                {topics.isLoading && !topics.data ? <div style={{ padding: 16 }}><Skeleton height={120} radius={12} /></div>
                  : topics.error && !topics.data ? <ErrorState message="Couldn’t load topics." onRetry={() => topics.mutate()} />
                  : tops.length === 0 ? <EmptyState icon={<Hash size={28} strokeWidth={1.5} />} title="No topics yet" message="No topic keywords found in collected posts." />
                  : tops.map((t, i) => (
                    <motion.div key={t.topic} className={k.row} style={{ ['--inset' as string]: '20px', minHeight: 50 }} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                      <span className={k.main}><span className={k.name} style={{ textTransform: 'capitalize' }}>{t.topic}</span></span>
                      <span className={`${k.trail} num-rounded`} style={{ color: 'var(--text-primary)' }}>{compact(t.mentions)}</span>
                    </motion.div>
                  ))}
              </GlassCard>
            </div>
          </div>

          {ok && (
            <div>
              <p className={styles.secH}><span>Recent posts</span></p>
              <GlassCard className={k.group} delay={0.18}>
                {posts.length === 0 ? <p className="t-callout text-tertiary" style={{ padding: 20 }}>No recent posts.</p> : posts.map((p, i) => (
                  <motion.div key={`${i}-${p.analyzed_at}`} className={styles.post} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}>
                    <i className={styles.dot} style={{ background: labelColor(p.sentiment_label), marginTop: 8, marginRight: 0 }} aria-label={p.sentiment_label ?? 'neutral'} />
                    <div className={styles.postText}>
                      <p>{p.content_snippet}</p>
                      <p className={styles.postMeta}><span>{p.platform}</span>{p.likes != null && <span>{compact(p.likes)} likes</span>}{p.comments != null && <span>{compact(p.comments)} comments</span>}<span>{timeAgo(p.analyzed_at)}</span></p>
                    </div>
                  </motion.div>
                ))}
              </GlassCard>
            </div>
          )}
        </>
      )}
    </Page>
  );
}

export default function ListeningPage() {
  return <Suspense fallback={null}><Content /></Suspense>;
}
