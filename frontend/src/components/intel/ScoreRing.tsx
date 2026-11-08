'use client';

import { motion } from 'framer-motion';
import { scoreColor } from './entity-utils';
import { Tick } from './Tick';

export function ScoreRing({ score, size = 96, stroke = 7, label = true }: { score: number | null; size?: number; stroke?: number; label?: boolean }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const pct = score != null ? Math.max(0, Math.min(score / 100, 1)) : 0;
  const color = scoreColor(score);
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }} role="img" aria-label={score != null ? `Score ${score} out of 100` : 'No score'}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--fill-tertiary)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - pct) }}
          transition={{ type: 'spring', stiffness: 60, damping: 16, mass: 0.9 }}
        />
      </svg>
      {label && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', lineHeight: 1 }}>
          {score != null ? (
            <>
              <span className="num-rounded" style={{ fontSize: size * 0.32, fontWeight: 700, letterSpacing: '-0.04em', color: color }}>
                <Tick value={score} />
              </span>
              <span className="t-caption text-tertiary" style={{ fontSize: Math.max(9, size * 0.11), marginTop: 2 }}>/100</span>
            </>
          ) : (
            <span className="text-tertiary" style={{ fontSize: Math.max(11, size * 0.15), fontWeight: 500 }}>Unrated</span>
          )}
        </div>
      )}
    </div>
  );
}
