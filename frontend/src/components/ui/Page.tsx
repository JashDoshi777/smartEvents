'use client';

import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Topbar } from '@/components/layout/Topbar';

/**
 * Standard page frame, iOS navigation-bar behaviour:
 *  - A big left-aligned LARGE TITLE sits in the content. When it scrolls away,
 *    a compact title fades into the translucent toolbar (like Settings/Music).
 *  - `fill` pages (split panes) keep the compact title in the toolbar always.
 */
export function Page({ title, subtitle, actions, children, fill = false, maxWidth = 1480 }: {
  title: string; subtitle?: string; actions?: React.ReactNode; children: React.ReactNode; fill?: boolean; maxWidth?: number;
}) {
  const sentinel = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const el = sentinel.current;
    if (!el || fill) return;
    const io = new IntersectionObserver(([e]) => setScrolled(!e.isIntersecting), { rootMargin: '-56px 0px 0px 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, [fill]);

  return (
    <div>
      <Topbar title={title} subtitle={fill ? subtitle : undefined} showTitle={fill || scrolled} raised={fill || scrolled} />
      {fill ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
          style={{ height: 'calc(100vh - 56px)', display: 'flex', flexDirection: 'column', minHeight: 0 }}
        >
          {children}
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
          style={{ padding: '0 clamp(16px, 2.4vw, 32px) 56px', maxWidth, display: 'flex', flexDirection: 'column', gap: 20 }}
        >
          <div ref={sentinel} style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', paddingTop: 4 }}>
            <div>
              <h1 style={{ fontSize: 'clamp(1.75rem, 3vw, 2.125rem)', fontWeight: 700, letterSpacing: '-0.035em', lineHeight: 1.1 }}>{title}</h1>
              {subtitle && <p style={{ marginTop: 4, fontSize: '0.9375rem', color: 'var(--text-secondary)' }}>{subtitle}</p>}
            </div>
            {actions && <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>{actions}</div>}
          </div>
          {children}
        </motion.div>
      )}
    </div>
  );
}
