'use client';

import { useEffect, useRef, useState } from 'react';

/** Number that eases up to its value (instant under reduced motion; null shows a dash). */
export function Tick({ value, decimals = 0, duration = 700, suffix = '' }: { value: number | null | undefined; decimals?: number; duration?: number; suffix?: string }) {
  const [shown, setShown] = useState(value ?? 0);
  const from = useRef(0);
  useEffect(() => {
    if (value == null) return;
    const reduce = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) { setShown(value); return; }
    const start = performance.now(), a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration), e = 1 - Math.pow(1 - p, 3);
      setShown(a + (value - a) * e);
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  if (value == null) return <>—</>;
  return <>{shown.toFixed(decimals)}{suffix}</>;
}
