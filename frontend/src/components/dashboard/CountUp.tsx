'use client';

import { useCountUp } from '@/lib/useCountUp';

/** Smooth number count-up for hero figures (instant under reduced motion). */
export function CountUp({ value, format = (n: number) => String(Math.round(n)), decimals = 0 }: { value: number | null | undefined; format?: (n: number) => string; decimals?: number }) {
  const n = useCountUp(value);
  if (n == null) return <>—</>;
  return <>{decimals ? n.toFixed(decimals) : format(n)}</>;
}
