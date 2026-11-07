'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { AnimatePresence, motion } from 'framer-motion';
import { Lock, TrendingUp, Loader2 } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/States';
import { EntityPicker, CityPicker, FormGroup, FormRow, FormHint } from '@/components/intel/Pickers';
import { CountUp } from '@/components/intel/CountUp';
import { Ring } from '@/components/intel/Ring';
import { getCityVenues, getMe, modelEventDeal, type DealModelResponse } from '@/lib/api';
import { inr, inrCompact, num } from '@/lib/format';
import styles from './page.module.css';

const ALLOWED = ['executive', 'analyst', 'booker'];
const riskStyle = (_r: string) => ({ color: 'var(--text-secondary)' });
const riskDot = (r: string) => r === 'Low' ? 'var(--positive)' : r === 'Medium' ? 'var(--warning)' : 'var(--negative)';

function Tip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-card" style={{ padding: '10px 12px', fontSize: '.8125rem', minWidth: 150 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      {payload.map(p => <div key={p.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 14 }}><span style={{ color: p.color }}>{p.name}</span><span className="tnum">{inrCompact(p.value)}</span></div>)}
    </div>
  );
}

export default function DealModelerPage() {
  const [entityId, setEntityId] = useState('');
  const [city, setCity] = useState('');
  const [venueId, setVenueId] = useState('');
  const [capacity, setCapacity] = useState('');
  const [price, setPrice] = useState('');
  const [lead, setLead] = useState('60');
  const [res, setRes] = useState<DealModelResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const { data: me } = useSWR('auth/me', getMe);
  const roleBlocked = forbidden || (me ? !ALLOWED.includes(me.role?.toLowerCase()) : false);
  const { data: venuesData } = useSWR(city ? `venues/${city}` : null, () => getCityVenues(city));
  const venues = useMemo(() => (venuesData?.venues ?? []).filter((v): v is typeof v & { id: string } => !!v.id), [venuesData]);
  const venue = venues.find(v => v.id === venueId);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const p = Number(price), cap = Number(capacity), ld = Number(lead);
    if (!entityId) return setErr('Choose an artist to model.');
    if (!city) return setErr('Choose a city.');
    if (!p || p < 100 || p > 50000) return setErr('Ticket price must be between ₹100 and ₹50,000.');
    if (!venueId && (!cap || cap < 100 || cap > 100000)) return setErr('Pick a venue, or enter a capacity between 100 and 1,00,000.');
    if (!ld || ld < 1 || ld > 730) return setErr('Lead time must be between 1 and 730 days.');
    setBusy(true);
    try {
      setRes(await modelEventDeal({ entity_id: entityId, city, venue_id: venueId || undefined, venue_capacity: venueId ? undefined : cap, ticket_price: p, lead_days: ld }));
    } catch (x) {
      const m = x instanceof Error ? x.message : '';
      if (/API 403/.test(m)) setForbidden(true);
      else if (/API 404/.test(m)) setErr('This artist or venue could not be found. Try another selection.');
      else if (/API 4\d\d/.test(m)) setErr('Those inputs were rejected by the model. Check the values and try again.');
      else setErr('The simulation service is unavailable right now. Please retry in a moment.');
    } finally { setBusy(false); }
  }

  const chartData = res ? (['conservative', 'expected', 'optimistic'] as const).map(k => ({
    name: k[0].toUpperCase() + k.slice(1), Revenue: res.scenarios[k].gross_revenue, Cost: res.scenarios[k].total_cost, Profit: res.scenarios[k].net_profit,
  })) : [];
  const ex = res?.scenarios.expected;
  const be = res?.break_even;
  const pred = res?.prediction.predicted_fill_rate_pct ?? 0;
  const beFill = be?.fill_rate_pct ?? null;

  const tone = (n: number) => (n >= 0 ? 'var(--positive)' : 'var(--negative)');
  const costParts = ex ? [['Artist', ex.artist_fee, .85], ['Venue', ex.venue_cost, .5], ['Operations', ex.ops_cost, .22]] as const : [];
  const costTotal = ex?.total_cost || 1;

  return (
    <Page title="Deal Modeler" subtitle="Simulate revenue, cost and break-even before you book">
      <div className={styles.layout}>
        <form className={styles.form} onSubmit={submit} noValidate>
          {roleBlocked && (
            <div className={styles.lock} role="status">
              <Lock size={16} />
              <span><b>Booking roles only.</b> The deal modeler is available to Executive, Analyst and Booker accounts{me ? <>; you’re signed in as <b>{me.role}</b></> : ''}. Ask an admin to change your role.</span>
            </div>
          )}
          <FormGroup title="The act">
            <FormRow label="Artist" htmlFor="m-artist"><EntityPicker id="m-artist" value={entityId} onChange={id => setEntityId(id)} placeholder="Choose" /></FormRow>
            <FormRow label="City" htmlFor="m-city"><CityPicker id="m-city" value={city} onChange={c => { setCity(c); setVenueId(''); }} /></FormRow>
            <FormRow label="Venue" htmlFor="m-venue">
              <select id="m-venue" className="input" value={venueId} onChange={e => setVenueId(e.target.value)} disabled={!city || venues.length === 0}>
                <option value="">{!city ? 'Pick a city first' : venues.length ? 'Enter capacity instead' : venuesData ? 'None on file' : 'Loading…'}</option>
                {venues.map(v => <option key={v.id} value={v.id}>{v.name} · {num(v.capacity)}</option>)}
              </select>
            </FormRow>
            {!venueId && <FormRow label="Capacity" htmlFor="m-cap"><input id="m-cap" className="input tnum" inputMode="numeric" placeholder="e.g. 5,000" value={capacity} onChange={e => setCapacity(e.target.value.replace(/\D/g, ''))} /></FormRow>}
          </FormGroup>
          <FormGroup title="The deal">
            <FormRow label="Ticket price" htmlFor="m-price"><span style={{ color: 'var(--text-secondary)', fontWeight: 600, width: 'auto' }}>₹</span><input id="m-price" className="input tnum" style={{ width: '7ch', flex: '0 0 auto', textAlign: 'left' }} inputMode="numeric" placeholder="1,500" value={price} onChange={e => setPrice(e.target.value.replace(/\D/g, ''))} /></FormRow>
            <FormRow label="Lead time" htmlFor="m-lead"><input id="m-lead" className="input tnum" style={{ width: '4ch', flex: '0 0 auto', textAlign: 'left' }} inputMode="numeric" value={lead} onChange={e => setLead(e.target.value.replace(/\D/g, ''))} /><span style={{ color: 'var(--text-secondary)', width: 'auto', marginLeft: 6 }}>days</span></FormRow>
          </FormGroup>
          {err && <div className={styles.err} role="alert">{err}</div>}
          <button type="submit" className="btn btn-primary" disabled={busy || roleBlocked} style={{ minHeight: 50, fontSize: '1rem' }}>
            {busy ? <><Loader2 size={16} className="spin" /> Simulating…</> : 'Run simulation'}
          </button>
        </form>

        <div className={styles.results}>
          {busy && !res ? (
            <div className={styles.bento}><Skeleton height={230} radius={26} className={styles.s8} /><Skeleton height={230} radius={26} className={styles.s4} /><Skeleton height={280} radius={26} className={styles.s12} /></div>
          ) : !res ? (
            <GlassCard className={styles.empty}>
              <EmptyState icon={<TrendingUp size={36} strokeWidth={1.4} />} title="Your P&L appears here" message="Choose an artist, a city and a ticket price to see predicted fill, profit and break-even in ₹ lakh and crore." />
            </GlassCard>
          ) : (
            <motion.div key={res.entity.id + res.inputs.ticket_price + res.venue.capacity} className={styles.bento} style={{ opacity: busy ? .55 : 1 }} initial={{ opacity: 0, y: 14 }} animate={{ opacity: busy ? .55 : 1, y: 0 }} transition={{ type: 'spring', stiffness: 220, damping: 26 }}>
              <GlassCard className={`${styles.hero} ${styles.s8}`}>
                <div className={styles.heroTop}>
                  <h2 className={styles.title}>{res.entity.name} at {res.venue.name ?? res.venue.city}</h2>
                  <span className={styles.risk} style={riskStyle(res.risk_level)}><i className={styles.dot} style={{ background: riskDot(res.risk_level), marginRight: 6, alignSelf: 'center' }} />{res.risk_level} risk</span>
                </div>
                <div className={styles.big} style={{ color: tone(ex?.net_profit ?? 0) }}>{ex ? <CountUp value={ex.net_profit} format={v => inrCompact(v)} /> : '—'}</div>
                <div className={styles.bigSub}>expected net profit · {ex?.margin_pct != null ? `${ex.margin_pct}% margin` : '—'}</div>
                <div className={styles.heroStats}>
                  <div><b>{inrCompact(ex?.gross_revenue)}</b><span>revenue</span></div>
                  <div><b>{inrCompact(ex?.total_cost)}</b><span>total cost</span></div>
                  <div><b>{num(ex?.attendance)}</b><span>of {num(res.venue.capacity)} seats</span></div>
                </div>
              </GlassCard>

              <GlassCard className={`${styles.ringCard} ${styles.s4}`} delay={.05}>
                <Ring value={pred} tick={beFill} size={148} stroke={15} >
                  <div><div className={styles.ringNum}>{pred}<small>%</small></div><div className={styles.ringLbl}>Predicted fill</div></div>
                </Ring>
                <p className={styles.ringNote}>{be?.achievable && be.tickets != null ? <>Break-even at <b>{beFill}%</b> · {num(be.tickets)} tickets</> : 'Break-even not reachable at this price'}</p>
              </GlassCard>

              <GlassCard className={`${styles.pad} ${styles.s7}`} delay={.08}>
                <div className={styles.head}><h2 className={styles.title}>Three scenarios</h2><span className="t-footnote text-tertiary">at {inr(res.inputs.ticket_price)} per ticket</span></div>
                <div className={styles.chart}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 4, right: 4, left: -6, bottom: 0 }} barGap={4}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="name" axisLine={false} tickLine={false} />
                      <YAxis tickFormatter={v => inrCompact(v)} axisLine={false} tickLine={false} width={60} />
                      <Tooltip content={<Tip />} cursor={{ fill: 'var(--fill-quaternary)' }} />
                      <Legend iconType="circle" iconSize={8} />
                      <Bar dataKey="Revenue" fill="var(--text-primary)" fillOpacity={.85} radius={[7, 7, 2, 2]} animationDuration={700} />
                      <Bar dataKey="Cost" fill="var(--text-tertiary)" radius={[7, 7, 2, 2]} animationDuration={700} />
                      <Bar dataKey="Profit" fill="var(--accent)" radius={[7, 7, 2, 2]} animationDuration={700} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </GlassCard>

              <GlassCard className={`${styles.pad} ${styles.s5}`} delay={.11}>
                <div className={styles.head}><h2 className={styles.title}>Where the money goes</h2></div>
                <div className={styles.stack}>{costParts.map(([l, v, c]) => <motion.i key={l} style={{ background: 'var(--text-primary)', opacity: c }} initial={{ flexGrow: 0 }} animate={{ flexGrow: v }} transition={{ type: 'spring', stiffness: 90, damping: 20 }} />)}</div>
                {costParts.map(([l, v, c]) => (
                  <div key={l} className={styles.costRow}><span><i className={styles.dot} style={{ background: 'var(--text-primary)', opacity: c }} />{l}</span><span><b className="tnum">{inrCompact(v)}</b> <small className="text-tertiary">{Math.round((v / costTotal) * 100)}%</small></span></div>
                ))}
                <p className={styles.note} style={{ marginTop: 8 }}>Artist fee {res.artist_fee.amount_fmt}{res.artist_fee.range_min != null && res.artist_fee.range_max != null ? ` (range ${inrCompact(res.artist_fee.range_min)} to ${inrCompact(res.artist_fee.range_max)})` : ''}</p>
              </GlassCard>

              <GlassCard className={`${styles.listCard} ${styles.s12}`} delay={.14}>
                {(['conservative', 'expected', 'optimistic'] as const).map(k => {
                  const s = res.scenarios[k];
                  return (
                    <div key={k} className={`${styles.srow} ${k === 'expected' ? styles.srowOn : ''}`}>
                      <div style={{ minWidth: 0 }}><b style={{ textTransform: 'capitalize' }}>{k}</b><span className="t-caption text-tertiary"> · {s.fill_rate_pct}% fill · {num(s.attendance)} tickets</span></div>
                      <span className="tnum text-secondary">{inrCompact(s.gross_revenue)}</span>
                      <b className="tnum" style={{ color: tone(s.net_profit), minWidth: 78, textAlign: 'right' }}>{inrCompact(s.net_profit)}</b>
                    </div>
                  );
                })}
              </GlassCard>
              <p className={`${styles.note} ${styles.s12}`}>
                Model {res.prediction.model}, confidence {res.prediction.confidence_pct}%{res.prediction.model_data_source ? `, ${res.prediction.model_data_source}` : ''}. {res.cost_model_note}
                {res.market_context?.predicthq?.comparable_events_found > 0 && <> PredictHQ found {res.market_context.predicthq.comparable_events_found} comparable events nearby{res.market_context.predicthq.avg_predicted_attendance != null ? ` (avg predicted attendance ${num(Math.round(res.market_context.predicthq.avg_predicted_attendance))})` : ''}.</>}
              </p>
            </motion.div>
          )}
        </div>
      </div>
    </Page>
  );
}
