'use client';

/* eslint-disable react-hooks/set-state-in-effect -- these effects sync state from external sources (URL params, localStorage, debounced network results), which is the intended use */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { CheckCircle2, XCircle, Moon, Sun, Server, Database, HardDrive, Star, FileDown, ChevronRight, Globe2, Bell, User as UserIcon, Loader2 } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { Segmented, Switch } from '@/components/ui/Controls';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { useTheme } from '@/components/providers/ThemeProvider';
import { useAuth } from '@/components/providers/AuthProvider';
import { useMarketScope, MarketScope } from '@/components/providers/MarketScopeProvider';
import { readWatchlistOnly, writeWatchlistOnly } from '@/components/layout/NotificationBell';
import { getHealth, getWatchlist, downloadExecutiveReportPdf } from '@/lib/api';
import { num } from '@/lib/format';
import styles from './page.module.css';

const API_LABELS: Record<string, string> = {
  spotify: 'Spotify', youtube: 'YouTube', ticketmaster: 'Ticketmaster', tmdb: 'TMDB', groq: 'Groq (AI Copilot)',
  gemini: 'Gemini (fallback AI)', newsapi: 'NewsAPI', reddit: 'Reddit', lastfm: 'Last.fm', mapbox: 'Mapbox',
};
const API_NOTES: Record<string, string> = {
  spotify: 'Development-mode apps get no popularity or genre data; Last.fm is the primary signal.',
  lastfm: 'Primary music-demand signal across Indian and international acts.',
  groq: 'Powers the AI Copilot and executive briefings.',
};

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className={styles.section}>
      <h2 className={`text-secondary ${styles.sectionTitle}`}>{title}</h2>
      <div className="list-group">{children}</div>
      {note && <p className={`t-caption text-tertiary ${styles.sectionNote}`}>{note}</p>}
    </section>
  );
}

function Status({ ok, up = 'Connected', down = 'Unreachable' }: { ok: boolean; up?: string; down?: string }) {
  return <span className={styles.status} style={{ color: ok ? 'var(--positive)' : 'var(--text-tertiary)' }}>{ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}{ok ? up : down}</span>;
}

export default function SettingsPage() {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const { scope, setScope } = useMarketScope();
  const toast = useToast();
  const health = useSWR('health', getHealth, { refreshInterval: 30000 });
  const watch = useSWR('watchlist', () => getWatchlist());
  const [exporting, setExporting] = useState(false);
  const [watchOnly, setWatchOnly] = useState(false);
  useEffect(() => setWatchOnly(readWatchlistOnly()), []);
  const canExport = user?.role === 'executive' || user?.role === 'analyst';

  const h = health.data;
  const apiEntries = h ? Object.entries(h.apis_configured) : [];
  const configured = apiEntries.filter(([, v]) => v).length;

  async function exportPdf() {
    setExporting(true);
    try {
      const blob = await downloadExecutiveReportPdf();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `liveiq-executive-report-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast('Report downloaded', 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Couldn’t generate the report', 'error');
    } finally { setExporting(false); }
  }

  return (
    <Page title="Settings" subtitle="Preferences, account and system health">
      <div className={styles.wrap}>
        {user && (
          <Section title="Account">
            <div className="list-row">
              <div className={styles.iconBox}><UserIcon size={20} strokeWidth={1.6} /></div>
              <div className={styles.grow}>
                <span className="t-callout" style={{ fontWeight: 600 }}>{user.full_name}</span>
                <span className="t-footnote text-tertiary">{user.email} · {user.role}</span>
              </div>
              <button className="btn" style={{ color: 'var(--negative)', background: 'none', padding: '8px 4px' }} onClick={logout}>Log out</button>
            </div>
          </Section>
        )}

        <Section title="Preferences" note="Saved on this device.">
          <div className="list-row">
            <div className={styles.iconBox}>{theme === 'dark' ? <Moon size={20} strokeWidth={1.6} /> : <Sun size={20} strokeWidth={1.6} />}</div>
            <div className={styles.grow}><span className="t-callout" style={{ fontWeight: 600 }}>Appearance</span></div>
            <Segmented ariaLabel="Appearance" value={theme} onChange={v => { if (v !== theme) toggle(); }} options={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />
          </div>
          <div className="list-row">
            <div className={styles.iconBox}><Globe2 size={20} strokeWidth={1.6} /></div>
            <div className={styles.grow}>
              <span className="t-callout" style={{ fontWeight: 600 }}>Default market</span>
              <span className="t-footnote text-tertiary">What dashboards show first</span>
            </div>
            <Segmented<MarketScope> ariaLabel="Default market" value={scope} onChange={setScope} options={[{ value: 'india', label: 'India' }, { value: 'global', label: 'Global' }]} />
          </div>
          <div className="list-row">
            <div className={styles.iconBox}><Bell size={20} strokeWidth={1.6} /></div>
            <div className={styles.grow}>
              <span className="t-callout" style={{ fontWeight: 600 }}>Notifications: watchlist only</span>
              <span className="t-footnote text-tertiary">Hide signals for acts you don’t watch</span>
            </div>
            <Switch checked={watchOnly} onChange={v => { setWatchOnly(v); writeWatchlistOnly(v); }} label="Show only watchlist notifications" />
          </div>
        </Section>

        <Section title="Shortcuts">
          <Link href="/watchlist" className="list-row">
            <div className={styles.iconBox}><Star size={20} strokeWidth={1.6} color="var(--text-secondary)" /></div>
            <div className={styles.grow}>
              <span className="t-callout" style={{ fontWeight: 600 }}>Watchlist</span>
              <span className="t-footnote text-tertiary">{watch.data ? `${num(watch.data.total)} act${watch.data.total === 1 ? '' : 's'} watched` : '—'}</span>
            </div>
            <ChevronRight size={16} color="var(--text-tertiary)" />
          </Link>
          {canExport && (          <button className="list-row" onClick={exportPdf} disabled={exporting}>
              <div className={styles.iconBox}>{exporting ? <Loader2 size={20} strokeWidth={1.6} className="spin" /> : <FileDown size={20} strokeWidth={1.6} />}</div>
              <div className={styles.grow}>
                <span className="t-callout" style={{ fontWeight: 600 }}>Export executive report</span>
                <span className="t-footnote text-tertiary">{exporting ? 'Generating PDF…' : 'PDF with KPIs, top acts and AI briefing'}</span>
              </div>
              <ChevronRight size={16} color="var(--text-tertiary)" />
            </button>)}
        </Section>

        <section className={styles.section}>
          <h2 className={`text-secondary ${styles.sectionTitle}`}>System status</h2>
          {health.error && !h ? <div className="list-group"><ErrorState message="Backend unreachable." onRetry={() => health.mutate()} /></div> : !h ? <Skeleton height={156} radius={20} /> : (
            <div className="list-group">
              <div className="list-row"><div className={styles.grow}><span className="t-body">Status</span></div><Status ok={h.status === 'ok'} up="Healthy" down="Degraded" /></div>
              <div className="list-row"><div className={styles.grow}><span className="t-body">Data sources configured</span></div><span className="t-body text-secondary num-rounded">{configured} of {apiEntries.length}</span></div>
              <div className="list-row"><div className={styles.grow}><span className="t-body">Backend version</span></div><span className="t-body text-secondary num-rounded">{h.version}</span></div>
            </div>
          )}
        </section>

        {h && <>
          <Section title="Infrastructure">
            <div className="list-row"><div className={styles.iconBox}><Database size={20} strokeWidth={1.6} /></div><div className={styles.grow}><span className="t-callout">PostgreSQL</span></div><Status ok={h.services.postgres === 'up'} /></div>
            <div className="list-row"><div className={styles.iconBox}><HardDrive size={20} strokeWidth={1.6} /></div><div className={styles.grow}><span className="t-callout">MongoDB</span></div><Status ok={h.services.mongodb === 'up'} /></div>
            <div className="list-row"><div className={styles.iconBox}><Server size={20} strokeWidth={1.6} /></div><div className={styles.grow}><span className="t-callout">Redis</span></div><Status ok={h.services.redis === 'up'} /></div>
          </Section>
          <Section title="Data sources" note="Read-only status from the backend configuration. Keys are never shown here.">
            {apiEntries.map(([key, ok]) => (
              <div key={key} className="list-row">
                <div className={styles.grow}>
                  <span className="t-callout" style={{ fontWeight: 600 }}>{API_LABELS[key] ?? key}</span>
                  {API_NOTES[key] && <span className="t-caption text-tertiary">{API_NOTES[key]}</span>}
                </div>
                <Status ok={ok} up="Configured" down="Not set" />
              </div>
            ))}
          </Section>
        </>}
      </div>
    </Page>
  );
}
