'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Download, Loader2, RefreshCw } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { useAuth } from '@/components/providers/AuthProvider';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { Ring, StackBar } from '@/components/dashboard/Ring';
import { getKPIs, getBriefing, getPortfolio, downloadExecutiveReportPdf } from '@/lib/api';
import { num, timeAgo } from '@/lib/format';
import { CountUp } from '@/components/dashboard/CountUp';
import styles from './page.module.css';

const scoreColor = (_v?: number | null) => 'var(--accent)';

export default function ExecutivePage() {
  const { isIndia } = useMarketScope();
  const { user } = useAuth();
  const toast = useToast();
  const kpis = useSWR('kpis', getKPIs, { refreshInterval: 60000 });
  const briefing = useSWR('briefing', getBriefing, { revalidateOnFocus: false });
  const portfolio = useSWR('portfolio', () => getPortfolio());
  const [exporting, setExporting] = useState(false);
  // The backend only lets executives and analysts export reports.
  const canExport = user?.role === 'executive' || user?.role === 'analyst';

  async function exportPdf() {
    setExporting(true);
    let url: string | null = null;
    try {
      const blob = await downloadExecutiveReportPdf();
      url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `liveiq-executive-report-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast('Report downloaded', 'success');
    } catch (err) {
      const m = err instanceof Error ? err.message : '';
      toast(m.includes('403') ? 'Your role can’t export reports' : m || 'Couldn’t generate the report', 'error');
    } finally {
      if (url) { const u = url; setTimeout(() => URL.revokeObjectURL(u), 4000); }
      setExporting(false);
    }
  }

  const k = kpis.data;
  const p = portfolio.data;
  const rows = (p?.portfolio ?? []).filter(e => isIndia ? !e.is_international : true).slice(0, 10);
  const top = Math.max(1, ...rows.map(r => r.composite_score ?? 0));
  const hs = p?.health_summary;
  const score = k?.entity_portfolio.avg_composite_score;

  return (
    <Page
      title="Executive suite"
      subtitle="Portfolio intelligence for leadership"
      actions={canExport ? (
        <button className="btn btn-primary" onClick={exportPdf} disabled={exporting} aria-label="Export PDF report">
          {exporting ? <Loader2 size={15} className="spin" /> : <Download size={15} />}
          {exporting ? 'Generating…' : 'Export PDF'}
        </button>
      ) : undefined}
    >
      {kpis.error && !k ? <GlassCard><ErrorState message="Couldn’t load portfolio KPIs." onRetry={() => kpis.mutate()} /></GlassCard> : (
        <div className={styles.bento}>
          <GlassCard className={`${styles.tile} ${styles.gauge}`}>
            <h2 className={styles.title}>Portfolio health</h2>
            {!k ? <Skeleton height={190} radius={22} /> : (<>
              <div style={{ display: 'flex', justifyContent: 'center', padding: '6px 0' }}>
                <Ring value={score} size={170} stroke={16} color={scoreColor(score)}>
                  <div><div className={'num-rounded'} style={{ fontSize: '3rem', fontWeight: 700, lineHeight: 1 }}>{score ?? '—'}</div><div className="t-caption text-tertiary">avg demand / 100</div></div>
                </Ring>
              </div>
              {hs && <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <StackBar parts={[{ label: 'Strong', value: hs.strong, color: 'var(--accent)' }, { label: 'Good', value: hs.good, color: 'var(--text-secondary)' }, { label: 'Needs data', value: hs.needs_data, color: 'var(--fill-tertiary)' }, { label: 'Weak', value: hs.weak, color: 'var(--text-tertiary)' }]} />
                <div className={styles.legend}>
                  {[['Strong', hs.strong, 'var(--accent)'], ['Good', hs.good, 'var(--text-secondary)'], ['Needs data', hs.needs_data, 'var(--fill-tertiary)'], ['Weak', hs.weak, 'var(--text-tertiary)']].map(([l, v, c]) => (
                    <span key={l as string} className={styles.legendRow}><span className={styles.dot} style={{ background: c as string }} /><span className="t-caption text-secondary">{l} {v}</span></span>
                  ))}
                </div>
              </div>}
            </>)}
          </GlassCard>

          <GlassCard className={`${styles.tile} ${styles.brief}`} delay={0.05}>
            <div className={styles.head}>
              <h2 className={styles.title}>Executive briefing</h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className="t-caption text-tertiary">{briefing.data ? `Generated ${timeAgo(briefing.data.generated_at)}` : ''}</span>
                <button className="btn" onClick={() => briefing.mutate()} disabled={briefing.isValidating} aria-label="Refresh briefing"><RefreshCw size={14} className={briefing.isValidating ? 'spin' : ''} /></button>
              </div>
            </div>
            {briefing.isLoading && !briefing.data ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>{[100, 92, 86, 70, 90].map((w, i) => <Skeleton key={i} height={14} width={`${w}%`} />)}</div>
            ) : briefing.error && !briefing.data ? <ErrorState message="Briefing is unavailable right now." onRetry={() => briefing.mutate()} />
              : <p className={`t-body text-secondary ${styles.briefing}`}>{briefing.data?.briefing || 'No briefing available yet.'}</p>}
          </GlassCard>

          <GlassCard className={styles.stats} delay={0.08}>
            {!k ? <Skeleton height={70} radius={14} style={{ gridColumn: '1 / -1' }} /> : <>
              <div className={styles.stat}><span className={`num-rounded ${styles.statVal}`}><CountUp value={isIndia ? k.entity_portfolio.indian : k.entity_portfolio.total_tracked} format={num as unknown as (n: number) => string} /></span><span className="t-footnote text-secondary">{isIndia ? 'Indian acts' : 'Acts tracked'} · {Math.round(k.entity_portfolio.metrics_coverage_pct)}% scored</span></div>
              <div className={styles.stat}><span className={`num-rounded ${styles.statVal}`}><CountUp value={k.entity_portfolio.international} /></span><span className="t-footnote text-secondary">International acts to book</span></div>
              <div className={styles.stat}><span className={`num-rounded ${styles.statVal}`}><CountUp value={k.city_coverage.active_on_district} /></span><span className="t-footnote text-secondary">Cities live · {num(k.city_coverage.expansion_opportunities)} to open</span></div>
            </>}
          </GlassCard>

          <GlassCard className={`${styles.tile} ${styles.rank}`} delay={0.14}>
            <h2 className={styles.title}>Top ranked acts{isIndia ? ' in India' : ''}</h2>
            {portfolio.isLoading && !p ? <SkeletonRows rows={6} /> : portfolio.error && !p ? <ErrorState onRetry={() => portfolio.mutate()} />
              : rows.length === 0 ? <EmptyState title="No ranked acts yet" message="Rankings appear once demand scores are computed." /> : (
              <div>
                {rows.map((e, i) => (
                  <motion.div key={`${e.id}-${i}`} className={styles.row} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
                    <span className={styles.avatar}>{e.name.charAt(0).toUpperCase()}</span>
                    <div className={styles.info}>
                      <span className={`t-body ${styles.ellip}`} style={{ fontWeight: 500 }}>{e.name}</span>
                      <span className={`t-footnote text-secondary ${styles.ellip}`}>{[e.category ?? e.type, e.health].filter(Boolean).join(' · ')}</span>
                    </div>
                    <div className={styles.bar}><motion.div className={styles.fill} initial={{ width: 0 }} animate={{ width: `${((e.composite_score ?? 0) / top) * 100}%` }} transition={{ duration: 0.8, delay: 0.1 + i * 0.04, ease: [0.22, 1, 0.36, 1] }} /></div>
                    <span className="num-rounded t-headline" style={{ textAlign: 'right' }}>{e.composite_score ?? '—'}</span>
                  </motion.div>
                ))}
              </div>
            )}
          </GlassCard>
        </div>
      )}
    </Page>
  );
}
