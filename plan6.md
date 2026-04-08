# Plan 6: Story Tab Visual Overhaul — WOW-Factor Redesign

## Current Problems
1. Box plots extracted as 22 "Series N" line traces with legends — garbage visualization
2. Story is infinite-scroll text blocks with single full-width charts — boring layout
3. No visual hierarchy between hypotheses/sections
4. Plots are not interactive or explorable
5. No carousel or modal for multiple plots per section
6. Page design lacks polish, animations, and visual storytelling

## Design Vision
Transform the story from a linear document into an **interactive investigative report** with:
- Hero section with animated key metrics
- Hypothesis cards as collapsible/expandable sections
- Plot carousels with thumbnail previews and modal lightbox
- Animated entry transitions for sections and charts
- Constrained max-width content with generous whitespace
- Visual distinction between EDA phases and hypothesis investigations

## Implementation Tasks

### Task 1: Fix Boxplot Data at Backend (kernel_manager.py)
- When kernel fallback detects many short line traces from a boxplot, SKIP emission entirely
- The matplotlib boxplot image (PNG) will still be available as fallback
- Filter: if traces > 8 AND every trace has ≤ 5 points AND all named "Series N" → skip

### Task 2: Plot Carousel Component (new: PlotCarousel.tsx)
- When a section has multiple plots, show them in a carousel with:
  - Dot indicators at bottom
  - Left/right arrow navigation
  - Thumbnail strip below (if > 2 plots)
  - Click any plot to open fullscreen modal
- Single plots render inline (no carousel chrome)
- Smooth CSS transitions between slides

### Task 3: Plot Lightbox Modal (new: PlotLightbox.tsx)  
- Fullscreen overlay with backdrop blur
- Large plot rendering at full resolution
- Caption, title, source cell link
- Left/right navigation between section plots
- Escape/click-outside to close
- Keyboard navigation (arrow keys, escape)

### Task 4: StorySectionCard Redesign (StorySectionCard.tsx)
- Hypothesis sections get a colored left border accent
- Phase badge with icon
- Collapsible prose with "Read more" for long content
- Insights as compact pills, not bullet lists
- Plot carousel integrated below prose
- Smooth expand/collapse animation

### Task 5: StoryPane Layout Redesign (StoryPane.tsx)
- Max-width 72rem for content, centered
- Hero header with gradient background and key stats
- Visual phase timeline/progress dots between sections
- Animated section entry (intersection observer)
- Floating "jump to section" sidebar/TOC on wide screens
- Footer with generation metadata

### Task 6: CSS Animations & Polish (globals.css)
- Staggered fade-in for sections on scroll (IntersectionObserver)
- Smooth chart transitions
- Hover states on plot cards
- Print-friendly styles

## Agent Assignment
- **Agent A**: Task 1 (backend boxplot fix) — quick, independent
- **Agent B**: Tasks 2+3 (PlotCarousel + PlotLightbox) — new components
- **Agent C**: Tasks 4+5 (StorySectionCard + StoryPane redesign) — layout overhaul
- **Agent D**: Task 6 (animations + CSS) — runs after C

Agents A and B run in parallel. Agent C depends on B (carousel component). Agent D runs last.

## Verification
After each agent completes:
1. Run `npx tsc --noEmit` for type safety
2. Use Playwright to upload T1_slice.csv, wait for completion, screenshot story
3. Verify: x-axis visible, no broken charts, carousel works, modal works
