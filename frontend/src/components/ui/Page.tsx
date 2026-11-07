'use client';

import { motion } from 'framer-motion';
import { Topbar } from '@/components/layout/Topbar';

/**
 * Standard page frame: sticky glass Topbar + padded, max-width content column
 * with an iOS-style entrance. Every page should render inside this so spacing,
 * scroll behaviour and responsiveness stay uniform.
 *
 *   <Page title="Markets" subtitle="…" actions={<button/>}> …content… </Page>
 *
 * `fill` makes the content area exactly viewport-height-minus-topbar with no
 * outer scroll (for master/detail split panes that scroll internally).
 */
export function Page({ title, subtitle, actions, children, fill = false, maxWidth = 1480 }: {
  title: string; subtitle?: string; actions?: React.ReactNode; children: React.ReactNode; fill?: boolean; maxWidth?: number;
}) {
  return (
    <div>
      <Topbar title={title} subtitle={subtitle} />
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
        style={fill
          ? { height: 'calc(100vh - var(--topbar-height) - 24px)', display: 'flex', flexDirection: 'column', minHeight: 0 }
          : { padding: '20px clamp(16px, 2.4vw, 32px) 56px', maxWidth, display: 'flex', flexDirection: 'column', gap: 18 }}
      >
        {actions && !fill && <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>{actions}</div>}
        {children}
      </motion.div>
    </div>
  );
}
