'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import {
  Users2, ChevronDown, AlertCircle, Info, Sparkles,
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getCities, recommendPairs, PairRecommendResponse } from '@/lib/api';
import styles from './page.module.css';

const MARKETS = ['All', 'India', 'Global'] as const;
type MarketFilter = typeof MARKETS[number];

function scoreColor(score: number) {
  if (score >= 80) return 'var(--positive)';
  if (score >= 50) return 'var(--warning)';
  return 'var(--text-tertiary)';
}

export default function PairingRecommenderPage() {
  const [city, setCity] = useState('');
  const [anchorEntityId, setAnchorEntityId] = useState('');
  const [budget, setBudget] = useState('');
  const [market, setMarket] = useState<MarketFilter>('All');
  const [result, setResult] = useState<PairRecommendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: portfolio } = useSWR('portfolio/pairing', () => getPortfolio(), { shouldRetryOnError: false });
  const { data: citiesData } = useSWR('cities/pairing', () => getCities(), { shouldRetryOnError: false });

  const allEntities = portfolio?.portfolio ?? [];
  const indiaCount = allEntities.filter(e => !e.is_international).length;
  const globalCount = allEntities.filter(e => e.is_international).length;
  const entities = allEntities.filter(e => {
    if (market === 'India') return !e.is_international;
    if (market === 'Global') return e.is_international;
    return true;
  });
  const cities = citiesData?.cities ?? [];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!city) {
      setError('Select a city before finding pairings.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await recommendPairs({
        city,
        anchor_entity_id: anchorEntityId || undefined,
        budget: budget ? Number(budget) : undefined,
        market: market === 'All' ? undefined : market,
        limit: 8,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to find pairings. Ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Artist Pairing Recommender" subtitle="Find genre-compatible, similar-tier artists to co-headline a shared bill" />

      <div className={styles.page}>
        <GlassCard className={styles.formCard} delay={0.04}>
          <div className={styles.formHeader}>
            <Users2 size={18} color="var(--accent)" />
            <div>
              <h2 className="t-headline text-primary">Configure the Search</h2>
              <p className="t-footnote text-tertiary">Optionally anchor to one artist to find their best pairing partners, or leave blank to rank all pairs</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className={styles.form}>
            {/* Market toggle */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {MARKETS.map(m => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setMarket(m); setAnchorEntityId(''); }}
                  style={{
                    padding: '4px 12px', borderRadius: 999, fontSize: '0.75rem', fontWeight: 500,
                    background: market === m ? 'var(--accent-dim)' : 'var(--glass-fill)',
                    border: `1px solid ${market === m ? 'var(--accent)' : 'var(--glass-border)'}`,
                    color: market === m ? 'var(--accent)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  {m}
                  {m === 'India' && ` (${indiaCount})`}
                  {m === 'Global' && ` (${globalCount})`}
                </button>
              ))}
            </div>

            <div className={styles.formGrid}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="pair-city">City</label>
                <div className={styles.selectWrap}>
                  <select
                    id="pair-city"
                    className={`input ${styles.select}`}
                    value={city}
                    onChange={e => setCity(e.target.value)}
                    required
                    disabled={cities.length === 0}
                  >
                    <option value="">{cities.length > 0 ? 'Select city...' : 'Cities unavailable'}</option>
                    {cities.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="pair-anchor">Anchor Artist (optional)</label>
                <div className={styles.selectWrap}>
                  <select id="pair-anchor" className={`input ${styles.select}`} value={anchorEntityId} onChange={e => setAnchorEntityId(e.target.value)}>
                    <option value="">Rank all pairs...</option>
                    {entities.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="pair-budget">Combined Budget (₹, optional)</label>
                <input
                  id="pair-budget"
                  className="input"
                  type="number"
                  min={0}
                  placeholder="e.g. 2000000"
                  value={budget}
                  onChange={e => setBudget(e.target.value)}
                />
              </div>
            </div>

            {error && (
              <div className={styles.errorBox}>
                <AlertCircle size={16} color="var(--negative)" />
                <span className="t-callout" style={{ color: 'var(--negative)' }}>{error}</span>
              </div>
            )}

            <button type="submit" className="btn btn-primary" disabled={loading} style={{ alignSelf: 'flex-start' }}>
              {loading ? 'Finding pairings...' : 'Find Pairings'}
            </button>
          </form>
        </GlassCard>

        {result && (
          <motion.div className={styles.resultWrap} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <div className={styles.summaryRow}>
              <span className="t-footnote text-tertiary">{result.candidates_considered} candidates considered</span>
              <span className="t-footnote text-tertiary">{result.pairs_matching_genre} pairs share a genre</span>
              {result.anchor_entity && (
                <span className="t-footnote text-tertiary">Anchored to <strong className="text-secondary">{result.anchor_entity.name}</strong></span>
              )}
            </div>

            {result.recommendations.length === 0 ? (
              <GlassCard className={styles.placeholder} delay={0.05}>
                <Users2 size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
                <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>No genre-compatible pairs found for this selection</p>
              </GlassCard>
            ) : (
              <div className={styles.pairGrid}>
                {result.recommendations.map((p, i) => (
                  <GlassCard key={`${p.entity_a.id}-${p.entity_b.id}`} className={styles.pairCard} delay={0.05 + i * 0.03}>
                    <div className={styles.pairArtists}>
                      <div className={styles.artistBox}>
                        <span className={`t-callout text-primary ${styles.artistName}`}>{p.entity_a.name}</span>
                        <span className="t-caption text-tertiary">{p.entity_a.composite_score ?? '—'} score</span>
                      </div>
                      <Sparkles size={14} className={styles.pairDivider} />
                      <div className={styles.artistBox}>
                        <span className={`t-callout text-primary ${styles.artistName}`}>{p.entity_b.name}</span>
                        <span className="t-caption text-tertiary">{p.entity_b.composite_score ?? '—'} score</span>
                      </div>
                    </div>

                    <div className={styles.pairMeta}>
                      <span className={styles.scoreBadge} style={{ color: scoreColor(p.similarity_score) }}>
                        {p.similarity_score}%
                      </span>
                      <div className={styles.genreTags}>
                        {p.shared_genres.map(g => <span key={g} className={styles.genreTag}>{g}</span>)}
                      </div>
                      {p.combined_booking_fee_estimate !== null && (
                        <span className="t-caption text-tertiary">
                          ~{new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(p.combined_booking_fee_estimate)} combined fee
                        </span>
                      )}
                    </div>
                  </GlassCard>
                ))}
              </div>
            )}

            <GlassCard style={{ padding: 18 }} delay={0.1}>
              <div className={styles.noteBox}>
                <Info size={15} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: 1 }} />
                <p className="t-caption text-tertiary" style={{ lineHeight: 1.6 }}>{result.methodology}</p>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {!result && !loading && (
          <GlassCard className={styles.placeholder} delay={0.1}>
            <Users2 size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Select a city above to find pairing recommendations</p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
