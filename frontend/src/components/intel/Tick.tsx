'use client';

import { useCountUpRef } from '@/lib/useCountUp';

/** Number that eases up to its value (instant under reduced motion; null shows a dash). */
export function Tick({ value, decimals = 0, duration = 700, suffix = '' }: { value: number | null | undefined; decimals?: number; duration?: number; suffix?: string }) {
  const show = (n: number) => `${n.toFixed(decimals)}${suffix}`;
  const ref = useCountUpRef<HTMLSpanElement>(value, show, duration / 1000);
  if (value == null) return <>—</>;
  return <span ref={ref}>{show(value)}</span>;
}
