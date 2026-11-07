'use client';

import { useEffect, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'framer-motion';

/** Springy count-up for hero figures. `format` renders the in-flight value. */
export function CountUp({ value, format = v => String(Math.round(v)) }: { value: number; format?: (v: number) => string }) {
  const reduce = useReducedMotion();
  const [v, setV] = useState(reduce ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduce) { setV(value); return; }
    const c = animate(from.current, value, { type: 'spring', stiffness: 70, damping: 18, onUpdate: x => { from.current = x; setV(x); } });
    return () => c.stop();
  }, [value, reduce]);
  return <>{format(v)}</>;
}
