'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Brain, TrendingUp, TrendingDown } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { ChipRow } from '@/components/ui/Controls';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Skeleton } from '@/components/ui/Skeleton';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { EntityPicker } from '@/components/intel/EntityPicker';
import { Tick } from '@/components/intel/Tick';
import { useScopedPortfolio } from '@/components/intel/entity-utils';
import { getCities, getPsychology } from '@/lib/api';
import k from '@/components/intel/Kit.module.css';
import styles from './page.module.css';

const FACTOR_LABEL: Record<string, string> = {
  exposure: 'Overexposure and novelty', novelty: 'Novelty', fomo: 'FOMO and competing events', controversy_drag: 'Controversy drag',
};

// Colour only where it is a real up/down delta.
const tone = (m: number) => (m > 1.01 ? 'var(--positive)' : m < 0.99 ? 'var(--negative)' : 'var(--text-primary)');

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
  useEffect(() => {
    if (!scoped.length) return;
    const lead = scoped.find(e => e.composite_score != null)?.id ?? scoped[0].id;
    if (!entityId && !deep) setEntityId(lead);
    else if (entityId && !deep && !scoped.some(e => e.id === entityId)) setEntityId(lead);
  }, [scoped]); // eslint-disable-line react-hooks/exhaustive-deps

  const report = useSWR(entityId ? ['psychology', entityId, city] : null, () => getPsychology(entityId, city || undefined));
  const r = report.data;
  const combined = r?.combined_multiplier ?? 1;
  const pct = Math.round((combined - 1) * 100);
  const pos = Math.max(0, Math.min(100, ((combined - 0.7) / 0.6) * 100));
  const pickerList = (() => { const x = all.find(e => e.id === entityId); return x && !scoped.some(e => e.id === entityId) ? [x, ...scoped] : scoped; })();

  return (
    <Page title="Demand Psychology" subtitle="How overexposure, FOMO and controversy move demand">
      <div className={styles.layout}>
        <GlassCard style={{ padding: 20 }} delay={0.04}>
          <div className={styles.sel}>
            <EntityPicker entities={pickerList} value={entityId} onChange={setEntityId} loading={pLoading} placeholder={`Select ${isIndia ? 'an Indian' : 'a global'} act`} />
            <ChipRow value={city} onChange={setCity} options={[{ value: '', label: 'All cities' }, ...cityList.map(c => ({ value: c.name, label: c.name }))]} />
          </div>
        </GlassCard>

        {!entityId ? (
          <GlassCard delay={0.08}><EmptyState icon={<Brain size={32} strokeWidth={1.5} />} title="Select an act" message="Pick an artist, comic or team to see what is helping or hurting demand." /></GlassCard>
        ) : report.isLoading && !r ? (
          <><Skeleton height={190} radius={20} /><Skeleton height={260} radius={20} /></>
        ) : report.error && !r ? (
          <GlassCard><ErrorState message="Couldn’t compute the psychology report for this selection." onRetry={() => report.mutate()} /></GlassCard>
        ) : r && (
          <>
            <GlassCard className={styles.hero} delay={0.06}>
              <div className={styles.heroTop}>
                <div>
                  <h2 className={k.title} style={{ marginBottom: 10 }}>{r.entity_name} · {city || 'all tracked cities'}</h2>
                  <span className={`${styles.big} num-rounded`} style={{ color: tone(combined) }}><Tick value={combined} decimals={2} suffix="×" /></span>
                </div>
                <span className={styles.delta} style={{ color: pct === 0 ? undefined : tone(combined) }}>
                  {pct > 0 ? <TrendingUp size={16} strokeWidth={1.75} /> : pct < 0 ? <TrendingDown size={16} strokeWidth={1.75} /> : null}
                  {pct > 0 ? `+${pct}% demand` : pct < 0 ? `${pct}% demand` : 'No adjustment'}
                </span>
              </div>
              <div>
                <div className={styles.scale}><motion.span className={styles.mark} initial={{ left: '50%' }} animate={{ left: `${pos}%` }} transition={{ type: 'spring', stiffness: 80, damping: 15 }} /></div>
                <div className={styles.ticks}><span>0.70× suppressed</span><span>1.00×</span><span>1.30× boosted</span></div>
              </div>
              <p className="t-footnote text-secondary" style={{ lineHeight: 1.55, maxWidth: 720 }}>{combined > 1.01 ? 'Real signals are lifting expected demand for this act. Apply this multiplier to fill-rate and revenue estimates.' : combined < 0.99 ? 'Real signals are suppressing expected demand for this act. Apply this multiplier to fill-rate and revenue estimates, or reconsider timing.' : 'Not enough real signal to move demand up or down, so treat this as a neutral 1.00× multiplier on fill-rate estimates.'}</p>
            </GlassCard>

            <div>
              <p className={styles.secH}>Factors</p>
              <GlassCard className={k.group} delay={0.1}>
                {r.factors.map((f, i) => {
                  const sigs = Object.entries(f.real_signal ?? {}).filter(([, v]) => v !== null && v !== undefined);
                  return (
                    <motion.div key={f.name} className={styles.fRow} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 + i * 0.05, duration: 0.32 }}>
                      <div className={styles.fMain}>
                        <b>{FACTOR_LABEL[f.name] ?? f.name.replace(/_/g, ' ')}</b>
                        <p>{f.explanation}</p>
                        {sigs.length > 0 && <span className={styles.sigs}>{sigs.map(([key, v]) => `${key.replace(/_/g, ' ')}: ${String(v)}`).join(' · ')}</span>}
                      </div>
                      <span className={`${styles.fMult} num-rounded`} style={{ color: tone(f.multiplier) }}>{f.multiplier.toFixed(2)}×</span>
                    </motion.div>
                  );
                })}
              </GlassCard>
            </div>

            {r.data_coverage_note && !/^All .* real data/i.test(r.data_coverage_note) && <p className={styles.cover}>Coverage gaps: {r.data_coverage_note}.</p>}
          </>
        )}
      </div>
    </Page>
  );
}

export default function PsychologyPage() {
  return <Suspense fallback={null}><Content /></Suspense>;
}
