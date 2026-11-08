'use client';

import { useCallback, useMemo, useState } from 'react';
import useSWR from 'swr';
import { Download, Loader2, Lock, Play, Search, ChevronRight, DatabaseZap } from 'lucide-react';
import { Page } from '@/components/ui/Page';
import { GlassCard } from '@/components/ui/GlassCard';
import { Segmented } from '@/components/ui/Controls';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton, SkeletonRows } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { useToast } from '@/components/ui/Toast';
import { InfoSheet } from '@/components/ui/Provenance';
import { useAuth } from '@/components/providers/AuthProvider';
import {
  ApiError, GapItem, GapKind, GapQuery, DataGapsResponse, ProvenanceEntry, AdminJob,
  getAdminJobs, getDataGaps, patchAdminRecord, runAdminJob,
} from '@/lib/api';
import { provenanceLabel } from '@/lib/provenance';
import { downloadCsv } from '@/lib/csv';
import { num, timeAgo } from '@/lib/format';
import styles from './page.module.css';

const PAGE_SIZE = 25;
const KINDS: { value: GapKind; label: string }[] = [{ value: 'entities', label: 'Entities' }, { value: 'venues', label: 'Venues' }, { value: 'cities', label: 'Cities' }];
const ENTITY_TYPES = ['artist', 'comedian', 'attraction', 'movie', 'sports_team', 'theatre_group'];
const VENUE_TYPES = ['arena', 'stadium', 'theatre', 'club', 'convention_centre', 'amphitheatre', 'sports_complex', 'outdoor_grounds', 'art_gallery', 'other'];
const TYPES: Record<GapKind, string[]> = { entities: ENTITY_TYPES, venues: VENUE_TYPES, cities: [] };

type FieldKind = { t: 'int' | 'num' | 'text' | 'long' | 'bool' | 'enum' | 'url' | 'pin'; min?: number; max?: number; options?: string[] };
const FIELD: Record<string, FieldKind> = {
  total_capacity: { t: 'int', min: 1 }, standing_capacity: { t: 'int', min: 1 }, seated_capacity: { t: 'int', min: 1 }, vip_capacity: { t: 'int', min: 1 },
  typical_venue_capacity_min: { t: 'int', min: 1 }, typical_venue_capacity_max: { t: 'int', min: 1 },
  booking_price_range_min: { t: 'int', min: 1 }, booking_price_range_max: { t: 'int', min: 1 },
  population: { t: 'int', min: 1 }, metro_population: { t: 'int', min: 1 }, avg_monthly_income: { t: 'int', min: 1 },
  youth_population_pct: { t: 'num', min: 0, max: 100 }, tier: { t: 'int', min: 1, max: 4 },
  nightlife_score: { t: 'num', min: 0, max: 100 }, sports_affinity_score: { t: 'num', min: 0, max: 100 }, arts_culture_score: { t: 'num', min: 0, max: 100 },
  comedy_market_size: { t: 'num', min: 0, max: 100 }, music_market_size: { t: 'num', min: 0, max: 100 },
  lat: { t: 'num', min: 6, max: 38 }, lng: { t: 'num', min: 68, max: 98 },
  is_international: { t: 'bool' }, is_indoor: { t: 'bool' }, has_parking: { t: 'bool' }, is_alcohol_permitted: { t: 'bool' },
  venue_type: { t: 'enum', options: VENUE_TYPES }, description: { t: 'long' }, image_url: { t: 'url' }, pincode: { t: 'pin' },
};
const fieldKind = (f: string): FieldKind => FIELD[f] ?? { t: 'text' };
const label = (f: string) => { const s = f.replace(/_/g, ' ').replace(/\b(pct|url)\b/g, m => m.toUpperCase()); return s.charAt(0).toUpperCase() + s.slice(1); };
const typeLabel = (t: string) => label(t);

function validate(field: string, raw: string): { value?: string | number | boolean; error?: string } {
  const v = raw.trim();
  const k = fieldKind(field);
  if (k.t === 'bool') return { value: v === 'true' };
  if (k.t === 'int' || k.t === 'num') {
    const n = Number(v);
    if (!Number.isFinite(n) || (k.t === 'int' && !Number.isInteger(n))) return { error: k.t === 'int' ? 'Enter a whole number.' : 'Enter a number.' };
    if (k.min != null && n < k.min) return { error: `Must be at least ${k.min}.` };
    if (k.max != null && n > k.max) return { error: `Must be at most ${k.max}.` };
    return { value: n };
  }
  if (k.t === 'url' && !/^https?:\/\/\S+$/i.test(v)) return { error: 'Must start with http:// or https://.' };
  if (k.t === 'pin' && !/^\d{6}$/.test(v)) return { error: 'Enter a 6-digit pincode.' };
  if (k.t === 'enum' && !k.options?.includes(v)) return { error: 'Choose a type.' };
  return { value: v };
}

function cronLabel(c: Record<string, number | string>): string {
  const hh = (h: number, m: number) => `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  const m = Number(c.minute ?? 0);
  if (c.hour == null) return `Hourly at :${String(m).padStart(2, '0')} IST`;
  const t = hh(Number(c.hour), m);
  if (c.day_of_week) return `Weekly, ${String(c.day_of_week).replace(/^./, x => x.toUpperCase())} ${t} IST`;
  return `Daily ${t} IST`;
}

/* ─── Edit sheet ─── */
function EditSheet({ kind, item, editable, me, onClose, onSaved }: {
  kind: GapKind; item: GapItem | null; editable: string[]; me: string | null; onClose: () => void;
  onSaved: (item: GapItem, changed: string[]) => Promise<void>;
}) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [showOther, setShowOther] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prov, setProv] = useState<Record<string, ProvenanceEntry>>({});
  const [formErr, setFormErr] = useState('');
  const toast = useToast();
  const [lastId, setLastId] = useState<string | null>(null);
  if (item && item.id !== lastId) { setLastId(item.id); setVals({}); setErrs({}); setShowOther(false); setProv({}); setFormErr(''); }

  const missing = useMemo(() => (item?.missing ?? []).filter(f => editable.includes(f)), [item, editable]);
  const other = useMemo(() => editable.filter(f => !missing.includes(f)), [editable, missing]);
  const unEditable = (item?.missing ?? []).filter(f => !editable.includes(f));

  async function save() {
    if (!item) return;
    const body: Record<string, string | number | boolean> = {}; const e: Record<string, string> = {};
    for (const [f, raw] of Object.entries(vals)) {
      if (raw.trim() === '' ) continue;
      const r = validate(f, raw);
      if (r.error) e[f] = r.error; else body[f] = r.value as string | number | boolean;
    }
    setErrs(e); setFormErr('');
    if (Object.keys(e).length) return;
    if (!Object.keys(body).length) { setFormErr('Enter a value for at least one field.'); return; }
    setBusy(true);
    try {
      const res = await patchAdminRecord(kind, item.id, body);
      setProv(res.provenance ?? {});
      toast(`Saved ${item.name}`, 'success');
      await onSaved(item, Object.keys(res.changed));
      onClose();
    } catch (x) {
      const status = x instanceof ApiError ? x.status : 0;
      const raw = x instanceof ApiError ? (x.raw as { fields?: unknown } | undefined) : undefined;
      if (status === 422 && raw && typeof raw === 'object' && raw.fields && !Array.isArray(raw.fields)) {
        setErrs(raw.fields as Record<string, string>);
        setFormErr('Some values were rejected. Fix the highlighted fields.');
      } else if (status === 403) setFormErr('Your role can’t edit records.');
      else setFormErr('Couldn’t save. Please try again.');
      toast('Couldn’t save changes', 'error');
    } finally { setBusy(false); }
  }

  const input = (f: string) => {
    const k = fieldKind(f);
    const id = `edit-${f}`;
    const common = { id, 'aria-invalid': !!errs[f], value: vals[f] ?? '', onChange: (e: React.ChangeEvent<HTMLInputElement & HTMLSelectElement & HTMLTextAreaElement>) => setVals(v => ({ ...v, [f]: e.target.value })) };
    return (
      <div className={styles.field} key={f}>
        <label htmlFor={id}>{label(f)}</label>
        {k.t === 'bool' ? <select className="input" {...common}><option value="">Not set</option><option value="true">Yes</option><option value="false">No</option></select>
          : k.t === 'enum' ? <select className="input" {...common}><option value="">Not set</option>{k.options!.map(o => <option key={o} value={o}>{typeLabel(o)}</option>)}</select>
          : k.t === 'long' ? <textarea className="input" rows={3} {...common} />
          : <input className="input" inputMode={k.t === 'int' || k.t === 'num' || k.t === 'pin' ? 'decimal' : 'text'} {...common} placeholder={k.min != null && k.max != null ? `${k.min} to ${k.max}` : undefined} />}
        {errs[f] && <span className={styles.fieldErr} role="alert">{errs[f]}</span>}
        {prov[f] && <span className={styles.fieldHint}>{provenanceLabel(prov[f], me)}</span>}
      </div>
    );
  };

  return (
    <Sheet open={!!item} onClose={onClose} title={item?.name ?? 'Edit record'}>
      {item && (
        <form className={styles.form} onSubmit={e => { e.preventDefault(); void save(); }} noValidate>
          <p className={styles.sub}>
            {missing.length ? `Missing: ${missing.map(label).join(', ')}.` : 'No tracked fields are missing.'}{' '}
            Values you save are stored as <b>Manual · you</b> with an audit trail. Fields can be set, never cleared.
          </p>
          {unEditable.length > 0 && <p className={styles.fieldHint}>{unEditable.map(label).join(', ')} can’t be edited here.</p>}
          {missing.map(input)}
          {other.length > 0 && (
            <>
              <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setShowOther(s => !s)} aria-expanded={showOther}>{showOther ? 'Hide other fields' : `Edit other fields (${other.length})`}</button>
              {showOther && <div className={styles.more}>{other.map(input)}<p className={styles.fieldHint}>Current values of filled fields are not shown. Saving overwrites them.</p></div>}
            </>
          )}
          {formErr && <p className={styles.fieldErr} role="alert">{formErr}</p>}
          <div className={styles.sheetActions}>
            <button type="button" className="btn btn-tinted" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={busy} data-testid="save-record">{busy ? <><Loader2 size={15} className="spin" /> Saving…</> : 'Save'}</button>
          </div>
        </form>
      )}
    </Sheet>
  );
}

/* ─── Jobs ─── */
function Jobs({ canRun }: { canRun: boolean }) {
  const { data, error, mutate } = useSWR('admin-jobs', () => getAdminJobs(20), { refreshInterval: 30000 });
  const toast = useToast();
  const [running, setRunning] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);

  async function run(j: AdminJob) {
    setRunning(j.name);
    try {
      await runAdminJob(j.name);
      toast(`${j.name.replace(/_/g, ' ')} started. It runs in the background.`, 'success');
      setTimeout(() => void mutate(), 2500);
    } catch (x) {
      const status = x instanceof ApiError ? x.status : 0;
      if (status === 403) { setDenied(true); toast('Only executives can run jobs. Scheduled runs continue as normal.', 'info'); }
      else if (status === 404) toast('That job no longer exists.', 'error');
      else toast('Couldn’t start the job.', 'error');
    } finally { setRunning(null); }
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="jobs">
      <div className={styles.jobsHead}>
        <h2 className={styles.title}>Scheduled jobs</h2>
        {data && <span className={styles.count}>{data.scheduler.enabled_in_this_process ? 'Scheduler on' : 'Scheduler off in this process'}</span>}
      </div>
      {denied && <p className={styles.notice} role="status" data-testid="jobs-denied">Running a job on demand needs an Executive account. You’re signed in as {canRun ? 'an executive' : 'an analyst'}, so jobs keep running on their schedule.</p>}
      {error && !data ? <div className="list-group"><ErrorState message="Couldn’t load the job list." onRetry={() => mutate()} /></div>
        : !data ? <Skeleton height={200} radius={20} />
        : data.jobs.length === 0 ? <div className="list-group"><EmptyState title="No jobs" message="The scheduler has no registered jobs." /></div>
        : (
          <div className="list-group">
            {data.jobs.map(j => {
              const r = j.last_run;
              const st = r?.status;
              return (
                <div key={j.name} className="list-row" data-testid={`job-${j.name}`}>
                  <div className={styles.rowMain}>
                    <span className={styles.rowName} style={{ whiteSpace: 'normal' }}>{j.name.replace(/_/g, ' ')}</span>
                    <span className={styles.rowMeta} style={{ whiteSpace: 'normal' }}>{j.description}</span>
                    <span className={styles.jobMeta}>
                      <span>{cronLabel(j.cron_ist)}</span><span aria-hidden>·</span>
                      {r ? (<><i className={`${styles.dot} ${st === 'success' ? styles.dotOk : st === 'error' ? styles.dotErr : ''}`} aria-hidden /><span data-testid="job-status">{st === 'success' ? 'Succeeded' : st === 'error' ? 'Failed' : st === 'partial' ? 'Partial' : 'Running'}</span><span>{timeAgo(r.finished_at ?? r.started_at)}</span>{r.rows_affected != null && <span>· {num(r.rows_affected)} rows</span>}</>) : <span>Not run yet</span>}
                    </span>
                  </div>
                  <button className="btn btn-tinted btn-sm" onClick={() => void run(j)} disabled={running === j.name || !canRun && denied} data-testid={`run-${j.name}`} aria-label={`Run ${j.name.replace(/_/g, ' ')} now`}>
                    {running === j.name ? <Loader2 size={14} className="spin" /> : <Play size={14} />} Run now
                  </button>
                </div>
              );
            })}
          </div>
        )}
    </section>
  );
}

/* ─── Page ─── */
export default function DataQualityPage() {
  const { user } = useAuth();
  const toast = useToast();
  const allowed = user?.role === 'analyst' || user?.role === 'executive';
  const [kind, setKind] = useState<GapKind>('entities');
  const [missing, setMissing] = useState<string[]>([]);
  const [type, setType] = useState('');
  const [market, setMarket] = useState<'all' | 'india' | 'global'>('all');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<GapItem | null>(null);
  const [exporting, setExporting] = useState(false);

  const query: GapQuery = useMemo(() => ({ kind, type: type || undefined, market, q: q.trim() || undefined, missing, page, page_size: PAGE_SIZE }), [kind, type, market, q, missing, page]);
  const key = allowed ? ['admin-gaps', JSON.stringify(query)] : null;
  const { data, error, isLoading, mutate } = useSWR<DataGapsResponse>(key, () => getDataGaps(query), { keepPreviousData: true });

  const reset = (fn: () => void) => { fn(); setPage(1); };
  const switchKind = (k: GapKind) => { setKind(k); setMissing([]); setType(''); setQ(''); setPage(1); };
  const toggle = (f: string) => reset(() => setMissing(m => m.includes(f) ? m.filter(x => x !== f) : [...m, f]));

  const coverage = useMemo(() => {
    if (!data || !data.scope_total) return null;
    const rows = data.tracked_fields.map(f => ({ f, pct: Math.round((1 - (data.summary_missing_counts[f] ?? 0) / data.scope_total) * 100), missing: data.summary_missing_counts[f] ?? 0 }));
    return { rows, avg: Math.round(rows.reduce((a, r) => a + r.pct, 0) / Math.max(rows.length, 1)) };
  }, [data]);

  const onSaved = useCallback(async (item: GapItem, changed: string[]) => {
    // Optimistic: drop the saved fields from this row immediately, then revalidate the real counts.
    await mutate(d => d && ({ ...d, items: d.items.map(i => i.id === item.id ? { ...i, missing: i.missing.filter(f => !changed.includes(f)), missing_count: i.missing.filter(f => !changed.includes(f)).length } : i) }), { revalidate: false });
    void mutate();
  }, [mutate]);

  async function exportCsv() {
    if (!data) return;
    setExporting(true);
    try {
      const rows: (string | number | null)[][] = [];
      const pages = Math.min(Math.ceil(data.total / 100), 50);
      for (let p = 1; p <= pages; p++) {
        const d = await getDataGaps({ ...query, page: p, page_size: 100 });
        d.items.forEach(i => rows.push([i.id, i.name, i.entity_type ?? i.venue_type ?? i.state ?? '', i.home_city ?? i.city ?? '', i.missing_count, i.missing.join('; ')]));
      }
      downloadCsv(`liveiq-data-gaps-${kind}-${new Date().toISOString().slice(0, 10)}.csv`, ['id', 'name', 'type_or_state', 'city', 'missing_count', 'missing_fields'], rows);
      toast(`Exported ${num(rows.length)} records`, 'success');
    } catch { toast('Couldn’t export the gap list', 'error'); } finally { setExporting(false); }
  }

  if (user && !allowed) {
    return (
      <Page title="Data quality" subtitle="Coverage of the public data behind LiveIQ">
        <GlassCard><div className={styles.lock} role="status" data-testid="viewer-notice">
          <Lock size={28} strokeWidth={1.5} />
          <p className="t-headline" style={{ color: 'var(--text-secondary)' }}>Analyst or Executive access</p>
          <p className="t-callout" style={{ maxWidth: 360 }}>The data review screen is read-only for viewers and hidden until your role is upgraded. Ask an admin if you need to fill data gaps.</p>
        </div></GlassCard>
      </Page>
    );
  }

  const items = data?.items ?? [];
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const metaOf = (i: GapItem) => [i.entity_type && typeLabel(i.entity_type), i.venue_type && typeLabel(i.venue_type), i.home_city ?? i.city ?? i.state].filter(Boolean).join(' · ');

  return (
    <Page title="Data quality" subtitle="What public data we have, what is missing, and fix it by hand"
      actions={<button className="btn btn-tinted" onClick={() => void exportCsv()} disabled={!data || data.total === 0 || exporting} data-testid="export-gaps">{exporting ? <Loader2 size={15} className="spin" /> : <Download size={15} strokeWidth={1.75} />} Export CSV</button>}>
      <div className={styles.wrap}>
        <p className={styles.notice}>LiveIQ is built for Zomato District on public sources. Gaps are filled from public data or by hand here. Nothing on this screen comes from District.</p>

        <Segmented<GapKind> ariaLabel="Record type" value={kind} onChange={switchKind} options={KINDS} />

        <GlassCard className={styles.hero}>
          <div className={styles.heroTop}>
            <div>
              <h2 className={styles.title}>Coverage</h2>
              <p className={styles.sub}>{data ? `${num(data.scope_total)} ${kind} in scope. Tap a field to list records missing it.` : 'Loading…'}</p>
            </div>
            {coverage && <div style={{ textAlign: 'right' }}><div className={styles.big} data-testid="coverage-avg">{coverage.avg}%</div><div className={styles.sub}>average across fields</div></div>}
          </div>
          {error && !data ? <ErrorState message="Couldn’t load coverage." onRetry={() => mutate()} />
            : !coverage ? (isLoading || !data ? <Skeleton height={180} radius={14} /> : <p className={styles.sub}>Nothing in scope.</p>)
            : <div className={styles.cov} data-testid="coverage">{coverage.rows.map(r => (
              <button key={r.f} type="button" className={styles.covRow} aria-pressed={missing.includes(r.f)} onClick={() => toggle(r.f)} data-testid={`cov-${r.f}`}>
                <span className={styles.covTop}><span>{label(r.f)}</span><span>{r.pct}%</span></span>
                <span className={styles.bar}><span className={styles.barFill} style={{ display: 'block', width: `${r.pct}%` }} /></span>
                <span className={styles.fieldHint}>{num(r.missing)} missing</span>
              </button>))}</div>}
        </GlassCard>

        <div className={styles.filters}>
          {data && <div className={styles.chips} role="group" aria-label="Missing fields">{data.tracked_fields.map(f => (
            <button key={f} type="button" className="chip" aria-pressed={missing.includes(f)} onClick={() => toggle(f)}>{label(f)}<span style={{ opacity: .65 }}>{num(data.summary_missing_counts[f] ?? 0)}</span></button>))}</div>}
          <div className={styles.filterRow}>
            <div className={styles.search}><Search size={15} strokeWidth={1.75} /><input className="input" placeholder={`Search ${kind}`} aria-label={`Search ${kind}`} value={q} onChange={e => reset(() => setQ(e.target.value))} /></div>
            {TYPES[kind].length > 0 && <select className={`input ${styles.select}`} aria-label="Type" value={type} onChange={e => reset(() => setType(e.target.value))}><option value="">All types</option>{TYPES[kind].map(t => <option key={t} value={t}>{typeLabel(t)}</option>)}</select>}
            {kind === 'entities' && <Segmented<'all' | 'india' | 'global'> ariaLabel="Market" value={market} onChange={m => reset(() => setMarket(m))} options={[{ value: 'all', label: 'All' }, { value: 'india', label: 'India' }, { value: 'global', label: 'Global' }]} />}
            {missing.length > 0 && <button className="btn btn-ghost btn-sm" onClick={() => reset(() => setMissing([]))}>Clear filters</button>}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className={styles.jobsHead}><h2 className={styles.title}>Records</h2>{data && <span className={styles.count} data-testid="gap-count">{num(data.total)} {data.total === 1 ? 'record' : 'records'}{missing.length ? ' missing all selected fields' : ''}</span>}</div>
          {error && !data ? <div className="list-group"><ErrorState onRetry={() => mutate()} /></div>
            : !data ? <div className="list-group"><SkeletonRows rows={6} /></div>
            : items.length === 0 ? <div className="list-group"><EmptyState icon={<DatabaseZap size={32} strokeWidth={1.4} />} title="No records match" message="Try removing a filter or searching a different name." /></div>
            : <div className="list-group" data-testid="gap-list" style={{ opacity: isLoading ? .6 : 1 }}>{items.map(i => (
              <button key={i.id} type="button" className="list-row" onClick={() => setEditing(i)} data-testid="gap-row">
                <div className={styles.rowMain}>
                  <span className={styles.rowName}>{i.name}</span>
                  <span className={styles.rowMeta}>{metaOf(i) || '—'}</span>
                  <span className={styles.rowMeta} style={{ whiteSpace: 'normal' }}>{i.missing.length ? `Missing ${i.missing.map(label).join(', ')}` : 'Complete'}</span>
                </div>
                <ChevronRight size={16} color="var(--text-tertiary)" />
              </button>))}</div>}
          {data && data.total > data.page_size && (
            <div className={styles.pager}>
              <button className="btn btn-tinted btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
              <span className={styles.count}>Page {page} of {pages}</span>
              <button className="btn btn-tinted btn-sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>)}
          <p className={styles.notice} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>Manual edits are logged with who and when.
            <InfoSheet title="How edits are recorded"><p>Each field you save is stored as Manual with your email and a timestamp, and the last 50 changes keep their old and new values. Filled fields from public sources, such as Wikidata, keep their own source and retrieval date.</p><p>Setting any city score marks that city’s scores as editorial rather than derived.</p></InfoSheet>
          </p>
        </div>

        <Jobs canRun={user?.role === 'executive'} />
      </div>
      <EditSheet kind={kind} item={editing} editable={data?.editable_fields ?? []} me={user?.email ?? null} onClose={() => setEditing(null)} onSaved={onSaved} />
    </Page>
  );
}
