'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import {
  Calculator, ChevronDown, AlertCircle, CheckCircle,
  TrendingUp, TrendingDown, Info, Ticket,
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getPortfolio, getCities, getCityVenues, modelEventDeal, DealModelResponse, DealScenario } from '@/lib/api';
import styles from './page.module.css';

function riskColor(risk: string) {
  if (risk === 'Low') return 'var(--positive)';
  if (risk === 'Medium') return 'var(--warning)';
  return 'var(--negative)';
}

function ScenarioCard({ label, scenario, active }: { label: string; scenario: DealScenario; active?: boolean }) {
  const profitable = scenario.net_profit > 0;
  return (
    <div className={`${styles.scenarioCard} ${active ? styles.scenarioCardActive : ''}`}>
      <div className={styles.scenarioHead}>
        <span className="t-callout text-primary" style={{ fontWeight: 700 }}>{label}</span>
        <span className="t-caption" style={{ color: 'var(--text-tertiary)' }}>{scenario.fill_rate_pct}% fill</span>
      </div>

      <div>
        <span className="t-caption text-tertiary">Attendance</span>
        <p className="t-headline text-primary" style={{ fontWeight: 700 }}>{scenario.attendance.toLocaleString('en-IN')}</p>
      </div>

      <div className={styles.scenarioDivider} />

      <div className={styles.scenarioLine}>
        <span className="text-tertiary">Gross revenue</span>
        <span className="text-primary" style={{ fontWeight: 600 }}>{scenario.gross_revenue_fmt}</span>
      </div>
      <div className={styles.scenarioLine}>
        <span className="text-tertiary">Artist fee</span>
        <span className="text-secondary">−{new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(scenario.artist_fee)}</span>
      </div>
      <div className={styles.scenarioLine}>
        <span className="text-tertiary">Venue + ops (est.)</span>
        <span className="text-secondary">−{new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(scenario.venue_cost + scenario.ops_cost)}</span>
      </div>

      <div className={styles.scenarioDivider} />

      <div className={styles.scenarioLine}>
        <span className="t-callout text-primary" style={{ fontWeight: 700 }}>Net profit</span>
        <span
          className="t-callout"
          style={{ fontWeight: 800, color: profitable ? 'var(--positive)' : 'var(--negative)' }}
        >
          {scenario.net_profit_fmt}
        </span>
      </div>
      {scenario.margin_pct !== null && (
        <span className="t-caption text-tertiary">{scenario.margin_pct}% margin</span>
      )}
    </div>
  );
}

const MARKETS = ['All', 'India', 'Global'] as const;
type MarketFilter = typeof MARKETS[number];

export default function DealModelerPage() {
  const [entityId, setEntityId] = useState('');
  const [city, setCity] = useState('');
  const [venueId, setVenueId] = useState('');
  const [manualCapacity, setManualCapacity] = useState('');
  const [price, setPrice] = useState('');
  const [leadDays, setLeadDays] = useState('60');
  const [market, setMarket] = useState<MarketFilter>('All');
  const [result, setResult] = useState<DealModelResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: portfolio } = useSWR('portfolio/deal-model', () => getPortfolio(), { shouldRetryOnError: false });
  const { data: citiesData } = useSWR('cities/deal-model', () => getCities(), { shouldRetryOnError: false });
  const { data: venuesData } = useSWR(
    city ? `venues/${city}` : null,
    () => getCityVenues(city),
    { shouldRetryOnError: false }
  );

  const allEntities = portfolio?.portfolio ?? [];
  const indiaCount = allEntities.filter(e => !e.is_international).length;
  const globalCount = allEntities.filter(e => e.is_international).length;
  const entities = allEntities.filter(e => {
    if (market === 'India') return !e.is_international;
    if (market === 'Global') return e.is_international;
    return true;
  });
  const cities = citiesData?.cities ?? [];
  const venues = (venuesData?.venues ?? []).filter(
    (v): v is typeof v & { id: string } => v.id !== null
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!entityId || !city || !price) {
      setError('Select an artist, city, and ticket price before running the simulation.');
      return;
    }
    if (!venueId && !manualCapacity) {
      setError('Select a venue, or enter a venue capacity manually.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await modelEventDeal({
        entity_id: entityId,
        city,
        venue_id: venueId || undefined,
        venue_capacity: venueId ? undefined : Number(manualCapacity),
        ticket_price: Number(price),
        lead_days: Number(leadDays) || 60,
      });
      setResult(res);
    } catch (err: any) {
      setError(err.message ?? 'Failed to model this deal. Ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Event Deal Modeler" subtitle="Full P&L simulation before you book — artist fee, venue, and 3 fill-rate scenarios" />

      <div className={styles.page}>
        <GlassCard className={styles.formCard} delay={0.04}>
          <div className={styles.formHeader}>
            <Calculator size={18} color="var(--accent)" />
            <div>
              <h2 className="t-headline text-primary">Configure the Deal</h2>
              <p className="t-footnote text-tertiary">Pick the artist, city, venue, and your proposed ticket price</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className={styles.form}>
            {/* Market toggle */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {MARKETS.map(m => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setMarket(m); setEntityId(''); }}
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
                <label className={styles.label} htmlFor="deal-entity">Artist / Act</label>
                <div className={styles.selectWrap}>
                  <select id="deal-entity" className={`input ${styles.select}`} value={entityId} onChange={e => setEntityId(e.target.value)} required>
                    <option value="">Select artist...</option>
                    {entities.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
                {entities.length === 0 && (
                  <p className="t-caption text-tertiary" style={{ marginTop: 4 }}>
                    {allEntities.length === 0 ? 'Backend offline — start FastAPI to load artists' : `No ${market} artists match`}
                  </p>
                )}
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="deal-city">City</label>
                <div className={styles.selectWrap}>
                  <select
                    id="deal-city"
                    className={`input ${styles.select}`}
                    value={city}
                    onChange={e => { setCity(e.target.value); setVenueId(''); }}
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
                <label className={styles.label} htmlFor="deal-venue">Venue</label>
                <div className={styles.selectWrap}>
                  <select
                    id="deal-venue"
                    className={`input ${styles.select}`}
                    value={venueId}
                    onChange={e => setVenueId(e.target.value)}
                    disabled={!city || venues.length === 0}
                  >
                    <option value="">{!city ? 'Select a city first' : venues.length === 0 ? 'No venues on file — enter capacity below' : 'Select venue...'}</option>
                    {venues.map(v => (
                      <option key={v.id} value={v.id}>{v.name} ({v.capacity?.toLocaleString('en-IN') ?? '—'} cap)</option>
                    ))}
                  </select>
                  <ChevronDown size={14} className={styles.selectIcon} />
                </div>
              </div>

              {!venueId && (
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="deal-capacity">Venue Capacity (manual)</label>
                  <input
                    id="deal-capacity"
                    className="input"
                    type="number"
                    min={100}
                    max={100000}
                    placeholder="e.g. 5000"
                    value={manualCapacity}
                    onChange={e => setManualCapacity(e.target.value)}
                    required={!venueId}
                  />
                </div>
              )}

              <div className={styles.field}>
                <label className={styles.label} htmlFor="deal-price">Ticket Price (₹)</label>
                <input
                  id="deal-price"
                  className="input"
                  type="number"
                  min={100}
                  max={50000}
                  placeholder="e.g. 3500"
                  value={price}
                  onChange={e => setPrice(e.target.value)}
                  required
                />
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="deal-lead-days">Lead Time (days until event)</label>
                <input
                  id="deal-lead-days"
                  className="input"
                  type="number"
                  min={1}
                  max={730}
                  value={leadDays}
                  onChange={e => setLeadDays(e.target.value)}
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
              {loading ? 'Modeling deal...' : 'Run P&L Simulation'}
            </button>
          </form>
        </GlassCard>

        {result && (
          <motion.div className={styles.resultWrap} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            {/* Hero summary */}
            <GlassCard className={styles.heroCard} delay={0}>
              <div className={styles.heroTop}>
                <div>
                  <p className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem', marginBottom: 6 }}>
                    {result.entity.name} · {result.venue.name ?? `${result.venue.capacity.toLocaleString('en-IN')} cap venue`} · {result.venue.city}
                  </p>
                  <h2 className="t-title2 text-primary" style={{ fontWeight: 800 }}>
                    Expected net: {result.scenarios.expected.net_profit_fmt}
                  </h2>
                </div>
                <div className={styles.riskBadge} style={{
                  color: riskColor(result.risk_level),
                  borderColor: riskColor(result.risk_level) + '50',
                  background: riskColor(result.risk_level) + '18',
                }}>
                  {result.risk_level === 'Low' ? <CheckCircle size={15} /> : <AlertCircle size={15} />}
                  {result.risk_level} Risk
                </div>
              </div>

              <div className={styles.metricsRow}>
                <div className={styles.metricBox}>
                  <span className="t-caption text-tertiary">Predicted Fill Rate</span>
                  <span className="t-headline text-primary" style={{ fontWeight: 700 }}>{result.prediction.predicted_fill_rate_pct}%</span>
                  <span className="t-caption text-tertiary">
                    {result.prediction.model === 'ml_gbr' ? `ML model · ${result.prediction.confidence_pct}% confidence` : 'Rule-based fallback'}
                    {result.prediction.model_data_source === 'synthetic' && ' · trained on synthetic data'}
                  </span>
                </div>
                <div className={styles.metricBox}>
                  <span className="t-caption text-tertiary">Artist Fee</span>
                  <span className="t-headline text-primary" style={{ fontWeight: 700 }}>{result.artist_fee.amount_fmt}</span>
                  <span className="t-caption text-tertiary">{result.artist_fee.source === 'real' ? 'From booking price range' : result.artist_fee.source}</span>
                </div>
                <div className={styles.metricBox}>
                  <span className="t-caption text-tertiary">Break-Even</span>
                  <span className="t-headline text-primary" style={{ fontWeight: 700 }}>
                    {result.break_even.tickets?.toLocaleString('en-IN') ?? '—'} tickets
                  </span>
                  <span className="t-caption" style={{ color: result.break_even.achievable ? 'var(--positive)' : 'var(--negative)' }}>
                    {result.break_even.achievable
                      ? `${result.break_even.fill_rate_pct}% fill — achievable`
                      : `${result.break_even.fill_rate_pct}% fill — exceeds venue capacity`}
                  </span>
                </div>
                <div className={styles.metricBox}>
                  <span className="t-caption text-tertiary">Composite Score</span>
                  <span className="t-headline text-primary" style={{ fontWeight: 700 }}>{result.entity.composite_score}/100</span>
                  <span className="t-caption text-tertiary">{result.entity.has_live_metrics ? 'Live metrics' : 'No metrics yet'}</span>
                </div>
              </div>
            </GlassCard>

            {/* 3 scenarios */}
            <div className={styles.scenarioGrid}>
              <ScenarioCard label="Conservative" scenario={result.scenarios.conservative} />
              <ScenarioCard label="Expected" scenario={result.scenarios.expected} active />
              <ScenarioCard label="Optimistic" scenario={result.scenarios.optimistic} />
            </div>

            {/* PredictHQ market context — real external cross-check, not fabricated */}
            {result.market_context?.predicthq?.comparable_events_found > 0 && (
              <GlassCard style={{ padding: 18 }} delay={0.12}>
                <div className={styles.noteBox}>
                  <TrendingUp size={15} color="var(--accent)" style={{ flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <p className="t-callout text-primary" style={{ fontWeight: 700, marginBottom: 4 }}>
                      Market Context — PredictHQ
                    </p>
                    <p className="t-caption text-tertiary" style={{ lineHeight: 1.6 }}>
                      {result.market_context.predicthq.comparable_events_found} real comparable event(s) found in this date window
                      {result.market_context.predicthq.avg_rank != null && ` · avg significance rank ${result.market_context.predicthq.avg_rank}/100`}
                      {result.market_context.predicthq.avg_predicted_attendance != null && ` · avg predicted attendance ${result.market_context.predicthq.avg_predicted_attendance.toLocaleString('en-IN')}`}
                    </p>
                    <p className="t-caption text-tertiary" style={{ lineHeight: 1.6, marginTop: 4, opacity: 0.75 }}>
                      {result.market_context.predicthq.source}
                    </p>
                  </div>
                </div>
              </GlassCard>
            )}

            {/* Cost model disclosure */}
            <GlassCard style={{ padding: 18 }} delay={0.1}>
              <div className={styles.noteBox}>
                <Info size={15} color="var(--text-tertiary)" style={{ flexShrink: 0, marginTop: 1 }} />
                <p className="t-caption text-tertiary" style={{ lineHeight: 1.6 }}>{result.cost_model_note}</p>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {!result && !loading && (
          <GlassCard className={styles.placeholder} delay={0.1}>
            <Ticket size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Configure a deal above to see the P&L simulation</p>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
