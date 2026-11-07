'use client';

import { useEffect, useState } from 'react';
import { animate, useReducedMotion } from 'framer-motion';

/** Smooth number count-up for hero figures (instant under reduced motion). */
export function CountUp({ value, format = (n: number) => String(Math.round(n)), decimals = 0 }: { value: number | null | undefined; format?: (n: number) => string; decimals?: number }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? (value ?? 0) : 0);
  useEffect(() => {
    if (value == null) return;
    if (reduce) { setN(value); return; }
    const c = animate(0, value, { duration: 0.9, ease: [0.22, 1, 0.36, 1], onUpdate: v => setN(v) });
    return () => c.stop();
  }, [value, reduce]);
  if (value == null) return <>—</>;
  return <>{decimals ? n.toFixed(decimals) : format(n)}</>;
}
