'use client';

import { useEffect, useLayoutEffect, useRef } from 'react';
import { animate, useReducedMotion } from 'framer-motion';

/**
 * Eased count-up that writes straight to the element's text — no React re-render per frame
 * (a dashboard has ~10 counters; re-rendering them 60×/s for a second made first paint janky).
 *
 *   const ref = useCountUpRef<HTMLSpanElement>(value, v => v.toFixed(1));
 *   return <span ref={ref}>{value.toFixed(1)}</span>;   // render the FINAL text; the hook animates from the previous value
 *
 * Under reduced motion the final text is simply left in place.
 */
export function useCountUpRef<T extends HTMLElement>(target: number | null | undefined, format: (v: number) => string, duration = 0.9) {
  const ref = useRef<T>(null);
  const from = useRef(0);
  const fmt = useRef(format);
  const reduce = useReducedMotion();

  useLayoutEffect(() => { fmt.current = format; });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || target == null) return;
    if (reduce) { from.current = target; return; }
    const c = animate(from.current, target, {
      duration, ease: [0.22, 1, 0.36, 1],
      onUpdate: v => { from.current = v; el.textContent = fmt.current(v); },
      onComplete: () => { from.current = target; el.textContent = fmt.current(target); },
    });
    return () => c.stop();
  }, [target, reduce, duration]);

  useEffect(() => () => { from.current = 0; }, []);
  return ref;
}
