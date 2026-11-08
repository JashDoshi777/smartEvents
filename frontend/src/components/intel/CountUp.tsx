'use client';

import { useCountUpRef } from '@/lib/useCountUp';

/** Count-up for hero figures. `format` renders the in-flight value. */
export function CountUp({ value, format = v => String(Math.round(v)) }: { value: number; format?: (v: number) => string }) {
  const ref = useCountUpRef<HTMLSpanElement>(value, format);
  return <span ref={ref}>{format(value)}</span>;
}
