'use client';

import { motion } from 'framer-motion';

/** Activity-ring style gauge (Apple Fitness feel): rounded caps, spring sweep, optional centre label. */
export function Ring({ value, size = 64, stroke = 8, color = 'var(--accent)', track = 'var(--fill-tertiary)', children, delay = 0 }: {
  value: number | null | undefined; size?: number; stroke?: number; color?: string; track?: string; children?: React.ReactNode; delay?: number;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value ?? 0)) / 100;
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - v) }}
          transition={{ type: 'spring', stiffness: 60, damping: 16, delay }}
        />
      </svg>
      {children != null && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>{children}</div>}
    </div>
  );
}

export const ROUNDED = 'ui-rounded, "SF Pro Rounded", var(--font-sans)';
