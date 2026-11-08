'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { Info } from 'lucide-react';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton } from '@/components/ui/Skeleton';
import { modelProvenance } from '@/lib/provenance';
import { compact, num } from '@/lib/format';
import { getEntityScore } from '@/lib/api';
import styles from './Provenance.module.css';

/** Tiny info button that opens a Sheet. The one reusable "what is this number" affordance. */
export function InfoSheet({ title, label, children, testId }: { title: string; label?: string; children: React.ReactNode; testId?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={styles.btn} aria-label={label ?? `About: ${title}`} onClick={() => setOpen(true)} data-testid={testId}><Info size={15} strokeWidth={1.75} /></button>
      <Sheet open={open} onClose={() => setOpen(false)} title={title}><div className={styles.body}>{children}</div></Sheet>
    </>
  );
}

/** Small neutral pill, e.g. "Derived". Optionally explains itself in a Sheet. */
export function Tag({ children, title, explain, testId }: { children: React.ReactNode; title?: string; explain?: React.ReactNode; testId?: string }) {
  return (
    <span className={styles.note} data-testid={testId}>
      <span className={styles.tag}>{children}</span>
      {explain && <InfoSheet title={title ?? 'About this label'}>{explain}</InfoSheet>}
    </span>
  );
}

/** Quiet one-line model provenance note with an info Sheet. */
export function ModelNote({ provenance, testId = 'model-note' }: { provenance: string | null | undefined; testId?: string }) {
  const m = modelProvenance(provenance);
  return (
    <span className={styles.note} data-testid={testId}>
      <span>{m.label}</span>
      <InfoSheet title="How this estimate is made">
        <p>{m.detail}</p>
        <p>LiveIQ is built for Zomato District as a pitch tool. It uses public signals (Last.fm, YouTube, Wikipedia, Google Trends, news) and does not contain District sales data.</p>
      </InfoSheet>
    </span>
  );
}

type Level = 'High' | 'Medium' | 'Low';
const LEVELS: Level[] = ['Low', 'Medium', 'High'];

/**
 * Demand signal derived ONLY from public signals the API returns (composite score + search interest).
 * No fill-rate, no invented numbers: the drivers are the raw real values.
 */
export function DemandSignal({ entityId, composite, trend }: { entityId: string; composite?: number | null; trend?: number | null }) {
  const { data } = useSWR(['entity-score', entityId], () => getEntityScore(entityId));
  const s = data?.signals;
  const comp = composite ?? data?.composite_score ?? null;
  const gt = trend ?? s?.google_trend_score ?? null;
  const parts = [comp, gt].filter((x): x is number => x != null);
  if (!data && parts.length === 0) return <Skeleton height={96} radius={14} />;
  if (parts.length === 0) return <p className="t-callout text-tertiary">No public demand signals for this act yet.</p>;
  const idx = parts.reduce((a, b) => a + b, 0) / parts.length;
  const level: Level = idx >= 60 ? 'High' : idx >= 35 ? 'Medium' : 'Low';
  const drivers: [string, string][] = [];
  if (comp != null) drivers.push(['Composite score', `${Math.round(comp)}/100`]);
  if (gt != null) drivers.push(['Search interest (Google Trends)', `${Math.round(gt)}/100`]);
  if (s?.lastfm_listeners != null) drivers.push(['Last.fm listeners', compact(s.lastfm_listeners)]);
  if (s?.youtube_subscribers != null) drivers.push(['YouTube subscribers', compact(s.youtube_subscribers)]);
  if (s?.news_mentions_7d != null) drivers.push(['News mentions (7 days)', num(s.news_mentions_7d)]);
  const sources = data?.data_completeness != null ? Math.round(data.data_completeness * 4) : null;
  return (
    <div className={styles.gauge} data-testid="demand-signal">
      <div className={styles.gaugeTop}>
        <span className={styles.level} data-testid="demand-level">{level} demand</span>
        <span className={styles.note}>Public signals only
          <InfoSheet title="Demand signal">
            <p>A plain reading of how much public attention this act has right now. It averages the composite score and Google search interest, then buckets it: Low below 35, Medium 35 to 60, High above 60.</p>
            <p>It does not predict ticket sales. It never uses sales data, because LiveIQ has none.</p>
          </InfoSheet>
        </span>
      </div>
      <div className={styles.track} aria-hidden>{LEVELS.map(l => <i key={l} className={`${styles.seg} ${LEVELS.indexOf(l) <= LEVELS.indexOf(level) ? styles.segOn : ''}`} />)}</div>
      <div className={styles.scale}><span>Low</span><span>Medium</span><span>High</span></div>
      <div className={styles.drivers}>{drivers.map(([k, v]) => <div key={k} className={styles.driver}><span>{k}</span><span>{v}</span></div>)}</div>
      {sources != null && sources < 4 && <p className="t-caption text-tertiary">Based on {sources} of 4 sources</p>}
    </div>
  );
}
