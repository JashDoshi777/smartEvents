'use client';

import useSWR, { mutate } from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import { Star, X } from 'lucide-react';
import { Topbar } from '@/components/layout/Topbar';
import { GlassCard } from '@/components/ui/GlassCard';
import { getWatchlist, removeFromWatchlist } from '@/lib/api';
import styles from './page.module.css';

export default function WatchlistPage() {
  const { data, isLoading } = useSWR('watchlist', () => getWatchlist(), { shouldRetryOnError: false });
  const entities = data?.watchlist ?? [];

  async function handleRemove(entityId: string) {
    await removeFromWatchlist(entityId);
    mutate('watchlist');
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar title="Watchlist" subtitle="Entities you're tracking — their signals get priority in your notification feed" />

      <div className={styles.page}>
        {isLoading ? (
          <div className={styles.grid}>
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="skeleton" style={{ height: 78, borderRadius: 14 }} />
            ))}
          </div>
        ) : entities.length === 0 ? (
          <GlassCard className={styles.placeholder} delay={0.05}>
            <Star size={32} color="var(--text-tertiary)" strokeWidth={1.5} />
            <p className="t-headline text-tertiary" style={{ marginTop: 16 }}>Your watchlist is empty</p>
            <p className="t-callout text-tertiary" style={{ marginTop: 6, maxWidth: 360, textAlign: 'center' }}>
              Star an artist from the Intelligence Hub to track them here — their alerts will surface first in your notifications.
            </p>
          </GlassCard>
        ) : (
          <div className={styles.grid}>
            <AnimatePresence>
              {entities.map((e, i) => (
                <motion.div
                  key={e.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.25, delay: i * 0.03 }}
                >
                  <GlassCard className={styles.card}>
                    <div className={styles.avatar}>{e.name.charAt(0).toUpperCase()}</div>
                    <div className={styles.info}>
                      <span className={`t-callout text-primary ${styles.name}`}>{e.name}</span>
                      <span className="t-caption text-tertiary">
                        {e.category ?? 'Music'}{e.is_international ? ' · Global' : ' · India'}
                      </span>
                    </div>
                    <button className={styles.removeBtn} onClick={() => handleRemove(e.id)} title="Remove from watchlist">
                      <X size={16} />
                    </button>
                  </GlassCard>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
