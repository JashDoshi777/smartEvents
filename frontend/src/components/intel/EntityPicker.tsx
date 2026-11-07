'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Search, Check } from 'lucide-react';
import { initials, scoreColor } from './entity-utils';
import styles from './EntityPicker.module.css';

export interface PickerEntity { id: string; name: string; category?: string | null; composite_score?: number | null }

/** Searchable single-select for large entity lists (replaces unwieldy native <select>). */
export function EntityPicker({ entities, value, onChange, placeholder = 'Select an artist or act', loading, inline }: {
  entities: PickerEntity[]; value: string; onChange: (id: string) => void; placeholder?: string; loading?: boolean; inline?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const wrap = useRef<HTMLDivElement>(null);
  const selected = entities.find(e => e.id === value);

  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', down); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key); };
  }, [open]);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (s ? entities.filter(e => e.name.toLowerCase().includes(s) || (e.category ?? '').toLowerCase().includes(s)) : entities).slice(0, 60);
  }, [entities, q]);

  return (
    <div className={`${styles.wrap} ${inline ? styles.inline : ''}`} ref={wrap}>
      <button type="button" className={`input ${styles.trigger}`} aria-haspopup="listbox" aria-expanded={open}
        onClick={() => { setOpen(o => !o); setQ(''); }} disabled={loading && !entities.length}>
        {selected ? (
          <span className={styles.sel}><span className={styles.av}>{initials(selected.name)}</span><span className={styles.nm}>{selected.name}</span></span>
        ) : <span className={styles.ph}>{loading && !entities.length ? 'Loading…' : placeholder}</span>}
        <ChevronDown size={15} className={styles.chev} />
      </button>
      {open && (
        <div className={styles.pop} role="listbox">
          <div className={styles.search}>
            <Search size={14} />
            <input autoFocus placeholder="Search…" value={q} onChange={e => setQ(e.target.value)} aria-label="Search entities" />
          </div>
          <div className={styles.items}>
            {list.length === 0 && <p className={`t-callout text-tertiary ${styles.none}`}>No matches</p>}
            {list.map(e => (
              <button type="button" key={e.id} role="option" aria-selected={e.id === value} className={styles.item}
                onClick={() => { onChange(e.id); setOpen(false); }}>
                <span className={styles.av}>{initials(e.name)}</span>
                <span className={styles.txt}><span className={styles.nm}>{e.name}</span>{e.category && <span className="t-caption text-tertiary">{e.category}</span>}</span>
                {e.composite_score != null && <span className="tnum" style={{ color: scoreColor(e.composite_score), fontWeight: 600, fontSize: '.8125rem' }}>{Math.round(e.composite_score)}</span>}
                {e.id === value && <Check size={14} color="var(--accent)" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
