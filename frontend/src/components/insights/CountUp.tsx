'use client';

import { useEffect, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'framer-motion';

/** Counts a number up with a spring; renders instantly under reduced motion. */
export function CountUp({ value, format, ...rest }: { value: number; format: (n: number) => string } & React.HTMLAttributes<HTMLSpanElement>) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduce) { setN(value); return; }
    const c = animate(from.current, value, { type: 'spring', stiffness: 60, damping: 18, onUpdate: v => { from.current = v; setN(v); } });
    return () => c.stop();
  }, [value, reduce]);
  return <span {...rest}>{format(Math.round(n))}</span>;
}
