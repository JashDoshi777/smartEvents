'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import {
  Radio, ChevronDown, AlertTriangle, MessageCircle, Newspaper, Info,
  ThumbsUp, ThumbsDown, Minus, Siren,
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getEntitySentiment, getEntityTopics, getCrisisAlerts } from '@/lib/api';
import styles from './page.module.css';

function sentimentColor(label?: string) {
  if (label === 'positive') return 'var(--positive)';
  if (label === 'negative') return 'var(--negative)';
  return 'var(--text-tertiary)';
}

function SentimentIcon({ label }: { label?: string }) {
  if (label === 'positive') return <ThumbsUp size={13} />;
  if (label === 'negative') return <ThumbsDown size={13} />;
  return <Minus size={13} />;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--negative)',
  high: 'var(--warning)',
  medium: 'var(--text-secondary)',
};

export default function ListeningPage() {
  const [entityId, setEntityId] = useState('');

  const { data: portfolio } = useSWR('portfolio/listening', () => getPortfolio(), { shouldRetryOnError: false });
  const entities = portfolio?.portfolio ?? [];

  const { data: sentiment, isLoading: loadingSentiment } = useSWR(
    entityId ? `social-sentiment-${entityId}` : null,
    () => getEntitySentiment(entityId),
    { shouldRetryOnError: false }
  );

  const { data: topicsData, isLoading: loadingTopics } = useSWR(
    entityId ? `social-topics-${entityId}` : null,
    () => getEntityTopics(entityId, 30),
    { shouldRetryOnError: false }
  );

  const { data: alertsData, isLoading: loadingAlerts } = useSWR(
    'crisis-alerts', getCrisisAlerts,
    { refreshInterval: 120000, shouldRetryOnError: false }
  );

  const sentimentBreakdown = sentiment?.sentiment ?? {};
  const recentPosts = sentiment?.recent_posts ?? [];
  const topics = topicsData?.topics ?? [];
  const alerts = alertsData?.alerts ?? [];

  const hasSentimentData = sentiment?.status === 'ok';

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Social Listening" subtitle="Real Reddit + News sentiment, topics, and crisis alerts — VADER-scored, no fabricated numbers" />

      <div className={styles.page}>
        {/* Crisis alerts — always visible, not tied to entity selection */}
        <GlassCard className={styles.alertsCard} delay={0.02}>
          <div className={styles.cardHead}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Siren size={15} color="var(--negative)" />
              <h2 className="t-headline text-primary">Crisis Alerts</h2>
            </div>
            <span className="t-caption text-tertiary">Negative-sentiment spikes, last 24h vs prior 7 days</span>
          </div>

          {loadingAlerts ? (
            <div className="skeleton" style={{ height: 60, borderRadius: 10 }} />
          ) : alerts.length === 0 ? (
            <div className={styles.empty}>
              <Info size={18} color="var(--text-tertiary)" strokeWidth={1.5} />
              <p className="t-callout text-tertiary" style={{ marginTop: 8, textAlign: 'center' }}>
                No negative-sentiment spikes detected right now.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {alerts.map((a: any, i: number) => (
                <motion.div
                  key={a.entity_id}
                  className={styles.alertRow}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  style={{ borderColor: (SEVERITY_COLORS[a.severity] ?? 'var(--glass-border)') + '50' }}
                >
                  <AlertTriangle size={15} color={SEVERITY_COLORS[a.severity] ?? 'var(--text-tertiary)'} />
                  <div style={{ flex: 1 }}>
                    <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{a.entity_name}</p>
                    <p className="t-caption text-tertiary">
                      Negative share {a.negative_share_prior_7d * 100}% → {a.negative_share_last_24h * 100}%
                      {' '}(+{a.delta_pct_points}pp, {a.posts_last_24h} posts)
                    </p>
                  </div>
                  <span className="t-caption" style={{ color: SEVERITY_COLORS[a.severity], fontWeight: 700, textTransform: 'uppercase' }}>
                    {a.severity}
                  </span>
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>

        {/* Entity selector */}
        <GlassCard className={styles.selectorCard} delay={0.06}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <Radio size={16} color="var(--accent)" />
            <p className="t-headline text-primary">Inspect entity:</p>
            <div className={styles.selectWrap}>
              <select className={`input ${styles.select}`} value={entityId} onChange={e => setEntityId(e.target.value)}>
                <option value="">Select artist...</option>
                {entities.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
              <ChevronDown size={13} className={styles.selectIcon} />
            </div>
          </div>
        </GlassCard>

        {entityId && (
          <div className={styles.mainGrid}>
            {/* Sentiment breakdown */}
            <GlassCard className={styles.sentimentCard} delay={0.1}>
              <div className={styles.cardHead}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <MessageCircle size={15} color="var(--accent)" />
                  <h2 className="t-headline text-primary">Sentiment Breakdown</h2>
                </div>
              </div>

              {loadingSentiment ? (
                <div className="skeleton" style={{ height: 160, borderRadius: 12 }} />
              ) : !hasSentimentData ? (
                <div className={styles.empty}>
                  <Info size={20} color="var(--text-tertiary)" strokeWidth={1.5} />
                  <p className="t-callout text-tertiary" style={{ marginTop: 10, textAlign: 'center' }}>
                    {sentiment?.message ?? 'No social listening data collected yet for this entity.'}
                  </p>
                </div>
              ) : (
                <>
                  <div className={styles.sentimentBars}>
                    <div className={styles.sentimentBarRow}>
                      <span className="t-caption text-tertiary">Positive</span>
                      <div className={styles.barTrack}>
                        <div className={styles.barFill} style={{ width: `${(sentimentBreakdown.positive ?? 0) * 100}%`, background: 'var(--positive)' }} />
                      </div>
                      <span className="t-caption text-primary">{Math.round((sentimentBreakdown.positive ?? 0) * 100)}%</span>
                    </div>
                    <div className={styles.sentimentBarRow}>
                      <span className="t-caption text-tertiary">Neutral</span>
                      <div className={styles.barTrack}>
                        <div className={styles.barFill} style={{ width: `${(sentimentBreakdown.neutral ?? 0) * 100}%`, background: 'var(--text-tertiary)' }} />
                      </div>
                      <span className="t-caption text-primary">{Math.round((sentimentBreakdown.neutral ?? 0) * 100)}%</span>
                    </div>
                    <div className={styles.sentimentBarRow}>
                      <span className="t-caption text-tertiary">Negative</span>
                      <div className={styles.barTrack}>
                        <div className={styles.barFill} style={{ width: `${(sentimentBreakdown.negative ?? 0) * 100}%`, background: 'var(--negative)' }} />
                      </div>
                      <span className="t-caption text-primary">{Math.round((sentimentBreakdown.negative ?? 0) * 100)}%</span>
                    </div>
                  </div>
                  <p className="t-caption text-tertiary" style={{ marginTop: 14 }}>
                    {sentimentBreakdown.sample_size} real posts/articles analyzed · {sentimentBreakdown.reddit_posts_7d ?? 0} Reddit mentions (7d) · {sentimentBreakdown.news_mentions_7d ?? 0} news mentions (7d)
                  </p>
                </>
              )}
            </GlassCard>

            {/* Topics */}
            <GlassCard className={styles.topicsCard} delay={0.14}>
              <div className={styles.cardHead}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Newspaper size={15} color="var(--accent)" />
                  <h2 className="t-headline text-primary">Trending Topics</h2>
                </div>
                <span className="t-caption text-tertiary">Last 30 days, keyword-based</span>
              </div>

              {loadingTopics ? (
                <div className="skeleton" style={{ height: 120, borderRadius: 12 }} />
              ) : topics.length === 0 ? (
                <div className={styles.empty}>
                  <p className="t-callout text-tertiary" style={{ textAlign: 'center' }}>
                    No topic mentions found in collected posts yet.
                  </p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {topics.map((t: any, i: number) => (
                    <motion.div key={t.topic} className={styles.topicRow} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                      <span className="t-callout text-primary" style={{ textTransform: 'capitalize', fontWeight: 600 }}>{t.topic}</span>
                      <span className="t-callout text-primary" style={{ fontWeight: 700 }}>{t.mentions}</span>
                    </motion.div>
                  ))}
                </div>
              )}
            </GlassCard>
          </div>
        )}

        {entityId && hasSentimentData && (
          <GlassCard delay={0.18} style={{ padding: 18 }}>
            <div className={styles.cardHead}>
              <h2 className="t-headline text-primary">Recent Posts</h2>
            </div>
            {recentPosts.length === 0 ? (
              <p className="t-callout text-tertiary">No recent posts.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {recentPosts.map((p: any, i: number) => (
                  <div key={i} className={styles.postRow}>
                    <span style={{ color: sentimentColor(p.sentiment_label), flexShrink: 0, display: 'flex', alignItems: 'center' }}>
                      <SentimentIcon label={p.sentiment_label} />
                    </span>
                    <p className="t-callout text-primary" style={{ flex: 1 }}>{p.content_snippet}</p>
                    <span className="t-caption text-tertiary" style={{ flexShrink: 0, textTransform: 'capitalize' }}>{p.platform}</span>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>
        )}

        {!entityId && (
          <GlassCard className={styles.placeholder} delay={0.1}>
            <Radio size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Select an artist above to see their social sentiment</p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
