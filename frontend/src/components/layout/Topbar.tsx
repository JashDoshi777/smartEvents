'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Sun, Moon, Search, LogOut, Music2, Film, Trophy, Mic2, Menu } from 'lucide-react';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { Segmented } from '@/components/ui/Controls';
import { useShell, usePalette } from './shell-context';
import { useTheme } from '@/components/providers/ThemeProvider';
import { useAuth } from '@/components/providers/AuthProvider';
import { searchEntities, EntitySearchResult } from '@/lib/api';
import { NotificationBell } from './NotificationBell';
import styles from './Topbar.module.css';

const TYPE_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  artist: Music2, movie: Film, sports_team: Trophy, comedian: Mic2,
};

function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<EntitySearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  // Debounced live search against the real /entities/search endpoint —
  // this input used to render with no handler at all (dead decoration).
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await searchEntities(query.trim());
        setResults(res.results);
        setActiveIndex(-1);
      } catch {
        setResults([]);
      }
    }, 220);
    return () => clearTimeout(timer);
  }, [query]);

  function goTo(entity: EntitySearchResult) {
    router.push(`/intelligence?entity=${entity.id}`);
    setQuery('');
    setResults([]);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex(i => Math.min(i + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex(i => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter' && activeIndex >= 0) { e.preventDefault(); goTo(results[activeIndex]); }
    else if (e.key === 'Escape') { setOpen(false); }
  }

  return (
    <div className={styles.searchWrap} ref={wrapRef}>
      <Search size={14} className={styles.searchIcon} />
      <input
        className={`${styles.searchInput} input`}
        placeholder="Search entities, cities..."
        type="search"
        value={query}
        onChange={e => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        aria-label="Search entities"
        aria-expanded={open && results.length > 0}
        role="combobox"
        aria-controls="global-search-results"
      />
      {open && query.trim().length >= 2 && (
        <div className={styles.searchDropdown} id="global-search-results" role="listbox">
          {results.length === 0 ? (
            <p className="t-caption text-tertiary" style={{ padding: '10px 14px' }}>No entities found.</p>
          ) : (
            results.map((r, i) => {
              const Icon = TYPE_ICON[r.entity_type] ?? Music2;
              return (
                <button
                  key={r.id}
                  className={`${styles.searchResult} ${i === activeIndex ? styles.searchResultActive : ''}`}
                  onClick={() => goTo(r)}
                  role="option"
                  aria-selected={i === activeIndex}
                >
                  <Icon size={14} className={styles.searchResultIcon} />
                  <span className="t-callout text-primary" style={{ fontWeight: 600 }}>{r.name}</span>
                  {r.category && <span className="t-caption text-tertiary">{r.category}</span>}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

function SearchTrigger() {
  const { open } = usePalette();
  return (
    <button className={styles.searchTrigger} onClick={open} aria-label="Search (Command K)">
      <Search size={15} />
      <span className={styles.searchText}>Search</span>
      <kbd className={styles.kbd}>⌘K</kbd>
    </button>
  );
}

interface TopbarProps {
  title: string;
  subtitle?: string;
  /** Show the inline title (fill/split pages, or once the large title scrolls away). */
  showTitle?: boolean;
  /** Bar gets its translucent material + hairline (true once content scrolls under it). */
  raised?: boolean;
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  if (!user) return null;

  const initial = user.full_name?.[0]?.toUpperCase() ?? user.email[0].toUpperCase();

  return (
    <div className={styles.userMenuWrap} ref={ref}>
      <button
        className={styles.userAvatar}
        onClick={() => setOpen(o => !o)}
        aria-label="User menu"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {initial}
      </button>
      {open && (
        <div className={styles.userDropdown} role="menu">
          <div className={styles.userInfo}>
            <span className="t-callout text-primary" style={{ fontWeight: 700 }}>{user.full_name}</span>
            <span className="t-caption text-tertiary">{user.email}</span>
            <span className={styles.roleBadge}>{user.role}</span>
          </div>
          <button className={styles.logoutBtn} onClick={logout} role="menuitem">
            <LogOut size={14} /> Log out
          </button>
        </div>
      )}
    </div>
  );
}

export function Topbar({ title, subtitle, showTitle = true, raised = true }: TopbarProps) {
  const { theme, toggle } = useTheme();
  const { scope, setScope } = useMarketScope();
  const { openMenu } = useShell();

  return (
    <header className={`${styles.topbar} ${raised ? styles.raised : ''}`}>
      <div className={styles.left}>
        <button className={styles.menuBtn} onClick={openMenu} aria-label="Open menu"><Menu size={18} /></button>
        <div className={`${styles.titles} ${showTitle ? styles.titleIn : ''}`}>
          <span className={styles.title} role="heading" aria-level={showTitle ? 1 : undefined}>{title}</span>
          {subtitle && showTitle && <p className={styles.subtitle}>{subtitle}</p>}
        </div>
      </div>

      <div className={styles.actions}>
        <div className={styles.scopeWrap}>
          <Segmented ariaLabel="Market scope" value={scope} onChange={setScope}
            options={[{ value: 'india', label: 'India' }, { value: 'global', label: 'Global' }]} />
        </div>
        <SearchTrigger />

        {/* Notifications */}
        <NotificationBell />

        {/* Theme toggle */}
        <button
          className={styles.themeToggle}
          onClick={toggle}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle theme"
        >
          <div className={`${styles.toggleTrack} ${theme === 'light' ? styles.light : ''}`}>
            <div className={styles.toggleThumb}>
              {theme === 'dark' ? <Moon size={10} /> : <Sun size={10} />}
            </div>
          </div>
        </button>

        {/* User menu */}
        <UserMenu />
      </div>
    </header>
  );
}
