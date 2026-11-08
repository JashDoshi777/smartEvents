'use client';

import { useEffect, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'framer-motion';

/**
 * Eased count-up from the previously shown value to `target`.
 * Returns the target immediately under reduced motion (derived, no state write).
 * Returns null while there is no target.
 */
export function useCountUp(target: number | null | undefined, duration = 0.9): number | null {
  const reduce = useReducedMotion();
  const [n, setN] = useState(0);
  const from = useRef(0);

  useEffect(() => {
    if (target == null || reduce) return;
    const c = animate(from.current, target, {
      duration, ease: [0.22, 1, 0.36, 1],
      onUpdate: v => { from.current = v; setN(v); },
    });
    return () => c.stop();
  }, [target, reduce, duration]);

  if (target == null) return null;
  return reduce ? target : n;
}
