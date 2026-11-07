'use client';
import Link from 'next/link';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import {
  CheckCircle, XCircle, Moon, Sun, Server, Database,
  HardDrive, Zap, Info, Star, FileDown, LogOut, ArrowRight,
} from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { MetricTile } from '@/components/ui/MetricTile';
import { useTheme } from '@/components/providers/ThemeProvider';
import { useAuth } from '@/components/providers/AuthProvider';
import { getHealth, getWatchlist, downloadExecutiveReportPdf } from '@/lib/api';
import { useState } from 'react';
import styles from './page.module.css';

const API_LABELS: Record<string, string> = {
  spotify: 'Spotify',
  youtube: 'YouTube',
  ticketmaster: 'Ticketmaster',
  tmdb: 'TMDB',
  groq: 'Groq (AI Copilot)',
  gemini: 'Gemini (fallback AI)',
  newsapi: 'NewsAPI',
  reddit: 'Reddit',
  lastfm: 'Last.fm',
  mapbox: 'Mapbox',
};

const API_NOTES: Record<string, string> = {
  spotify: 'Authenticated, but Development-mode apps get no popularity/followers/genres per Spotify’s Nov 2024 policy — Last.fm is the primary signal until extended access is approved.',
  lastfm: 'Primary music-demand signal — verified coverage across all tracked artists (Indian + international).',
  groq: 'Powers the AI Copilot and executive briefings.',
};

function ServiceRow({ name, up, icon }: { name: string; up: boolean; icon: React.ReactNode }) {
  return (
    <div className={styles.row}>
      <div className={styles.rowLeft}>
        <div className={styles.rowIcon}>{icon}</div>
        <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{name}</span>
      </div>
      <div className={styles.statusBadge} style={{
        color: up ? 'var(--positive)' : 'var(--negative)',
        background: up ? 'var(--positive-dim, rgba(48,209,88,0.12))' : 'var(--negative-dim)',
      }}>
        {up ? <CheckCircle size={13} /> : <XCircle size={13} />}
        {up ? 'Connected' : 'Unreachable'}
      </div>
    </div>
  );
}

function ApiKeyRow({ name, configured, note }: { name: string; configured: boolean; note?: string }) {
  return (
    <div className={styles.row}>
      <div className={styles.rowLeft}>
        <div className={styles.rowIcon} style={{ opacity: configured ? 1 : 0.5 }}>
          {configured ? <CheckCircle size={14} color="var(--positive)" /> : <XCircle size={14} color="var(--text-tertiary)" />}
        </div>
        <div>
          <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{name}</span>
          {note && <p className="t-caption text-tertiary" style={{ marginTop: 2, maxWidth: 480 }}>{note}</p>}
        </div>
      </div>
      <span className="t-caption" style={{ color: configured ? 'var(--positive)' : 'var(--text-tertiary)', fontWeight: 600, flexShrink: 0 }}>
        {configured ? 'Configured' : 'Not set'}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const { data: health, isLoading, error } = useSWR('health', getHealth, {
    refreshInterval: 30000,
    shouldRetryOnError: false,
  });
  const { data: watchlistData } = useSWR('watchlist', () => getWatchlist(), { shouldRetryOnError: false });
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const apiEntries = health ? Object.entries(health.apis_configured) : [];
  const configuredCount = apiEntries.filter(([, v]) => v).length;

  async function handleExportPdf() {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await downloadExecutiveReportPdf();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `liveiq-executive-report-${new Date().toISOString().slice(0, 10)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Failed to generate report');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Settings" subtitle="System health, API configuration, and preferences" />
      <div style={{ padding: '84px 28px 40px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Summary tiles */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }} className="grid-3">
          <MetricTile
            label="System Status"
            value={isLoading ? '—' : health?.status === 'ok' ? 'Healthy' : 'Degraded'}
            icon={<Server size={16} />}
            accent={health?.status === 'ok'}
            delay={0}
          />
          <MetricTile
            label="APIs Configured"
            value={health ? `${configuredCount}/${apiEntries.length}` : '—'}
            icon={<Zap size={16} />}
            delay={0.05}
          />
          <MetricTile
            label="Backend Version"
            value={health?.version ?? '—'}
            icon={<Info size={16} />}
            delay={0.1}
          />
        </div>

        {error && (
          <GlassCard style={{ padding: 20 }} delay={0.12}>
            <p className="t-callout text-tertiary">
              Backend unreachable — start FastAPI to see live system status.
            </p>
          </GlassCard>
        )}

        {/* Infrastructure */}
        <GlassCard style={{ padding: 24 }} delay={0.15}>
          <h2 className="t-headline text-primary" style={{ marginBottom: 4 }}>Infrastructure</h2>
          <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>Core data stores this app depends on</p>
          {isLoading ? (
            <div className="skeleton" style={{ height: 120, borderRadius: 10 }} />
          ) : health ? (
            <div className={styles.rowList}>
              <ServiceRow name="PostgreSQL (NeonDB)" up={health.services.postgres === 'up'} icon={<Database size={14} />} />
              <ServiceRow name="MongoDB" up={health.services.mongodb === 'up'} icon={<HardDrive size={14} />} />
              <ServiceRow name="Redis" up={health.services.redis === 'up'} icon={<Server size={14} />} />
            </div>
          ) : null}
        </GlassCard>

        {/* API Keys */}
        <GlassCard style={{ padding: 24 }} delay={0.2}>
          <h2 className="t-headline text-primary" style={{ marginBottom: 4 }}>Data Source API Keys</h2>
          <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>
            Live status from the backend&apos;s .env configuration — no keys are shown or editable here for security; edit backend/.env directly.
          </p>
          {isLoading ? (
            <div className="skeleton" style={{ height: 240, borderRadius: 10 }} />
          ) : health ? (
            <div className={styles.rowList}>
              {apiEntries.map(([key, configured]) => (
                <ApiKeyRow
                  key={key}
                  name={API_LABELS[key] ?? key}
                  configured={configured}
                  note={API_NOTES[key]}
                />
              ))}
            </div>
          ) : null}
        </GlassCard>

        {/* Preferences */}
        <GlassCard style={{ padding: 24 }} delay={0.25}>
          <h2 className="t-headline text-primary" style={{ marginBottom: 4 }}>Preferences</h2>
          <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>Personal display settings, saved to this browser</p>
          <div className={styles.row}>
            <div className={styles.rowLeft}>
              <div className={styles.rowIcon}>{theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}</div>
              <div>
                <span className="t-callout text-primary" style={{ fontWeight: 600 }}>Appearance</span>
                <p className="t-caption text-tertiary" style={{ marginTop: 2 }}>Dark mode by default, matches Apple iOS 26 design language</p>
              </div>
            </div>
            <button className="btn btn-secondary" onClick={toggle} style={{ flexShrink: 0 }}>
              Switch to {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </GlassCard>

        {/* Account */}
        {user && (
          <GlassCard style={{ padding: 24 }} delay={0.28}>
            <h2 className="t-headline text-primary" style={{ marginBottom: 4 }}>Account</h2>
            <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>Signed in as</p>
            <div className={styles.row}>
              <div className={styles.rowLeft}>
                <div className={styles.rowIcon}><CheckCircle size={14} color="var(--positive)" /></div>
                <div>
                  <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{user.full_name}</span>
                  <p className="t-caption text-tertiary" style={{ marginTop: 2 }}>{user.email} · {user.role}</p>
                </div>
              </div>
              <button className="btn btn-secondary" onClick={logout} style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
                <LogOut size={14} /> Log out
              </button>
            </div>
          </GlassCard>
        )}

        {/* Watchlist summary */}
        <GlassCard style={{ padding: 24 }} delay={0.3}>
          <h2 className="t-headline text-primary" style={{ marginBottom: 4 }}>Watchlist</h2>
          <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>Entities you're tracking — their signals get priority in your notification feed</p>
          <div className={styles.row}>
            <div className={styles.rowLeft}>
              <div className={styles.rowIcon}><Star size={14} color="var(--warning)" /></div>
              <div>
                <span className="t-callout text-primary" style={{ fontWeight: 600 }}>
                  {watchlistData ? `${watchlistData.total} entit${watchlistData.total === 1 ? 'y' : 'ies'} watched` : '—'}
                </span>
                <p className="t-caption text-tertiary" style={{ marginTop: 2 }}>Manage from the Intelligence Hub or the Watchlist page</p>
              </div>
            </div>
            <Link href="/watchlist" className="btn btn-secondary" style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
              View Watchlist <ArrowRight size={14} />
            </Link>
          </div>
        </GlassCard>

        {/* Report export */}
        <GlassCard style={{ padding: 24 }} delay={0.32}>
          <h2 className="t-headline text-primary" style={{ marginBottom: 4 }}>Report Export</h2>
          <p className="t-footnote text-tertiary" style={{ marginBottom: 16 }}>Download a stakeholder-ready PDF — KPI summary, top entities, city coverage, AI briefing</p>
          <div className={styles.row}>
            <div className={styles.rowLeft}>
              <div className={styles.rowIcon}><FileDown size={14} /></div>
              <div>
                <span className="t-callout text-primary" style={{ fontWeight: 600 }}>Executive Report (PDF)</span>
                <p className="t-caption text-tertiary" style={{ marginTop: 2 }}>Generated live from current portfolio data — may take a few seconds</p>
              </div>
            </div>
            <button className="btn btn-primary" onClick={handleExportPdf} disabled={exporting} style={{ flexShrink: 0 }}>
              {exporting ? 'Generating…' : 'Export PDF'}
            </button>
          </div>
          {exportError && (
            <p className="t-caption" style={{ color: 'var(--negative)', marginTop: 10 }}>{exportError}</p>
          )}
        </GlassCard>

      </div>
    </div>
  );
}
