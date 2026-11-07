'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Brain, MapPin, MessageSquare, Menu } from 'lucide-react';
import { motion } from 'framer-motion';
import styles from './TabBar.module.css';

const TABS = [
  { href: '/', icon: LayoutDashboard, label: 'Home' },
  { href: '/intelligence', icon: Brain, label: 'Discover' },
  { href: '/markets', icon: MapPin, label: 'Markets' },
  { href: '/copilot', icon: MessageSquare, label: 'Copilot' },
];

/** iOS bottom tab bar — phones only. "More" opens the full sidebar drawer. */
export function TabBar({ onMore }: { onMore: () => void }) {
  const pathname = usePathname();
  return (
    <nav className={styles.bar} aria-label="Tab bar">
      {TABS.map(({ href, icon: Icon, label }) => {
        const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
        return (
          <Link key={href} href={href} className={`${styles.tab} ${active ? styles.active : ''}`} aria-current={active ? 'page' : undefined}>
            {active && <motion.span layoutId="tab-pill" className={styles.pill} transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
            <Icon size={22} strokeWidth={active ? 2.3 : 1.7} />
            <span>{label}</span>
          </Link>
        );
      })}
      <button className={styles.tab} onClick={onMore} aria-label="More">
        <Menu size={22} strokeWidth={1.7} /><span>More</span>
      </button>
    </nav>
  );
}
