'use client';

import { motion } from 'framer-motion';

/** Activity-ring style gauge. `value` 0-100. Optional `tick` marks a target (e.g. break-even). */
export function Ring({ value, size = 120, stroke = 12, color = 'var(--text-primary)', tick, children }: {
  value: number | null; size?: number; stroke?: number; color?: string; tick?: number | null; children?: React.ReactNode;
}) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value ?? 0));
  const ang = tick != null ? (Math.max(0, Math.min(100, tick)) / 100) * 2 * Math.PI - Math.PI / 2 : 0;
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', overflow: 'visible' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--fill-tertiary)" strokeWidth={stroke} />
        {value != null && (
          <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeOpacity={.85} strokeWidth={stroke} strokeLinecap="round"
            strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - v / 100) }} transition={{ type: 'spring', stiffness: 60, damping: 18 }} />
        )}
      </svg>
      {tick != null && (
        <div style={{ position: 'absolute', left: size / 2 + r * Math.cos(ang) - 1.5, top: size / 2 + r * Math.sin(ang) - stroke / 2 - 3, width: 3, height: stroke + 6, background: 'var(--accent)', borderRadius: 2, transform: `rotate(${ang + Math.PI / 2}rad)`, transformOrigin: 'center' }} />
      )}
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>{children}</div>
    </div>
  );
}
