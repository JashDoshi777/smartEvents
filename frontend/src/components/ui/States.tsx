'use client';

import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';

export function EmptyState({ icon, title, message, action }: { icon?: ReactNode; title: string; message?: string; action?: ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 8, padding: '48px 24px', color: 'var(--text-tertiary)' }}>
      <div style={{ opacity: .8 }}>{icon ?? <Inbox size={34} strokeWidth={1.4} />}</div>
      <p className="t-headline" style={{ color: 'var(--text-secondary)' }}>{title}</p>
      {message && <p className="t-callout" style={{ maxWidth: 340 }}>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message = 'Something went wrong loading this.', onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div role="alert" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 10, padding: '40px 24px' }}>
      <AlertTriangle size={32} strokeWidth={1.5} color="var(--warning)" />
      <p className="t-headline">Couldn’t load</p>
      <p className="t-callout text-secondary" style={{ maxWidth: 360 }}>{message}</p>
      {onRetry && <button className="btn btn-tinted btn-sm" onClick={onRetry}><RefreshCw size={14} /> Try again</button>}
    </div>
  );
}
