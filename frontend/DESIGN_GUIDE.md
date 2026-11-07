# LiveIQ Frontend Guide (iOS 26 / India-first)

Next.js 16 App Router · React 19 · SWR · framer-motion · recharts · CSS Modules + global tokens.
**Read `node_modules/next/dist/docs/` before using unfamiliar Next APIs — this is not the Next you remember.**

## Non-negotiables
- Apple-grade: iOS 26 "liquid glass", SF Pro type, spring motion, 44px touch targets, no emojis, no purple.
- **India-first**: ₹ everywhere, lakh/crore via `src/lib/format.ts` (`inr`, `inrCompact`, `num`, `compact`, `dateIN`). Default to Indian cities/artists. Global data is opt-in via the scope toggle.
- **No hardcoded data.** Everything comes from the backend (`src/lib/api.ts`). If a field is null show `—`, never fake numbers.
- Every data view needs 4 states: loading (skeleton, never a blank page or spinner-only), empty (`EmptyState`), error (`ErrorState` with retry), success.
- Works at 390px phone width through 1920px desktop. No horizontal page scroll. Test both themes.
- Never invent features that need a missing backend endpoint. If a button exists it must work.

## Building blocks (use these — do not re-implement)
- `components/ui/Page.tsx` — `<Page title subtitle actions fill?>` wraps EVERY page (sticky Topbar + padded content). Remove old `padding-top: 60/80px`, `margin-top: 60px`, `calc(100vh - 60px)` hacks: the topbar is sticky and in-flow now. For split panes use `<Page fill>` and give panes `min-height:0; overflow:auto`.
- `components/ui/GlassCard`, `MetricTile`, `Skeleton` (`Skeleton`, `SkeletonCard`, `SkeletonRows`), `States` (`EmptyState`, `ErrorState`), `Controls` (`Segmented`, `ChipRow`, `Switch`), `Sheet`, `Toast` (`useToast()`).
- `components/providers/MarketScopeProvider` — `useMarketScope()` → `{scope:'india'|'global', isIndia}`; `isIndianEntity(e)`. Pass `market=india|global` to backend endpoints that support it (`/dashboard/summary`, `/trends/breakout`, `/trends/viral`), else filter client-side.
- Global CSS classes in `app/globals.css`: `.btn .btn-primary .btn-tinted .btn-ghost .btn-danger .btn-sm .btn-icon`, `.chip`, `.seg`, `.switch`, `.input`, `.list-group/.list-row`, `.table`, `.badge-*`, `.skeleton`, `.glass-card`, `.t-*` type scale, `.tnum`. Tokens: `--accent --positive --negative --warning --saffron --c1..c8 --glass-* --text-* --fill-* --divider --radius-*`. Use tokens only — no raw hex except in charts via `var(--cN)`.
- Data fetching: `useSWR(key, fetcher)`; global SWRConfig (in `lib/swr.tsx`) already persists cache to localStorage + keeps previous data, so don't add your own loading flicker. Include the scope in the SWR key.
- Motion: spring/ease-out via framer-motion, 200–400ms, `whileTap={{scale:.97}}` on tappable things, respect reduced motion. Lists stagger in subtly. No jank/layout shift.
- Charts (recharts): rounded bars/area gradients, no chart junk, token colours, glass tooltip, axis labels in tertiary text, sensible INR/number formatting, ResponsiveContainer with fixed-height parent, skeleton while loading.

## Testing
Playwright is installed (`@playwright/test`, chromium). Dev server: http://localhost:3000, API: http://localhost:8000. Auth: put tokens in localStorage (`liveiq_access_token`, `liveiq_refresh_token`) — see `e2e/shot.mjs` for a login + screenshot helper. Put specs in `e2e/*.spec.ts` (config: `playwright.config.ts`).
