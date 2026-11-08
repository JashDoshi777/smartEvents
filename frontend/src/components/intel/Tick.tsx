'use client';

import { useCountUp } from '@/lib/useCountUp';

/** Number that eases up to its value (instant under reduced motion; null shows a dash). */
export function Tick({ value, decimals = 0, duration = 700, suffix = '' }: { value: number | null | undefined; decimals?: number; duration?: number; suffix?: string }) {
  const n = useCountUp(value, duration / 1000);
  if (n == null) return <>—</>;
  return <>{n.toFixed(decimals)}{suffix}</>;
}
