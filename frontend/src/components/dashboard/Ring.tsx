'use client';

import { motion } from 'framer-motion';

/** Activity-ring style gauge. value 0-100. */
export function Ring({ value, size = 120, stroke = 12, color = 'var(--accent)', children }: {
  value: number | null | undefined; size?: number; stroke?: number; color?: string; children?: React.ReactNode;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value ?? 0));
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--fill-tertiary)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - v / 100) }}
          transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>{children}</div>
    </div>
  );
}

/** Thin stacked proportion bar with legend-friendly colours. */
export function StackBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return (
    <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', gap: 2, background: 'var(--fill-quaternary)' }} role="img" aria-label={parts.map(p => `${p.label} ${p.value}`).join(', ')}>
      {parts.filter(p => p.value > 0).map(p => (
        <motion.div key={p.label} style={{ background: p.color, borderRadius: 4 }} initial={{ flexGrow: 0 }} animate={{ flexGrow: p.value / total }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }} />
      ))}
    </div>
  );
}
