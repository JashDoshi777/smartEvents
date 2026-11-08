'use client';

import { useCountUpRef } from '@/lib/useCountUp';

/** Counts a number up; renders instantly under reduced motion. */
export function CountUp({ value, format, ...rest }: { value: number; format: (n: number) => string } & React.HTMLAttributes<HTMLSpanElement>) {
  const show = (n: number) => format(Math.round(n));
  const ref = useCountUpRef<HTMLSpanElement>(value, show);
  return <span {...rest} ref={ref}>{show(value)}</span>;
}
