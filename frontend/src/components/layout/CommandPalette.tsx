'use client';

/* eslint-disable react-hooks/set-state-in-effect -- these effects sync state from external sources (URL params, localStorage, debounced network results), which is the intended use */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, CornerDownLeft, History, Sun, Moon, Globe2, MapPinned, Music2 } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { searchEntities, EntitySearchResult } from '@/lib/api';
import { useTheme } from '@/components/providers/ThemeProvider';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { NAV_ALL } from './nav';
import { PaletteContext } from './shell-context';
import styles from './CommandPalette.module.css';

const RECENT_KEY = 'liveiq-recent-searches';
interface Recent { id: string; label: string; href: string; hint?: string }
function readRecents(): Recent[] {
  try { const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]'); return Array.isArray(v) ? v.filter((r): r is Recent => !!r && typeof r.id === 'string' && typeof r.href === 'string' && r.href.startsWith('/')).slice(0, 4) : []; } catch { return []; }
}
function pushRecent(r: Recent) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify([r, ...readRecents().filter(x => x.id !== r.id)].slice(0, 4))); } catch { /* storage unavailable */ }
}

interface Item { id: string; label: string; hint?: string; icon: React.ReactNode; run: () => void }

/** Spotlight-style ⌘K palette: jump to any page, find any entity, flip theme / market. */
export function PaletteProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [entities, setEntities] = useState<EntitySearchResult[]>([]);
  const [active, setActive] = useState(0);
  const [recents, setRecents] = useState<Recent[]>([]);
  const listRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { theme, toggle } = useTheme();
  const { scope, setScope } = useMarketScope();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen(o => !o); }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => { if (open) { setQ(''); setEntities([]); setActive(0); setRecents(readRecents()); setTimeout(() => inputRef.current?.focus(), 30); } }, [open]);

  useEffect(() => {
    if (q.trim().length < 2) { setEntities([]); return; }
    let cancelled = false; // ignore out-of-order responses for an older query
    const t = setTimeout(async () => {
      try { const r = (await searchEntities(q.trim(), 6)).results; if (!cancelled) setEntities(r); } catch { if (!cancelled) setEntities([]); }
    }, 180);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q]);

  const items: Item[] = useMemo(() => {
    const go = (href: string) => () => { router.push(href); setOpen(false); };
    const needle = q.trim().toLowerCase();
    const pages = NAV_ALL.filter(n => !needle || n.label.toLowerCase().includes(needle))
      .map(n => ({ id: `p${n.href}`, label: n.label, hint: 'Page', icon: <n.icon size={16} />, run: go(n.href) }));
    const goEntity = (e: EntitySearchResult) => () => { pushRecent({ id: `e${e.id}`, label: e.name, href: `/intelligence?entity=${e.id}`, hint: e.category ?? e.entity_type }); router.push(`/intelligence?entity=${e.id}`); setOpen(false); };
    const ents = entities.map(e => ({ id: `e${e.id}`, label: e.name, hint: e.category ?? e.entity_type, icon: <Music2 size={16} />, run: goEntity(e) }));
    const rec: Item[] = needle ? [] : recents.map(r => ({ id: `r${r.id}`, label: r.label, hint: 'Recent', icon: <History size={16} />, run: go(r.href) }));
    const actions: Item[] = [
      { id: 'a-theme', label: theme === 'dark' ? 'Switch to Light appearance' : 'Switch to Dark appearance', hint: 'Action', icon: theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />, run: () => { toggle(); setOpen(false); } },
      { id: 'a-scope', label: scope === 'india' ? 'Show Global market' : 'Show India market', hint: 'Action', icon: scope === 'india' ? <Globe2 size={16} /> : <MapPinned size={16} />, run: () => { setScope(scope === 'india' ? 'global' : 'india'); setOpen(false); } },
    ].filter(a => !needle || a.label.toLowerCase().includes(needle));
    return [...rec, ...ents, ...pages, ...actions];
  }, [q, entities, recents, router, theme, toggle, scope, setScope]);

  useEffect(() => { setActive(0); }, [items.length]);
  useEffect(() => { listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }); }, [active]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, items.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); items[active]?.run(); }
    else if (e.key === 'Tab') { e.preventDefault(); } // keep focus inside the dialog
  }

  return (
    <PaletteContext.Provider value={{ open: () => setOpen(true) }}>
      {children}
      <AnimatePresence>
        {open && (
          <motion.div className={styles.backdrop} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={e => { if (e.target === e.currentTarget) setOpen(false); }}>
            <motion.div className={styles.panel} role="dialog" aria-label="Command palette"
              initial={{ opacity: 0, scale: .96, y: -12 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: .97 }}
              transition={{ type: 'spring', stiffness: 520, damping: 38 }}>
              <div className={styles.inputRow}>
                <Search size={18} className={styles.sIcon} />
                <input ref={inputRef} role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list" value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKeyDown}
                  placeholder="Search artists, pages, actions…" aria-label="Search" className={styles.input} />
                <kbd className={styles.kbd}>esc</kbd>
              </div>
              <div className={styles.list} role="listbox" id="palette-list" ref={listRef}>
                {items.length === 0 && <p className={styles.empty}>No results for “{q}”</p>}
                {items.map((it, i) => (
                  <button key={it.id} role="option" aria-selected={i === active} className={`${styles.row} ${i === active ? styles.rowActive : ''}`}
                    onMouseEnter={() => setActive(i)} onClick={it.run}>
                    <span className={styles.rIcon}>{it.icon}</span>
                    <span className={styles.rLabel}>{it.label}</span>
                    {it.hint && <span className={styles.rHint}>{it.hint}</span>}
                    {i === active && <CornerDownLeft size={14} className={styles.enter} />}
                  </button>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </PaletteContext.Provider>
  );
}
