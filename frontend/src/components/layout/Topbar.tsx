'use client';


import { useState, useRef, useEffect } from 'react';
import { Sun, Moon, Search, LogOut, Menu } from 'lucide-react';
import { useMarketScope } from '@/components/providers/MarketScopeProvider';
import { Segmented } from '@/components/ui/Controls';
import { useShell, usePalette } from './shell-context';
import { useTheme } from '@/components/providers/ThemeProvider';
import { useAuth } from '@/components/providers/AuthProvider';
import { NotificationBell } from './NotificationBell';
import styles from './Topbar.module.css';

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
    function onEsc(e: KeyboardEvent) { if (e.key === 'Escape') setOpen(false); }
    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('keydown', onEsc);
    return () => { document.removeEventListener('mousedown', onClickOutside); document.removeEventListener('keydown', onEsc); };
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
