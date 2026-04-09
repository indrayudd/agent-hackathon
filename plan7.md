# Plan 7: UI Snappiness & Fluidity

## Problems
1. Switching to notebook shows scrolling animation to saved position (CSS smooth scroll)
2. Switching to story shows top of page, then 3-4s later snaps to saved position (double rAF delay)
3. Tab switching feels laggy overall — heavy components re-mount each time

## Root Causes
1. `.notebook-scroll` has `scroll-behavior: smooth` in globals.css — makes programmatic scroll restoration animate
2. Scroll restore effect uses double `requestAnimationFrame` — 2 paint frames before setting scrollTop
3. Story tab has heavy content (many charts) that takes time to mount — scroll container not available immediately
4. Tab content is conditionally rendered (`{resolvedTab === "x" && <Component />}`) — unmounts/remounts on every switch

## Fixes
1. Remove `scroll-behavior: smooth` from `.notebook-scroll` — scroll restoration should be instant
2. Replace double rAF with immediate scrollTop set + a single rAF fallback
3. Use CSS `display: none` instead of conditional rendering for tabs — keep all tabs mounted, just hidden
4. Remove the IntersectionObserver scroll-in animation re-triggering on tab switch
