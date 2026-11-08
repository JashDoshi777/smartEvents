'use client';

import { useCountUp } from '@/lib/useCountUp';

/** Counts a number up; renders instantly under reduced motion. */
export function CountUp({ value, format, ...rest }: { value: number; format: (n: number) => string } & React.HTMLAttributes<HTMLSpanElement>) {
  const n = useCountUp(value, 0.9) ?? value;
  return <span {...rest}>{format(Math.round(n))}</span>;
}
