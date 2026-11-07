'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { Check, ChevronDown, Search, X } from 'lucide-react';
import { getCities, getPortfolio, type PortfolioEntity } from '@/lib/api';
import styles from './intel.module.css';

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <span className={styles.hint}>{hint}</span>}
    </div>
  );
}

/** Searchable entity (artist/act) picker backed by the executive portfolio. India acts first. */
export function EntityPicker({ value, onChange, indiaOnly = false, types, placeholder = 'Select artist', id }: {
  value: string; onChange: (id: string, e: PortfolioEntity | null) => void; indiaOnly?: boolean; types?: string[]; placeholder?: string; id?: string;
}) {
  const { data, error } = useSWR('portfolio/picker', () => getPortfolio());
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const uid = useId();

  const all = useMemo(() => {
    const rows = (data?.portfolio ?? []).filter(e => (!indiaOnly || !e.is_international) && (!types || types.includes(e.type)));
    return rows.sort((a, b) => Number(a.is_international) - Number(b.is_international) || (b.composite_score ?? 0) - (a.composite_score ?? 0));
  }, [data, indiaOnly, types]);
  const selected = all.find(e => e.id === value) ?? (data?.portfolio ?? []).find(e => e.id === value);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (s ? all.filter(e => e.name.toLowerCase().includes(s)) : all).slice(0, 60);
  }, [all, q]);

  useEffect(() => {
    if (!open) return;
    const close = (ev: PointerEvent) => { if (!ref.current?.contains(ev.target as Node)) setOpen(false); };
    const esc = (ev: KeyboardEvent) => { if (ev.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', close); document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', esc); };
  }, [open]);

  return (
    <div className={styles.picker} ref={ref}>
      <button type="button" id={id} className={`input ${styles.trigger}`} data-empty={!selected} aria-haspopup="listbox" aria-expanded={open} aria-controls={uid}
        onClick={() => { setOpen(o => !o); setQ(''); }}>
        <span>{selected ? selected.name : data ? placeholder : error ? 'Artists unavailable' : 'Loading artists…'}</span>
        {selected ? <X size={15} aria-label="Clear" onClick={ev => { ev.stopPropagation(); onChange('', null); }} /> : <ChevronDown size={15} />}
      </button>
      {open && (
        <div className={styles.pop} id={uid}>
          <div className={styles.search}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 12, color: 'var(--text-tertiary)' }} />
              <input autoFocus className="input" style={{ paddingLeft: 32, minHeight: 38 }} placeholder="Search artists" value={q} onChange={e => setQ(e.target.value)} aria-label="Search artists" />
            </div>
          </div>
          <div className={styles.list} role="listbox">
            {shown.length === 0 ? <div className={styles.none}>No artists match “{q}”</div> : shown.map(e => (
              <button key={e.id} type="button" role="option" aria-selected={e.id === value} className={styles.opt} data-active={e.id === value}
                onClick={() => { onChange(e.id, e); setOpen(false); }}>
                <span>{e.name}</span>
                <small>{e.is_international ? 'Global' : 'India'}{e.id === value && <> <Check size={12} style={{ verticalAlign: -1 }} /></>}</small>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Native select (best on mobile) of cities from /cities, Indian cities only. */
export function CityPicker({ value, onChange, id, allowEmpty = true }: { value: string; onChange: (c: string) => void; id?: string; allowEmpty?: boolean }) {
  const { data, error } = useSWR('cities/picker', () => getCities());
  const cities = (data?.cities ?? []);
  return (
    <select id={id} className="input" style={{ minHeight: 44 }} value={value} onChange={e => onChange(e.target.value)} disabled={!data}>
      {allowEmpty && <option value="">{data ? 'Select city' : error ? 'Cities unavailable' : 'Loading cities…'}</option>}
      {cities.map(c => <option key={c.id} value={c.name}>{c.name}{c.tier ? ` · Tier ${c.tier}` : ''}</option>)}
    </select>
  );
}

/** iOS inset-grouped form container + row (label left, control right). */
export function FormGroup({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <div>
      {title && <div className={styles.ghead}>{title}</div>}
      <div className={styles.group}>{children}</div>
    </div>
  );
}
export function FormRow({ label, htmlFor, children }: { label: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className={styles.frow}>
      <label htmlFor={htmlFor}>{label}</label>
      <div className={styles.fctl}>{children}</div>
    </div>
  );
}
export const FormHint = ({ children }: { children: React.ReactNode }) => <div className={styles.fhint}>{children}</div>;
