'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MapPin, Music2, TrendingUp, Users, Utensils,
  ChevronDown, Info, Zap, ChevronRight
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getCities, getCityIntelligence } from '@/lib/api';
import styles from './page.module.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreColor(s: number | null) {
  if (!s) return 'var(--text-tertiary)';
  if (s >= 70) return 'var(--positive)';
  if (s >= 45) return 'var(--accent)';
  return 'var(--warning)';
}

// ── Static venue tiers (seeded — realistic Zomato District venues) ────────────
// These are pulled from the cities intelligence endpoint; shown as placeholder when city not selected
const VENUE_TIERS = [
  { label: 'Intimate', capacity: '2,000–5,000', icon: '■', desc: 'Clubs, warehouses, rooftops' },
  { label: 'Mid-size', capacity: '5,000–15,000', icon: '■', desc: 'Amphitheatres, arenas' },
  { label: 'Stadium',  capacity: '15,000–80,000', icon: '■', desc: 'Grounds, racecourses, stadiums' },
];

// ── City card ─────────────────────────────────────────────────────────────────
function CityCard({ city, selected, onSelect }: {
  city: any; selected: boolean; onSelect: () => void;
}) {
  const mScore = city.music_score ?? city.market_scores?.music ?? null;
  const nScore = city.nightlife_score ?? city.market_scores?.nightlife ?? null;

  return (
    <motion.div
      className={`${styles.cityCard} ${selected ? styles.cityCardActive : ''}`}
      onClick={onSelect}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <div className={styles.cityCardTop}>
        <div>
          <span className="t-callout text-primary" style={{ fontWeight: 700 }}>{city.name}</span>
          <span className="t-caption text-tertiary" style={{ display: 'block', marginTop: 2 }}>
            Tier {city.tier ?? city.district_tier ?? '?'}
            {city.active_on_district ? ' · Active' : ' · Expansion target'}
          </span>
        </div>
        <div className={styles.cityScores}>
          {mScore != null && (
            <span style={{ fontSize: '1.1rem', fontWeight: 800, color: scoreColor(mScore), letterSpacing: '-0.04em' }}>
              {mScore}
            </span>
          )}
        </div>
      </div>
      <div className={styles.cityBars}>
        <div className={styles.cityBarRow}>
          <span className="t-caption text-tertiary" style={{ width: 48 }}>Music</span>
          <div className={styles.barTrack}>
            <motion.div
              className={styles.barFill}
              style={{ background: scoreColor(mScore) }}
              initial={{ width: 0 }}
              animate={{ width: `${mScore ?? 0}%` }}
              transition={{ duration: 0.65, ease: [0.25, 0.46, 0.45, 0.94] }}
            />
          </div>
          <span className="t-caption" style={{ color: scoreColor(mScore), width: 24, textAlign: 'right' }}>{mScore ?? '—'}</span>
        </div>
        {nScore != null && (
          <div className={styles.cityBarRow}>
            <span className="t-caption text-tertiary" style={{ width: 48 }}>Night</span>
            <div className={styles.barTrack}>
              <motion.div
                className={styles.barFill}
                style={{ background: scoreColor(nScore) }}
                initial={{ width: 0 }}
                animate={{ width: `${nScore}%` }}
                transition={{ duration: 0.65, delay: 0.08, ease: [0.25, 0.46, 0.45, 0.94] }}
              />
            </div>
            <span className="t-caption" style={{ color: scoreColor(nScore), width: 24, textAlign: 'right' }}>{nScore}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ── City detail panel ─────────────────────────────────────────────────────────
function CityDetail({ cityName }: { cityName: string }) {
  const { data, isLoading } = useSWR(
    `city-intel-${cityName}`,
    () => getCityIntelligence(cityName),
    { shouldRetryOnError: false }
  );

  const intel = data?.intelligence ?? {};
  const cityData = data?.city ?? {};

  return (
    <div className={styles.detail}>
      <div className={styles.detailHeader}>
        <MapPin size={18} color="var(--accent)" />
        <div>
          <h2 className="t-title2 text-primary">{cityName}</h2>
          <p className="t-footnote text-tertiary">Market Intelligence Report</p>
        </div>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {[120, 80, 200, 140].map((h, i) => (
            <div key={i} className="skeleton" style={{ height: h, borderRadius: 14 }} />
          ))}
        </div>
      ) : (
        <>
          {/* Market scores */}
          <GlassCard className={styles.intelCard} delay={0}>
            <h3 className="t-headline text-primary" style={{ marginBottom: 14 }}>Market Scores</h3>
            <div className={styles.intelGrid}>
              {[
                { label: 'Music demand', value: intel.music_score ?? cityData.music_score, max: 100 },
                { label: 'Nightlife',    value: intel.nightlife_score ?? cityData.nightlife_score, max: 100 },
                { label: 'Competitor events', value: intel.competitor_events, max: 50 },
                { label: 'Market gaps', value: intel.market_gaps, max: 10 },
              ].map(({ label, value, max }) => (
                <div key={label} className={styles.intelStat}>
                  <span className="t-label text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.6875rem' }}>{label}</span>
                  <span style={{ fontSize: '1.5rem', fontWeight: 800, letterSpacing: '-0.04em', color: scoreColor(typeof value === 'number' ? Math.round((value / max) * 100) : null) }}>
                    {value ?? '—'}
                  </span>
                </div>
              ))}
            </div>
          </GlassCard>

          {/* Venue selector */}
          <GlassCard className={styles.intelCard} delay={0.06}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Music2 size={14} color="var(--accent)" />
              <h3 className="t-headline text-primary">Recommended Venues</h3>
            </div>
            {(intel.top_venues ?? []).length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {intel.top_venues.map((v: any, i: number) => (
                  <motion.div
                    key={i}
                    className={styles.venueRow}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.08 + i * 0.05 }}
                  >
                    <div className={styles.venueRank}>{i + 1}</div>
                    <div style={{ flex: 1 }}>
                      <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{v.name ?? `Venue ${i + 1}`}</p>
                      <p className="t-caption text-tertiary">
                        {v.capacity ? `${v.capacity.toLocaleString('en-IN')} capacity` : 'Capacity TBC'}
                        {v.type ? ` · ${v.type}` : ''}
                      </p>
                    </div>
                    {v.fill_rate_avg != null && (
                      <span className="t-callout" style={{ fontWeight: 700, color: scoreColor(v.fill_rate_avg) }}>
                        {v.fill_rate_avg}% fill
                      </span>
                    )}
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className={styles.emptyIntel}>
                <p className="t-callout text-tertiary">
                  No venue data yet. Seed venues with the venue seeder script, or the intelligence worker will populate this from Ticketmaster event locations.
                </p>
                <div className={styles.venueTiers}>
                  {VENUE_TIERS.map(t => (
                    <div key={t.label} className={styles.venueTierCard}>
                      <span className="t-headline text-primary" style={{ fontWeight: 800 }}>{t.label}</span>
                      <span className="t-caption text-tertiary">{t.capacity}</span>
                      <span className="t-caption text-tertiary">{t.desc}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </GlassCard>

          {/* Restaurant / Nightlife Partnership Engine */}
          <GlassCard className={styles.intelCard} delay={0.12}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Utensils size={14} color="var(--positive)" />
              <h3 className="t-headline text-primary">Dining &amp; Nightlife Partnership Candidates</h3>
            </div>
            <p className="t-footnote text-tertiary" style={{ marginBottom: 14 }}>
              Real venue listings in this city (Foursquare + OpenStreetMap) — potential partnership
              targets for cross-promotion, no live offer or partnership program exists yet
            </p>

            {intel.venue_counts_by_type && (
              <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
                {(['restaurant', 'cafe', 'bar', 'nightclub'] as const).map(vt => (
                  <div
                    key={vt}
                    style={{
                      padding: '4px 12px', borderRadius: 999, fontSize: '0.75rem', fontWeight: 600,
                      background: 'var(--glass-fill)', border: '1px solid var(--glass-border)',
                      color: (intel.venue_counts_by_type[vt] ?? 0) > 0 ? 'var(--text-primary)' : 'var(--text-tertiary)',
                    }}
                  >
                    {vt.charAt(0).toUpperCase() + vt.slice(1)}s: {intel.venue_counts_by_type[vt] ?? 0}
                  </div>
                ))}
              </div>
            )}

            {(intel.restaurant_partnerships ?? []).length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {intel.restaurant_partnerships.map((r: any, i: number) => (
                  <motion.div
                    key={i}
                    className={styles.restaurantRow}
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.12 + i * 0.04 }}
                  >
                    <div className={styles.restAvatar}>{(r.name ?? 'R').charAt(0)}</div>
                    <div style={{ flex: 1 }}>
                      <p className="t-callout text-primary" style={{ fontWeight: 600 }}>{r.name ?? `Venue ${i + 1}`}</p>
                      <p className="t-caption text-tertiary">
                        {r.venue_type ? `${r.venue_type.charAt(0).toUpperCase()}${r.venue_type.slice(1)} · ` : ''}
                        {r.cuisine ?? 'Not tagged by source'}
                      </p>
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className={styles.emptyIntel}>
                <Utensils size={20} color="var(--text-tertiary)" strokeWidth={1.5} />
                <p className="t-callout text-tertiary" style={{ marginTop: 8, textAlign: 'center', lineHeight: 1.6 }}>
                  No venue data synced for this city yet — restaurant_sync.py runs daily across the
                  12 tracked cities (Foursquare Places API + OpenStreetMap).
                </p>
              </div>
            )}
          </GlassCard>

          {/* AI recommendation */}
          {intel.recommendation && (
            <GlassCard className={styles.intelCard} delay={0.18} style={{ background: 'var(--accent-dim)', borderColor: 'rgba(10,132,255,0.2)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <Zap size={14} color="var(--accent)" style={{ flexShrink: 0, marginTop: 2 }} />
                <div>
                  <p className="t-headline text-primary" style={{ marginBottom: 4 }}>AI Recommendation</p>
                  <p className="t-callout text-secondary" style={{ lineHeight: 1.7 }}>{intel.recommendation}</p>
                </div>
              </div>
            </GlassCard>
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// City Markets Page
// ═══════════════════════════════════════════════════════════════════════════════

export default function MarketsPage() {
  const [selectedCity, setSelectedCity] = useState<string | null>(null);

  const { data: citiesData, isLoading } = useSWR(
    'cities/markets', () => getCities(),
    { refreshInterval: 180000, shouldRetryOnError: false }
  );

  const cities = citiesData?.cities ?? [];

  return (
    <div className={styles.page}>
      <Topbar title="City Markets" subtitle="Venue selector, demand analysis, and restaurant partnership engine" />

      <div className={styles.layout}>
        {/* ── City list ── */}
        <div className={styles.cityPane}>
          <div className={styles.cityPaneHeader}>
            <h2 className="t-headline text-primary">Markets</h2>
            <span className="t-caption text-tertiary">{cities.length} cities tracked</span>
          </div>

          {isLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '8px 0' }}>
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="skeleton" style={{ height: 96, borderRadius: 14 }} />
              ))}
            </div>
          ) : cities.length === 0 ? (
            <div className={styles.emptyCity}>
              <MapPin size={24} color="var(--text-tertiary)" strokeWidth={1.5} />
              <p className="t-callout text-tertiary" style={{ marginTop: 10, textAlign: 'center' }}>
                No cities found. Run the seed_cities.py script to populate city data.
              </p>
            </div>
          ) : (
            <div className={styles.cityList}>
              {cities.map(c => (
                <CityCard
                  key={c.id ?? c.name}
                  city={c}
                  selected={selectedCity === c.name}
                  onSelect={() => setSelectedCity(c.name)}
                />
              ))}
            </div>
          )}
        </div>

        {/* ── Detail pane ── */}
        <div className={styles.detailPane}>
          <AnimatePresence mode="wait">
            {selectedCity ? (
              <motion.div
                key={selectedCity}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
                style={{ height: '100%' }}
              >
                <CityDetail cityName={selectedCity} />
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                className={styles.detailEmpty}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                <MapPin size={40} color="var(--text-tertiary)" strokeWidth={1.5} />
                <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Select a market</p>
                <p className="t-callout text-tertiary" style={{ maxWidth: 240, textAlign: 'center', lineHeight: 1.65, marginTop: 6 }}>
                  Click any city to view demand scores, venue recommendations, and the restaurant partnership engine.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
