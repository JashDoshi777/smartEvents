'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Brain, TrendingUp, MapPin, BarChart3,
  Users, DollarSign, MessageSquare, Settings, ChevronLeft,
  Activity, Calculator, Users2, LineChart, Star, CalendarDays, Radio, Sparkles
} from 'lucide-react';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
  { href: '/',             icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/intelligence', icon: Brain,           label: 'Intelligence' },
  { href: '/trends',       icon: TrendingUp,      label: 'Trend Radar' },
  { href: '/markets',      icon: MapPin,           label: 'Markets' },
  { href: '/executive',    icon: BarChart3,        label: 'Executive' },
  { href: '/competitors',  icon: Users,            label: 'Competitors' },
  { href: '/listening',    icon: Radio,            label: 'Listening' },
  { href: '/recommendations', icon: Sparkles,      label: 'Recommendations' },
  { href: '/pricing',      icon: DollarSign,       label: 'Pricing' },
  { href: '/events',       icon: Activity,         label: 'Events' },
  { href: '/events/model', icon: Calculator,       label: 'Deal Modeler' },
  { href: '/events/pairing', icon: Users2,          label: 'Artist Pairing' },
  { href: '/intelligence/forecast', icon: LineChart, label: 'Demand Forecast' },
  { href: '/watchlist',    icon: Star,             label: 'Watchlist' },
  { href: '/venues/calendar', icon: CalendarDays,  label: 'Venue Calendar' },
  { href: '/psychology',   icon: Brain,            label: 'Psychology' },
  { href: '/copilot',      icon: MessageSquare,    label: 'AI Copilot' },
  { href: '/settings',     icon: Settings,         label: 'Settings' },
];

interface SidebarProps {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}

export function Sidebar({ collapsed, onCollapsedChange }: SidebarProps) {
  const pathname = usePathname();

  return (
    <motion.aside
      className={styles.sidebar}
      animate={{ width: collapsed ? 72 : 240 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {/* Logo */}
      <div className={styles.logo}>
        <div className={styles.logoMark}>
          <span>L</span>
        </div>
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              className={styles.logoText}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.2 }}
            >
              <span className={styles.logoName}>LiveIQ</span>
              <span className={styles.logoSub}>by District</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className={styles.divider} />

      {/* Nav */}
      <nav className={styles.nav}>
        {(() => {
          // Pick the single longest matching href so nested routes (e.g.
          // /events/model under /events) highlight only the most specific
          // match, not both.
          const bestMatch = NAV_ITEMS
            .filter(item => pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href)))
            .sort((a, b) => b.href.length - a.href.length)[0]?.href;

          return NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const active = href === bestMatch;
          return (
            <Link key={href} href={href} className={`${styles.navItem} ${active ? styles.active : ''}`}>
              <div className={styles.navIcon}>
                <Icon size={18} strokeWidth={active ? 2 : 1.6} />
              </div>
              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    className={styles.navLabel}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -6 }}
                    transition={{ duration: 0.18 }}
                  >
                    {label}
                  </motion.span>
                )}
              </AnimatePresence>
              {active && (
                <motion.div
                  className={styles.activeIndicator}
                  layoutId="sidebar-active"
                  transition={{ type: 'spring', stiffness: 380, damping: 34 }}
                />
              )}
            </Link>
          );
          });
        })()}
      </nav>

      {/* Collapse toggle */}
      <button
        className={styles.collapseBtn}
        onClick={() => onCollapsedChange(!collapsed)}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        <motion.div
          animate={{ rotate: collapsed ? 180 : 0 }}
          transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
        >
          <ChevronLeft size={16} />
        </motion.div>
      </button>
    </motion.aside>
  );
}
