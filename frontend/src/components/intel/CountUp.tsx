'use client';

import { useCountUp } from '@/lib/useCountUp';

/** Count-up for hero figures. `format` renders the in-flight value. */
export function CountUp({ value, format = v => String(Math.round(v)) }: { value: number; format?: (v: number) => string }) {
  const n = useCountUp(value, 0.9) ?? value;
  return <>{format(n)}</>;
}
