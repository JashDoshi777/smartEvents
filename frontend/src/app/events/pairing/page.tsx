'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Loader2, Users2 } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Segmented } from '@/components/ui/Controls';
import { EntityPicker, CityPicker, FormGroup, FormRow, FormHint } from '@/components/intel/Pickers';
import { Ring } from '@/components/intel/Ring';
import { recommendPairs, type PairRecommendResponse } from '@/lib/api';
import { inrCompact, num } from '@/lib/format';
import styles from './page.module.css';

type Market = 'india' | 'all';

export default function PairingPage() {
  const [city, setCity] = useState('Mumbai');
  const [anchor, setAnchor] = useState('');
  const [budget, setBudget] = useState('');
  const [market, setMarket] = useState<Market>('india');
  const [res, setRes] = useState<PairRecommendResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);
  const seq = useRef(0);

  const run = useCallback(async () => {
    if (!city) return setFormErr('Choose a city to build the bill for.');
    setFormErr(null); setErr(null); setBusy(true);
    const my = ++seq.current;
    try {
      const out = await recommendPairs({ city, budget: budget ? Number(budget) : undefined, anchor_entity_id: anchor || undefined, market: market === 'india' ? 'India' : undefined, limit: 10 });
      if (my === seq.current) setRes(out);
    } catch (x) {
      if (my !== seq.current) return;
      const m = x instanceof Error ? x.message : '';
      setRes(null);
      setErr(/API 404/.test(m) ? 'That artist has no live metrics yet, so we can’t pair them. Pick another anchor.'
        : /API 400/.test(m) ? 'Not enough artists with live data to form pairings for this filter. Try “All markets”.'
        : 'Pairing service is unavailable right now. Please retry.');
    } finally { if (my === seq.current) setBusy(false); }
  }, [city, budget, anchor, market]);

  useEffect(() => { run(); /* initial suggestion run */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [top, ...rest] = res?.recommendations ?? [];
  return (
    <Page title="Artist Pairing" subtitle="Co-headliners and support acts that fill rooms together">
      <div className={styles.layout}>
        <form className={styles.form} onSubmit={e => { e.preventDefault(); run(); }}>
          <FormGroup title="Build a bill">
            <FormRow label="City" htmlFor="p-city"><CityPicker id="p-city" value={city} onChange={setCity} /></FormRow>
            <FormRow label="Anchor"><EntityPicker value={anchor} onChange={id => setAnchor(id)} placeholder="Any artist" indiaOnly={market === 'india'} types={['artist']} /></FormRow>
            <FormRow label="Budget" htmlFor="p-budget"><span style={{ color: 'var(--text-secondary)', fontWeight: 600, width: 'auto', marginRight: 4 }}>₹</span><input id="p-budget" className="input tnum" style={{ width: '10ch', flex: '0 0 auto', textAlign: 'left' }} inputMode="numeric" placeholder="No cap" value={budget} onChange={e => setBudget(e.target.value.replace(/\D/g, ''))} /></FormRow>
            <FormRow label="Market"><Segmented ariaLabel="Market" value={market} onChange={m => { setMarket(m); setAnchor(''); }} options={[{ value: 'india', label: 'India' }, { value: 'all', label: 'All' }]} /></FormRow>
          </FormGroup>
          {budget && <FormHint>Combined fee capped at {inrCompact(Number(budget))}</FormHint>}
          {formErr && <div className={styles.err} role="alert">{formErr}</div>}
          <button type="submit" className="btn btn-primary" disabled={busy} style={{ minHeight: 50, fontSize: '1rem' }}>
            {busy ? <><Loader2 size={16} className="spin" /> Finding pairs…</> : 'Find pairings'}
          </button>
        </form>

        <div className={styles.results}>
          {busy && !res ? (
            <><Skeleton height={190} radius={26} />{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} height={64} radius={18} />)}</>
          ) : err ? (
            <GlassCard><ErrorState message={err} onRetry={run} /></GlassCard>
          ) : !res ? (
            <GlassCard className={styles.empty}><EmptyState icon={<Users2 size={36} strokeWidth={1.4} />} title="No pairings yet" message="Choose a city and press Find pairings." /></GlassCard>
          ) : !top ? (
            <GlassCard className={styles.empty}><EmptyState icon={<Users2 size={36} strokeWidth={1.4} />} title="No pairs fit these filters" message="Try raising the budget, removing the anchor artist, or switching to All markets." /></GlassCard>
          ) : (
            <motion.div className={styles.results} style={{ opacity: busy ? .55 : 1 }} initial={{ opacity: 0, y: 12 }} animate={{ opacity: busy ? .55 : 1, y: 0 }} transition={{ type: 'spring', stiffness: 220, damping: 26 }}>
              <GlassCard className={styles.feature}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <span className={styles.eyebrow}>Best pairing for {res.city}</span>
                  <div className={styles.fNames}><span>{top.entity_a.name}</span><span className={styles.amp}>&amp;</span><span>{top.entity_b.name}</span></div>
                  <div className={styles.sub}>{[top.entity_a.category, top.entity_b.category].filter((c, k, a) => c && a.indexOf(c) === k).join(' · ') || '—'}</div>
                  {top.shared_genres.length > 0 && <div className={styles.genres}>{top.shared_genres.slice(0, 5).map(g => <span key={g} className={styles.genre}>{g}</span>)}</div>}
                  <div className={styles.fee}>{top.combined_booking_fee_estimate != null ? <><b>{inrCompact(top.combined_booking_fee_estimate)}</b> combined fee</> : 'Booking fee not on file'}</div>
                </div>
                <Ring value={top.similarity_score} size={112} stroke={11}><div><div className={styles.ringNum}>{Math.round(top.similarity_score)}</div><div className={styles.ringLbl}>match</div></div></Ring>
              </GlassCard>

              {rest.length > 0 && (
                <GlassCard className={styles.list}>
                  {rest.map((p, i) => (
                    <motion.div key={`${p.entity_a.id}-${p.entity_b.id}`} className={styles.prow} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 8) * .035, duration: .3 }}>
                      <span className={styles.rank}>{i + 2}</span>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className={styles.names}>{p.entity_a.name} <span className={styles.amp}>&amp;</span> {p.entity_b.name}</div>
                        <div className={styles.sub}>{p.shared_genres.slice(0, 3).join(', ') || 'No shared genre tags'}{p.combined_booking_fee_estimate != null ? ` · ${inrCompact(p.combined_booking_fee_estimate)}` : ''}</div>
                      </div>
                      <span className={styles.score}>{Math.round(p.similarity_score)}</span>
                    </motion.div>
                  ))}
                </GlassCard>
              )}
              <p className={styles.note}>{num(res.pairs_matching_genre)} genre matches from {num(res.candidates_considered)} artists{res.anchor_entity ? `, anchored on ${res.anchor_entity.name}` : ''}. {res.methodology}</p>
            </motion.div>
          )}
        </div>
      </div>
    </Page>
  );
}
