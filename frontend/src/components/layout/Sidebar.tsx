'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, X } from 'lucide-react';
import { NAV_GROUPS, bestMatch } from './nav';
import styles from './Sidebar.module.css';

const GROUPS = NAV_GROUPS;

interface SidebarProps {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ collapsed, onCollapsedChange, mobileOpen, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const best = bestMatch(pathname);

  return (
    <>
      <AnimatePresence>
        {mobileOpen && (
          <motion.div className={styles.scrim} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onMobileClose} />
        )}
      </AnimatePresence>

      <aside
        className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''} ${mobileOpen ? styles.mobileOpen : ''}`}
        aria-label="Primary navigation"
      >
        <div className={styles.logo}>
          <div className={styles.logoMark}><span>L</span></div>
          {!collapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoName}>LiveIQ</span>
              <span className={styles.logoSub}>by District</span>
            </div>
          )}
          <button className={styles.closeMobile} onClick={onMobileClose} aria-label="Close menu"><X size={18} /></button>
        </div>

        <nav className={styles.nav}>
          {GROUPS.map(g => (
            <div key={g.title} className={styles.group}>
              {!collapsed && <span className={styles.groupTitle}>{g.title}</span>}
              {collapsed && <div className={styles.groupRule} />}
              {g.items.map(({ href, icon: Icon, label }) => {
                const active = href === best;
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={onMobileClose}
                    className={`${styles.navItem} ${active ? styles.active : ''}`}
                    aria-current={active ? 'page' : undefined}
                    title={collapsed ? label : undefined}
                  >
                    {active && (
                      <motion.span className={styles.activePill} layoutId="nav-pill" transition={{ type: 'spring', stiffness: 420, damping: 36 }} />
                    )}
                    <Icon size={18} strokeWidth={active ? 2.2 : 1.7} className={styles.navIcon} />
                    {!collapsed && <span className={styles.navLabel}>{label}</span>}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <button
          className={styles.collapseBtn}
          onClick={() => onCollapsedChange(!collapsed)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <ChevronLeft size={16} style={{ transform: collapsed ? 'rotate(180deg)' : undefined, transition: 'transform .3s var(--ease-out)' }} />
          {!collapsed && <span>Collapse</span>}
        </button>
      </aside>
    </>
  );
}
