'use client';

import { useEffect, useRef, useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { AnimatePresence, motion } from 'framer-motion';
import { Bell, Info, TrendingUp, Flame, CheckCheck, Star } from 'lucide-react';
import { getNotifications, getUnreadCount, markNotificationRead, markAllNotificationsRead, NotificationItem, NotificationsResponse } from '@/lib/api';
import { timeAgo as ago } from '@/lib/format';
import styles from './NotificationBell.module.css';

function severityColor(sev: string) {
  if (sev === 'high' || sev === 'critical') return 'var(--negative)';
  if (sev === 'medium') return 'var(--accent)';
  return 'var(--text-tertiary)';
}

function typeIcon(type: string) {
  if (type === 'search_breakout') return <TrendingUp size={13} />;
  if (type === 'news_burst') return <Flame size={13} />;
  return <Info size={13} />;
}

function NotificationRow({ n, onRead }: { n: NotificationItem; onRead: (id: string) => void }) {
  return (
    <button
      className={styles.row}
      role="menuitem"
      aria-label={`${n.severity} severity: ${n.title ?? n.entity ?? 'Signal detected'}${n.is_read ? ' (read)' : ' (unread)'}`}
      onClick={() => !n.is_read && onRead(n.id)}
      style={{ opacity: n.is_read ? 0.55 : 1 }}
    >
      <div className={styles.rowIcon} style={{ color: severityColor(n.severity) }}>
        {typeIcon(n.type)}
      </div>
      <div className={styles.rowBody}>
        <p className={styles.rowTitle}>
          {n.is_watched && <Star size={11} fill="var(--warning)" color="var(--warning)" style={{ marginRight: 4, verticalAlign: -1 }} />}
          {n.title ?? n.entity ?? 'Signal detected'}
        </p>
        {n.message && <p className={styles.rowMessage}>{n.message}</p>}
        <span className={styles.rowTime}>{n.detected_at ? ago(n.detected_at) : ''}</span>
      </div>
      {!n.is_read && <div className={styles.unreadDot} />}
    </button>
  );
}

const PREF_KEY = 'liveiq-notif-watchlist-only';
export function readWatchlistOnly(): boolean { try { return localStorage.getItem(PREF_KEY) === '1'; } catch { return false; } }
export function writeWatchlistOnly(v: boolean) { try { localStorage.setItem(PREF_KEY, v ? '1' : '0'); window.dispatchEvent(new Event('liveiq-prefs')); } catch { /* storage unavailable */ } }

export function NotificationBell() {
  const [watchOnly, setWatchOnly] = useState(false);
  useEffect(() => {
    const sync = () => setWatchOnly(readWatchlistOnly());
    sync();
    window.addEventListener('liveiq-prefs', sync);
    return () => window.removeEventListener('liveiq-prefs', sync);
  }, []);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { mutate } = useSWRConfig(); // bound to the provider cache in lib/swr.tsx
  const { data: countData } = useSWR('notifications/unread-count', getUnreadCount, {
    refreshInterval: 60000,
    shouldRetryOnError: false,
  });
  const { data: listData, isLoading, error: listError, mutate: reloadList } = useSWR(
    open ? 'notifications/list' : null,
    () => getNotifications(),
    { refreshInterval: 60000, shouldRetryOnError: false }
  );

  const notifications = (listData?.notifications ?? []).filter(n => !watchOnly || n.is_watched);
  // The server count is the single source of truth: the list is capped (newest 20),
  // so deriving the badge from it would under-report when more are unread.
  const unreadCount = countData?.unread_count ?? 0;
  const [failed, setFailed] = useState(false);

  async function handleRead(id: string) {
    setFailed(false);
    // Optimistic: flip the row and decrement the badge instantly, then reconcile with the server.
    void mutate('notifications/list', (cur: NotificationsResponse | undefined) => cur && ({ ...cur, notifications: cur.notifications.map(n => n.id === id ? { ...n, is_read: true } : n) }), { revalidate: false });
    void mutate('notifications/unread-count', (cur: { unread_count: number } | undefined) => cur && ({ unread_count: Math.max(0, cur.unread_count - 1) }), { revalidate: false });
    try { await markNotificationRead(id); } catch { setFailed(true); }
    void mutate('notifications/unread-count');
    void mutate('notifications/list');
  }

  async function handleReadAll() {
    setFailed(false);
    void mutate('notifications/list', (cur: NotificationsResponse | undefined) => cur && ({ ...cur, notifications: cur.notifications.map(n => ({ ...n, is_read: true })) }), { revalidate: false });
    void mutate('notifications/unread-count', { unread_count: 0 }, { revalidate: false });
    try { await markAllNotificationsRead(); } catch { setFailed(true); }
    void mutate('notifications/unread-count');
    void mutate('notifications/list');
  }

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <div className={styles.wrap} ref={containerRef}>
      <button
        className="btn btn-icon"
        title="Notifications"
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="notification-dropdown"
        onClick={() => setOpen(o => !o)}
        style={{ position: 'relative' }}
      >
        <Bell size={16} />
        {unreadCount > 0 && (
          <span className={styles.badge}>{unreadCount > 9 ? '9+' : unreadCount}</span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className={styles.backdrop} onClick={() => setOpen(false)} />
            <motion.div
              id="notification-dropdown"
              role="menu"
              aria-label="Notifications"
              className={styles.dropdown}
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.18, ease: [0.25, 0.46, 0.45, 0.94] }}
            >
              <div className={styles.header}>
                <span className="t-callout text-primary" style={{ fontWeight: 700 }}>Notifications</span>
                {unreadCount > 0 && (
                  <button className={styles.readAllBtn} onClick={handleReadAll}>
                    <CheckCheck size={12} /> Mark all read
                  </button>
                )}
              </div>

              <div className={styles.list}>
                {failed && <p className="t-caption" style={{ padding: '8px 16px', color: 'var(--negative)' }} role="alert">Couldn’t update. Try again.</p>}
                {listError && !listData ? (
                  <div className={styles.empty}>
                    <p className="t-caption text-tertiary">Couldn’t load notifications.</p>
                    <button className="btn btn-sm btn-ghost" style={{ color: 'var(--accent)', marginTop: 6 }} onClick={() => reloadList()}>Retry</button>
                  </div>
                ) : isLoading && !listData ? (
                  <div style={{ padding: 20 }}>
                    <div className="skeleton" style={{ height: 60, borderRadius: 8, marginBottom: 8 }} />
                    <div className="skeleton" style={{ height: 60, borderRadius: 8 }} />
                  </div>
                ) : notifications.length === 0 ? (
                  <div className={styles.empty}>
                    <Info size={18} color="var(--text-tertiary)" />
                    <p className="t-caption text-tertiary" style={{ marginTop: 8 }}>
                      No notifications yet — breakout and news signals will appear here once entity metrics are collected.
                    </p>
                  </div>
                ) : (
                  notifications.map(n => <NotificationRow key={n.id} n={n} onRead={handleRead} />)
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
