'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { LineChart as LineIcon, TrendingDown, TrendingUp, Minus, Hourglass } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Segmented } from '@/components/ui/Controls';
import { Field, EntityPicker } from '@/components/intel/Pickers';
import { getDemandForecast, getPortfolio, type DemandForecastResponse } from '@/lib/api';
import { dateIN } from '@/lib/format';
import styles from './page.module.css';

type Row = { date: string; history?: number; predicted?: number; band?: [number, number] };

function Tip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number | [number, number] }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const get = (k: string) => payload.find(p => p.dataKey === k)?.value;
  const h = get('history') as number | undefined, p = get('predicted') as number | undefined, b = get('band') as [number, number] | undefined;
  return (
    <div className="glass-card" style={{ padding: '10px 12px', fontSize: '.8125rem', minWidth: 150 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{dateIN(label)}</div>
      {h != null && <div className="tnum">Observed: {h.toFixed(0)}</div>}
      {p != null && <div className="tnum">Forecast: {p.toFixed(0)}</div>}
      {b && <div className="tnum text-tertiary">Range: {b[0].toFixed(0)} – {b[1].toFixed(0)}</div>}
    </div>
  );
}

function errorCopy(m: string) {
  if (/API 503/.test(m)) return 'The forecasting engine (Prophet) isn’t installed on the server, so forecasts are unavailable.';
  if (/API 404/.test(m)) return 'We couldn’t find that artist.';
  if (/API 500/.test(m)) return 'The model couldn’t fit this artist’s data. Try a different artist or horizon.';
  return 'Couldn’t reach the forecast service. Please try again.';
}

export default function ForecastPage() {
  const [entityId, setEntityId] = useState('');
  const [months, setMonths] = useState('3');

  const { data: portfolio } = useSWR('portfolio/picker', () => getPortfolio());
  const quick = useMemo(() => (portfolio?.portfolio ?? []).filter(e => !e.is_international && e.type === 'artist' && e.google_trend_score != null).slice(0, 4), [portfolio]);

  const { data, error, isLoading, isValidating, mutate } = useSWR<DemandForecastResponse>(
    entityId ? `forecast/${entityId}/${months}` : null,
    () => getDemandForecast(entityId, { months: Number(months) }),
    { shouldRetryOnError: false, revalidateOnFocus: false },
  );

  const rows: Row[] = useMemo(() => {
    if (!data) return [];
    const h: Row[] = data.history.map(p => ({ date: p.date, history: p.google_trend_score }));
    const f: Row[] = (data.forecast ?? []).map(p => ({ date: p.date, predicted: p.predicted_trend_score, band: [p.lower_bound, p.upper_bound] as [number, number] }));
    // connect the lines at the junction
    if (h.length && f.length) h[h.length - 1].predicted = h[h.length - 1].history;
    return [...h, ...f];
  }, [data]);

  const dir = data?.trend_direction;
  const dirColor = dir === 'rising' ? 'var(--positive)' : dir === 'falling' ? 'var(--negative)' : 'var(--text-secondary)';
  const DirIcon = dir === 'rising' ? TrendingUp : dir === 'falling' ? TrendingDown : Minus;
  const last = data?.forecast?.[data.forecast.length - 1];
  const hasForecast = data?.status === 'ok' && !!data.forecast?.length;
  const loading = !!entityId && isLoading && !data;

  return (
    <Page title="Demand Forecast" subtitle="Where an artist’s search interest is heading next">
      <div className={styles.layout}>
        <GlassCard className={styles.controls}>
          <Field label="Artist or act" htmlFor="f-ent"><EntityPicker id="f-ent" value={entityId} onChange={id => setEntityId(id)} /></Field>
          <Field label="Horizon">
            <Segmented ariaLabel="Forecast horizon" value={months} onChange={setMonths} options={[{ value: '1', label: '1 mo' }, { value: '3', label: '3 mo' }, { value: '6', label: '6 mo' }, { value: '12', label: '12 mo' }]} />
          </Field>
          {quick.length > 0 && (
            <div className={styles.chips} aria-label="Quick picks">
              <span className="t-caption text-tertiary">Quick picks</span>
              {quick.map(e => <button key={e.id} type="button" className="chip" aria-pressed={entityId === e.id} onClick={() => setEntityId(e.id)}>{e.name}</button>)}
            </div>
          )}
        </GlassCard>

        {!entityId ? (
          <GlassCard><EmptyState icon={<LineIcon size={36} strokeWidth={1.4} />} title="Pick an artist to forecast" message="We project Google Trends interest using Prophet, with an 80% confidence band." /></GlassCard>
        ) : loading ? (
          <>
            <div className={styles.tiles}>{[0, 1, 2, 3].map(i => <Skeleton key={i} height={104} radius={22} />)}</div>
            <Skeleton height={380} radius={22} />
          </>
        ) : error && !data ? (
          <GlassCard><ErrorState message={errorCopy(error instanceof Error ? error.message : '')} onRetry={() => mutate()} /></GlassCard>
        ) : data ? (
          <div className={styles.bento} style={{ opacity: isValidating ? .6 : 1, transition: 'opacity .2s' }}>
            <GlassCard className={`${styles.hero} ${styles.s4}`}>
              <span className={styles.eyebrow}>{data.entity.name}</span>
              {hasForecast && last ? (
                <>
                  <div className={styles.big}>{last.predicted_trend_score.toFixed(0)}</div>
                  <div className={styles.bigSub}>projected interest in {months} month{months === '1' ? '' : 's'}</div>
                  <div className={styles.trendLine} style={{ color: dirColor }}><DirIcon size={16} /> <span>{dir}</span><span className="text-tertiary" style={{ textTransform: 'none', fontWeight: 400 }}> · range {last.lower_bound.toFixed(0)} to {last.upper_bound.toFixed(0)}</span></div>
                </>
              ) : (
                <>
                  <div className={styles.big} style={{ color: 'var(--text-tertiary)' }}>—</div>
                  <div className={styles.bigSub}>No forecast yet</div>
                </>
              )}
              <div className={styles.heroStats}>
                <div><b>{data.history_points}</b><span>data points</span></div>
                <div><b>{data.history_span_days}</b><span>days covered</span></div>
                <div><b>{data.history.length ? Math.round(data.history[data.history.length - 1].google_trend_score) : '—'}</b><span>latest signal</span></div>
              </div>
            </GlassCard>

            {hasForecast ? (
              <GlassCard className={`${styles.pad} ${styles.s8}`} delay={.05}>
                <div className={styles.head}>
                  <h2 className="t-headline">Search interest</h2>
                  <span className={styles.legend}><i style={{ background: 'var(--text-secondary)' }} /> Observed <i style={{ background: 'var(--accent)', marginLeft: 12 }} /> Forecast</span>
                </div>
                <div className={styles.chart}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={rows} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                      <defs><linearGradient id="band" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity={.28} /><stop offset="100%" stopColor="var(--accent)" stopOpacity={0} /></linearGradient></defs>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="date" tickFormatter={d => dateIN(d, { day: 'numeric', month: 'short' })} minTickGap={56} axisLine={false} tickLine={false} />
                      <YAxis domain={[0, 100]} ticks={[0, 50, 100]} axisLine={false} tickLine={false} width={44} />
                      <Tooltip content={<Tip />} />
                      <Area dataKey="band" stroke="none" fill="url(#band)" isAnimationActive={false} />
                      <Line dataKey="history" stroke="var(--text-secondary)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls={false} animationDuration={700} />
                      <Line dataKey="predicted" stroke="var(--accent)" strokeWidth={2} strokeDasharray="5 4" dot={false} animationDuration={900} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <p className={styles.note}>{data.methodology ?? 'Prophet forecast on weekly Google Trends readings; the shaded band is the 80% interval.'}</p>
              </GlassCard>
            ) : (
              <GlassCard className={`${styles.pad} ${styles.s8}`} delay={.05}>
                <div className={styles.center}>
                  <EmptyState icon={<Hourglass size={34} strokeWidth={1.4} />} title={`Not enough history for ${data.entity.name}`}
                    message="A forecast on a handful of readings would just be noise. Interest data is collected on a schedule; check back as it builds up." />
                  {data.minimum_required && (
                    <div className={styles.progress}>
                      {[
                        ['Data points', data.history_points, data.minimum_required.points],
                        ['Days covered', data.history_span_days, data.minimum_required.span_days],
                      ].map(([l, v, t]) => (
                        <div key={l as string} className={styles.pRow}>
                          <div><span>{l}</span><span className="tnum">{v} / {t}</span></div>
                          <div className={styles.pTrack}><div className={styles.pFill} style={{ width: `${Math.min(100, ((v as number) / (t as number)) * 100)}%` }} /></div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {rows.length > 1 && (
                  <div className={styles.chart} style={{ marginTop: 20, height: 180 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={rows} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="date" tickFormatter={d => dateIN(d, { day: 'numeric', month: 'short' })} minTickGap={48} axisLine={false} tickLine={false} />
                        <YAxis domain={[0, 100]} ticks={[0, 50, 100]} axisLine={false} tickLine={false} width={44} />
                        <Tooltip content={<Tip />} />
                        <Line dataKey="history" stroke="var(--text-secondary)" strokeWidth={2} dot={{ r: 3 }} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </GlassCard>
            )}
          </div>
        ) : null}
      </div>
    </Page>
  );
}
