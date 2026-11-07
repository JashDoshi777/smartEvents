'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Brain, Info, TrendingUp, TrendingDown, Eye, Timer, Flame, Sparkles, Minus } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton, SkeletonCard } from '@/components/ui/Skeleton';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { EntityPicker } from '@/components/intel/EntityPicker';
import { useScopedPortfolio } from '@/components/intel/entity-utils';
import { getCities, getPsychology } from '@/lib/api';
import styles from './page.module.css';

const FACTOR_META: Record<string, { label: string; Icon: typeof Eye; blurb: string }> = {
  exposure: { label: 'Overexposure and novelty', Icon: Eye, blurb: 'How recently and often this act has played the market' },
  novelty: { label: 'Novelty', Icon: Sparkles, blurb: 'Freshness in this market' },
  fomo: { label: 'FOMO and competing events', Icon: Timer, blurb: 'Same-weekend competition and scarcity' },
  controversy_drag: { label: 'Controversy drag', Icon: Flame, blurb: 'Negative social sentiment pulling demand down' },
};

const tone = (m: number) => (m > 1.01 ? 'var(--positive)' : m < 0.99 ? 'var(--negative)' : 'var(--text-tertiary)');
const toneBg = (m: number) => (m > 1.01 ? 'var(--positive-dim)' : m < 0.99 ? 'var(--negative-dim)' : 'var(--fill-tertiary)');

function Content() {
  const params = useSearchParams();
  const { isIndia } = useMarketScope();
  const { scoped, all, isLoading: pLoading } = useScopedPortfolio();
  const [entityId, setEntityId] = useState('');
  const [city, setCity] = useState('Mumbai');

  const cities = useSWR('cities/all', () => getCities());
  const cityList = cities.data?.cities ?? [];

  const deep = params.get('entity');
  useEffect(() => { if (deep) setEntityId(deep); }, [deep]);
  // Default to the top-scoring entity in the current market so the page opens with real analysis.
  useEffect(() => {
    if (!entityId && !deep && scoped.length) setEntityId(scoped.find(e => e.composite_score != null)?.id ?? scoped[0].id);
  }, [scoped, entityId, deep]);
  // If the market toggle changes and the pick no longer belongs, move to that market's leader.
  useEffect(() => {
    if (entityId && scoped.length && !deep && !scoped.some(e => e.id === entityId)) setEntityId(scoped.find(e => e.composite_score != null)?.id ?? scoped[0].id);
  }, [scoped]); // eslint-disable-line react-hooks/exhaustive-deps

  const report = useSWR(entityId ? ['psychology', entityId, city] : null, () => getPsychology(entityId, city || undefined), { keepPreviousData: false });
  const r = report.data;
  const combined = r?.combined_multiplier ?? 1;
  const pct = Math.round((combined - 1) * 100);
  const pos = Math.max(0, Math.min(100, ((combined - 0.7) / 0.6) * 100));
  const pickerList = (() => { const x = all.find(e => e.id === entityId); return x && !scoped.some(e => e.id === entityId) ? [x, ...scoped] : scoped; })();

  return (
    <Page title="Demand Psychology" subtitle="How overexposure, FOMO and controversy move demand">
      <GlassCard className={styles.card} delay={0.04}>
        <div className={styles.sel}>
          <Brain size={18} color="var(--text-secondary)" />
          <div className={styles.selCol}>
            <EntityPicker entities={pickerList} value={entityId} onChange={setEntityId} loading={pLoading} placeholder={`Select ${isIndia ? 'an Indian' : 'a global'} act`} />
            <ChipRow value={city} onChange={setCity} options={[{ value: '', label: 'All cities' }, ...cityList.map(c => ({ value: c.name, label: c.name }))]} />
          </div>
        </div>
      </GlassCard>

      {!entityId ? (
        <GlassCard delay={0.08}><EmptyState icon={<Brain size={34} strokeWidth={1.4} />} title="Select an act" message="Pick an artist, comic or team to see what is helping or hurting demand." /></GlassCard>
      ) : report.isLoading && !r ? (
        <><Skeleton height={190} radius={22} /><div className={styles.factors}><SkeletonCard lines={3} height={170} /><SkeletonCard lines={3} height={170} /><SkeletonCard lines={3} height={170} /></div></>
      ) : report.error && !r ? (
        <GlassCard><ErrorState message="Couldn’t compute the psychology report for this selection." onRetry={() => report.mutate()} /></GlassCard>
      ) : r && (
        <>
          <GlassCard className={styles.hero} delay={0.06}>
            <div className={styles.heroTop}>
              <div>
                <p className="t-footnote text-tertiary" style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>{r.entity_name} · {city || 'all tracked cities'}</p>
                <motion.span key={`${entityId}${city}`} className={`${styles.big} tnum`} style={{ color: tone(combined) }} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>{combined.toFixed(2)}×</motion.span>
              </div>
              <span className={styles.delta} style={{ color: tone(combined), background: toneBg(combined) }}>
                {pct > 0 ? <TrendingUp size={15} /> : pct < 0 ? <TrendingDown size={15} /> : <Minus size={15} />}
                {pct > 0 ? `+${pct}% demand` : pct < 0 ? `${pct}% demand` : 'No adjustment'}
              </span>
            </div>
            <div>
              <div className={styles.scale}><motion.span className={styles.mark} initial={{ left: '50%' }} animate={{ left: `${pos}%` }} transition={{ type: 'spring', stiffness: 80, damping: 15 }} /></div>
              <div className={styles.ticks}><span>0.70× suppressed</span><span>1.00×</span><span>1.30× boosted</span></div>
            </div>
            <p className="t-footnote text-secondary" style={{ lineHeight: 1.55, maxWidth: 760 }}>{combined > 1.01 ? 'Real signals are lifting expected demand for this act. Apply this multiplier to fill-rate and revenue estimates.' : combined < 0.99 ? 'Real signals are suppressing expected demand for this act. Apply this multiplier to fill-rate and revenue estimates, or reconsider timing.' : 'No psychological adjustment: there is not enough real signal to move demand up or down. Treat as a neutral 1.00× multiplier on fill-rate estimates.'}</p>
          </GlassCard>

          <div className={styles.factors}>
            {r.factors.map((f, i) => {
              const meta = FACTOR_META[f.name] ?? { label: f.name.replace(/_/g, ' '), Icon: Info, blurb: '' };
              const sigs = Object.entries(f.real_signal ?? {}).filter(([, v]) => v !== null && v !== undefined);
              return (
                <motion.div key={f.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.06, duration: 0.36, ease: [0.22, 1, 0.36, 1] }}>
                  <GlassCard className={styles.factor}>
                    <div className={styles.fHead}>
                      <span className={styles.fIcon} style={{ background: 'var(--fill-tertiary)', color: 'var(--text-secondary)' }}><meta.Icon size={18} /></span>
                      <span className={styles.fName}>{meta.label}</span>
                      <span className={`${styles.fMult} tnum`} style={{ color: tone(f.multiplier) }}>{f.multiplier.toFixed(2)}×</span>
                    </div>
                    <p className="t-footnote text-secondary" style={{ lineHeight: 1.5 }}>{f.explanation}</p>
                    {sigs.length > 0 && <div className={styles.chips}>{sigs.map(([k, v]) => <span key={k} className={styles.chip}>{k.replace(/_/g, ' ')}: {String(v)}</span>)}</div>}
                  </GlassCard>
                </motion.div>
              );
            })}
          </div>

          {r.data_coverage_note && !/^All .* real data/i.test(r.data_coverage_note) && (
            <GlassCard className={styles.note} delay={0.3}>
              <Info size={16} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: 2 }} />
              <p className="t-footnote text-tertiary" style={{ lineHeight: 1.55 }}>Coverage gaps: {r.data_coverage_note}.</p>
            </GlassCard>
          )}
        </>
      )}
    </Page>
  );
}

export default function PsychologyPage() {
  return <Suspense fallback={null}><Content /></Suspense>;
}
