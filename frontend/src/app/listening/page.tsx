'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Radio, ShieldCheck, Siren, MessageCircle, Hash, ThumbsUp, ThumbsDown, Minus, Heart, MessagesSquare } from 'lucide-react';
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
import styles from './page.module.css';

const SEV: Record<string, string> = { critical: 'var(--negative)', high: 'var(--text-primary)', medium: 'var(--text-secondary)' };
const labelColor = (l: string | null) => (l === 'positive' ? 'var(--positive)' : l === 'negative' ? 'var(--negative)' : 'var(--text-tertiary)');
const LabelIcon = ({ l }: { l: string | null }) => (l === 'positive' ? <ThumbsUp size={13} /> : l === 'negative' ? <ThumbsDown size={13} /> : <Minus size={13} />);
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
  const maxTop = Math.max(1, ...tops.map(t => t.mentions));
  const alerts = crisis.data?.alerts ?? [];
  const pickerList = (() => { const x = all.find(e => e.id === entityId); return x && !scoped.some(e => e.id === entityId) ? [x, ...scoped] : scoped; })();
  const segs = [
    { k: 'Positive', v: pct(s?.positive), c: 'var(--positive)' },
    { k: 'Neutral', v: pct(s?.neutral), c: 'var(--text-tertiary)' },
    { k: 'Negative', v: pct(s?.negative), c: 'var(--negative)' },
  ];

  return (
    <Page title="Social Listening" subtitle="Reddit and news sentiment, topics and crisis alerts, scored with VADER">
      <GlassCard className={styles.card} delay={0.02}>
        <div className={styles.head}>
          <h2 className="t-headline" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Siren size={16} /> Crisis alerts</h2>
          <span className="t-caption text-tertiary">Negative-sentiment spikes, last 24h vs prior 7 days</span>
        </div>
        {crisis.isLoading && !crisis.data ? <Skeleton height={56} radius={14} />
          : crisis.error && !crisis.data ? <ErrorState message="Couldn’t load crisis alerts." onRetry={() => crisis.mutate()} />
          : alerts.length === 0 ? (
            <div className={styles.clear}>
              <span className={styles.clearIcon}><ShieldCheck size={20} /></span>
              <div><p className="t-callout" style={{ fontWeight: 600 }}>All clear</p><p className="t-footnote text-tertiary">No negative-sentiment spikes detected right now.</p></div>
            </div>
          ) : alerts.map((a, i) => (
            <motion.div key={a.entity_id} className={styles.alert} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
              <Siren size={16} color={SEV[a.severity]} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p className="t-callout" style={{ fontWeight: 600 }}>{a.entity_name}</p>
                <p className="t-caption text-tertiary">Negative share {Math.round(a.negative_share_prior_7d * 100)}% to {Math.round(a.negative_share_last_24h * 100)}% (+{a.delta_pct_points} pts, {a.posts_last_24h} posts)</p>
              </div>
              <span className="t-caption" style={{ color: SEV[a.severity], fontWeight: 700, textTransform: 'uppercase' }}>{a.severity}</span>
            </motion.div>
          ))}
      </GlassCard>

      <GlassCard className={styles.card} delay={0.06}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <Radio size={18} color="var(--text-secondary)" />
          <p className="t-headline">Inspect</p>
          <div style={{ flex: 1, minWidth: 220 }}><EntityPicker entities={pickerList} value={entityId} onChange={setEntityId} loading={pLoading} placeholder={`Select ${isIndia ? 'an Indian' : 'a global'} act`} /></div>
        </div>
        {sampled.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <p className="t-caption text-tertiary" style={{ marginBottom: 8 }}>Recently sampled</p>
            <ChipRow value={entityId} onChange={setEntityId} options={sampled.slice(0, 10).map(x => ({ value: x.id, label: x.name, count: x.n }))} />
          </div>
        )}
      </GlassCard>

      {entityId && (
        <>
          <div className={styles.grid}>
            <GlassCard className={styles.card} delay={0.1}>
              <div className={styles.head}><h2 className="t-headline" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><MessageCircle size={16} /> Sentiment</h2>
                {s?.last_collected_at && <span className="t-caption text-tertiary">Collected {timeAgo(s.last_collected_at)}</span>}</div>
              {sent.isLoading && !sent.data ? <Skeleton height={170} radius={14} />
                : sent.error && !sent.data ? <ErrorState message="Couldn’t load sentiment." onRetry={() => sent.mutate()} />
                : !ok ? <EmptyState icon={<MessageCircle size={32} strokeWidth={1.4} />} title="No social data yet" message="Listening covers a rotating subset of entities every 30 minutes. This one hasn’t been sampled yet." />
                : (
                  <>
                    <div className={styles.stack} role="img" aria-label="Sentiment split">
                      {segs.map((g, i) => <motion.span key={g.k} style={{ background: g.c, borderRadius: 7 }} initial={{ width: 0 }} animate={{ width: `${g.v}%` }} transition={{ duration: 0.7, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }} />)}
                    </div>
                    <div className={styles.legend}>
                      {segs.map(g => <div key={g.k} className={styles.legendItem}><span className="t-caption text-tertiary"><i className={styles.dot} style={{ background: g.c }} />{g.k}</span><b className="tnum">{Math.round(g.v)}%</b></div>)}
                    </div>
                    <div className={styles.meta}>
                      <span className="t-caption text-tertiary">{s?.sample_size ?? 0} posts and articles analysed</span>
                      <span className="t-caption text-tertiary">{s?.reddit_posts_7d ?? 0} Reddit (7d)</span>
                      <span className="t-caption text-tertiary">{s?.news_mentions_7d ?? 0} news (7d)</span>
                      {s?.compound != null && <span className="t-caption text-tertiary">Net tone {s.compound >= 0 ? '+' : ''}{s.compound.toFixed(2)}</span>}
                    </div>
                  </>
                )}
            </GlassCard>

            <GlassCard className={styles.card} delay={0.14}>
              <div className={styles.head}><h2 className="t-headline" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Hash size={16} /> Trending topics</h2><span className="t-caption text-tertiary">Last 30 days</span></div>
              {topics.isLoading && !topics.data ? <Skeleton height={140} radius={14} />
                : topics.error && !topics.data ? <ErrorState message="Couldn’t load topics." onRetry={() => topics.mutate()} />
                : tops.length === 0 ? <EmptyState icon={<Hash size={30} strokeWidth={1.4} />} title="No topics yet" message="No topic keywords found in collected posts." />
                : tops.map((t, i) => (
                  <div key={t.topic} className={styles.topic}>
                    <div className={styles.topicTop}><span>{t.topic}</span><span className="tnum text-secondary">{compact(t.mentions)}</span></div>
                    <div className={styles.track}><motion.i initial={{ width: 0 }} animate={{ width: `${(t.mentions / maxTop) * 100}%` }} transition={{ duration: 0.7, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] }} /></div>
                  </div>
                ))}
            </GlassCard>
          </div>

          {ok && (
            <GlassCard className={styles.card} delay={0.18}>
              <div className={styles.head}><h2 className="t-headline">Recent posts</h2></div>
              {posts.length === 0 ? <p className="t-callout text-tertiary">No recent posts.</p> : posts.map((p, i) => (
                <motion.div key={`${i}-${p.analyzed_at}`} className={styles.post} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}>
                  <span className={styles.postIcon} style={{ color: labelColor(p.sentiment_label), background: `color-mix(in srgb, ${labelColor(p.sentiment_label)} 14%, transparent)` }}><LabelIcon l={p.sentiment_label} /></span>
                  <div className={styles.postText}>
                    <p>{p.content_snippet}</p>
                    <p className="t-caption text-tertiary" style={{ marginTop: 4, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      {p.likes != null && <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}><Heart size={11} /> {compact(p.likes)}</span>}
                      {p.comments != null && <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}><MessagesSquare size={11} /> {compact(p.comments)}</span>}
                      <span>{timeAgo(p.analyzed_at)}</span>
                    </p>
                  </div>
                  <span className={styles.platform}>{p.platform}</span>
                </motion.div>
              ))}
            </GlassCard>
          )}
        </>
      )}
    </Page>
  );
}

export default function ListeningPage() {
  return <Suspense fallback={null}><Content /></Suspense>;
}
