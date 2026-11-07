'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Brain, ChevronDown, Info, TrendingUp, TrendingDown } from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getCities, getPsychologyReport } from '@/lib/api';
import styles from './page.module.css';

function multiplierColor(m: number) {
  if (m > 1.01) return 'var(--positive)';
  if (m < 0.99) return 'var(--negative)';
  return 'var(--text-tertiary)';
}

export default function PsychologyPage() {
  const [entityId, setEntityId] = useState('');
  const [city, setCity] = useState('');

  const { data: portfolio } = useSWR('portfolio/psychology', () => getPortfolio(), { shouldRetryOnError: false });
  const entities = portfolio?.portfolio ?? [];
  const { data: citiesData } = useSWR('cities/psychology', () => getCities(), { shouldRetryOnError: false });
  const cities = citiesData?.cities ?? [];

  const { data: report, isLoading } = useSWR(
    entityId ? `psychology-${entityId}-${city}` : null,
    () => getPsychologyReport(entityId, city || undefined),
    { shouldRetryOnError: false }
  );

  const combined = report?.combined_multiplier ?? 1.0;
  const pctChange = Math.round((combined - 1) * 100);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Psychological Demand Analysis" subtitle="Real overexposure, novelty, FOMO, and controversy-drag effects — computed from actual event and social history, not guessed" />

      <div className={styles.page}>
        <GlassCard className={styles.selectorCard} delay={0.04}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <Brain size={16} color="var(--accent)" />
            <p className="t-headline text-primary">Analyze:</p>
            <div className={styles.selectWrap}>
              <select className={`input ${styles.select}`} value={entityId} onChange={e => setEntityId(e.target.value)}>
                <option value="">Select artist...</option>
                {entities.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
              <ChevronDown size={13} className={styles.selectIcon} />
            </div>
            <div className={styles.selectWrap}>
              <select className={`input ${styles.select}`} value={city} onChange={e => setCity(e.target.value)}>
                <option value="">All cities</option>
                {cities.map((c: any) => <option key={c.id} value={c.name}>{c.name}</option>)}
              </select>
              <ChevronDown size={13} className={styles.selectIcon} />
            </div>
          </div>
        </GlassCard>

        {!entityId && (
          <GlassCard className={styles.placeholder} delay={0.08}>
            <Brain size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Select an artist to see real psychological demand factors</p>
          </GlassCard>
        )}

        {entityId && isLoading && (
          <div className="skeleton" style={{ height: 220, borderRadius: 16 }} />
        )}

        {entityId && report && (
          <>
            <GlassCard className={styles.heroCard} delay={0.06}>
              <p className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem', marginBottom: 8 }}>
                {report.entity_name}{city ? ` · ${city}` : ' · all tracked cities'}
              </p>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={{ fontSize: '2.4rem', fontWeight: 800, color: multiplierColor(combined) }}>
                  {combined.toFixed(2)}×
                </span>
                <span className="t-callout" style={{ color: multiplierColor(combined), fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                  {pctChange > 0 ? <TrendingUp size={15} /> : pctChange < 0 ? <TrendingDown size={15} /> : null}
                  {pctChange > 0 ? `+${pctChange}%` : pctChange < 0 ? `${pctChange}%` : 'no adjustment'}
                </span>
              </div>
              <p className="t-caption text-tertiary" style={{ marginTop: 10, lineHeight: 1.6 }}>{report.interpretation}</p>
            </GlassCard>

            <div className={styles.factorsGrid}>
              {report.factors.map((f: any, i: number) => (
                <motion.div key={f.name} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
                  <GlassCard className={styles.factorCard} delay={0}>
                    <div className={styles.factorHead}>
                      <span className="t-callout text-primary" style={{ fontWeight: 700, textTransform: 'capitalize' }}>
                        {f.name.replace('_', ' ')}
                      </span>
                      <span style={{ fontWeight: 800, color: multiplierColor(f.multiplier) }}>{f.multiplier.toFixed(2)}×</span>
                    </div>
                    <p className="t-caption text-tertiary" style={{ lineHeight: 1.6, marginTop: 8 }}>{f.explanation}</p>
                    <div className={styles.signalRow}>
                      {Object.entries(f.real_signal).map(([k, v]: [string, any]) => (
                        v !== null && v !== undefined && (
                          <span key={k} className={styles.signalChip}>{k.replace(/_/g, ' ')}: {String(v)}</span>
                        )
                      ))}
                    </div>
                  </GlassCard>
                </motion.div>
              ))}
            </div>

            {report.data_coverage_note && report.data_coverage_note !== 'All four factors had real data to evaluate.' && (
              <GlassCard style={{ padding: 16 }} delay={0.2}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <Info size={15} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: 1 }} />
                  <p className="t-caption text-tertiary" style={{ lineHeight: 1.6 }}>
                    Coverage gaps: {report.data_coverage_note}
                  </p>
                </div>
              </GlassCard>
            )}
          </>
        )}
      </div>
    </div>
  );
}
