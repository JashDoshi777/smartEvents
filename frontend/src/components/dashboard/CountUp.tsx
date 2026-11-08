'use client';

import { useCountUpRef } from '@/lib/useCountUp';

/** Smooth number count-up for hero figures (instant under reduced motion). */
export function CountUp({ value, format = (n: number) => String(Math.round(n)), decimals = 0 }: { value: number | null | undefined; format?: (n: number) => string; decimals?: number }) {
  const show = (n: number) => (decimals ? n.toFixed(decimals) : format(n));
  const ref = useCountUpRef<HTMLSpanElement>(value, show);
  if (value == null) return <>—</>;
  return <span ref={ref}>{show(value)}</span>;
}
