'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Brain, TrendingUp, MapPin, BarChart3, Users, IndianRupee,
  MessageSquare, Settings, ChevronLeft, Activity, Calculator, Users2, LineChart,
  Star, CalendarDays, Radio, Sparkles, Lightbulb, X,
} from 'lucide-react';
import styles from './Sidebar.module.css';

const GROUPS = [
  { title: 'Overview', items: [
    { href: '/',          icon: LayoutDashboard, label: 'Dashboard' },
    { href: '/executive', icon: BarChart3,       label: 'Executive' },
    { href: '/copilot',   icon: MessageSquare,   label: 'AI Copilot' },
  ]},
  { title: 'Discover', items: [
    { href: '/intelligence',    icon: Brain,     label: 'Intelligence' },
    { href: '/trends',          icon: TrendingUp, label: 'Trend Radar' },
    { href: '/recommendations', icon: Sparkles,  label: 'Recommendations' },
    { href: '/listening',       icon: Radio,     label: 'Social Listening' },
    { href: '/psychology',      icon: Lightbulb, label: 'Demand Psychology' },
  ]},
  { title: 'Markets', items: [
    { href: '/markets',          icon: MapPin,       label: 'City Markets' },
    { href: '/competitors',      icon: Users,        label: 'Competitors' },
    { href: '/venues/calendar',  icon: CalendarDays, label: 'Venue Calendar' },
  ]},
  { title: 'Plan & Price', items: [
    { href: '/pricing',               icon: IndianRupee, label: 'Pricing' },
    { href: '/events',                icon: Activity,    label: 'Fill-rate Monitor' },
    { href: '/events/model',          icon: Calculator,  label: 'Deal Modeler' },
    { href: '/events/pairing',        icon: Users2,      label: 'Artist Pairing' },
    { href: '/intelligence/forecast', icon: LineChart,   label: 'Demand Forecast' },
  ]},
  { title: 'Workspace', items: [
    { href: '/watchlist', icon: Star,     label: 'Watchlist' },
    { href: '/settings',  icon: Settings, label: 'Settings' },
  ]},
];

const ALL = GROUPS.flatMap(g => g.items);

interface SidebarProps {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ collapsed, onCollapsedChange, mobileOpen, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  // Highlight only the most specific match (/events/model beats /events).
  const best = ALL
    .filter(i => pathname === i.href || (i.href !== '/' && pathname.startsWith(i.href)))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

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
