'use client';

import { motion } from 'framer-motion';
import { ReactNode } from 'react';
import styles from './MetricTile.module.css';

interface MetricTileProps {
  label: string;
  value: string | number;
  sub?: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  icon?: ReactNode;
  accent?: boolean;
  delay?: number;
}

export function MetricTile({ label, value, sub, trend, trendValue, icon, accent, delay = 0 }: MetricTileProps) {
  const trendColor = trend === 'up' ? 'var(--positive)' : trend === 'down' ? 'var(--negative)' : 'var(--text-tertiary)';

  return (
    <motion.div
      className={`glass-card ${styles.tile} ${accent ? styles.accent : ''}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <div className={styles.top}>
        <span className={styles.label}>{label}</span>
        {icon && <div className={styles.icon}>{icon}</div>}
      </div>

      <div className={styles.valueRow}>
        <motion.span
          className={styles.value}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: delay + 0.1 }}
        >
          {value}
        </motion.span>
        {trendValue && (
          <span className={styles.trend} style={{ color: trendColor }}>
            {trend === 'up' ? '+' : trend === 'down' ? '' : ''}{trendValue}
          </span>
        )}
      </div>

      {sub && <p className={styles.sub}>{sub}</p>}
    </motion.div>
  );
}
