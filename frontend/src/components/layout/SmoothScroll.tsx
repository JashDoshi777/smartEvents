'use client';

import { useEffect } from 'react';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';

/**
 * Inertial, eased page scrolling (Lenis). Deliberately conservative:
 *  - mouse-wheel / trackpad only — touch devices keep native momentum scrolling (syncTouch off);
 *  - users with "reduce motion" get 1:1 scrolling (Lenis' respectReducedMotion, on by default);
 *  - nested scrollers (split-pane lists, chat, sheets, dropdowns) keep native scrolling (allowNestedScroll),
 *    and dialogs/sheets are excluded entirely so the page behind never moves.
 */
export function SmoothScroll() {
  useEffect(() => {
    if (window.matchMedia('(pointer: coarse)').matches) return;
    const lenis = new Lenis({
      autoRaf: true,
      lerp: 0.11,
      wheelMultiplier: 1,
      smoothWheel: true,
      syncTouch: false,
      allowNestedScroll: true,
      prevent: (node: HTMLElement) => !!node.closest('[role="dialog"], .sheet-backdrop, [data-lenis-prevent]'),
    });
    return () => lenis.destroy();
  }, []);
  return null;
}
