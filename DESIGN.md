---
name: EM Fusion
colors:
  surface: '#10131a'
  surface-dim: '#10131a'
  surface-bright: '#363941'
  surface-container-lowest: '#0b0e15'
  surface-container-low: '#191b23'
  surface-container: '#1d2027'
  surface-container-high: '#272a31'
  surface-container-highest: '#32353c'
  on-surface: '#e1e2ec'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#e1e2ec'
  inverse-on-surface: '#2e3038'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#4cd7f6'
  on-secondary: '#003640'
  secondary-container: '#03b5d3'
  on-secondary-container: '#00424e'
  tertiary: '#ffb786'
  on-tertiary: '#502400'
  tertiary-container: '#df7412'
  on-tertiary-container: '#461f00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#acedff'
  secondary-fixed-dim: '#4cd7f6'
  on-secondary-fixed: '#001f26'
  on-secondary-fixed-variant: '#004e5c'
  tertiary-fixed: '#ffdcc6'
  tertiary-fixed-dim: '#ffb786'
  on-tertiary-fixed: '#311400'
  on-tertiary-fixed-variant: '#723600'
  background: '#10131a'
  on-background: '#e1e2ec'
  surface-variant: '#32353c'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  data-mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
  label-caps:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 16px
  margin-edge: 24px
  panel-padding: 12px
  stack-gap: 8px
---

## Brand & Style

The design system is engineered for high-stakes electromagnetic situational awareness, prioritizing precision, speed of cognition, and technical authority. The aesthetic is **Corporate Modern** with a **Technical** edge, moving away from "gamer" aesthetics toward a disciplined, analytical interface suitable for defense and infrastructure monitoring.

The visual language emphasizes clarity through a "Data-First" approach. Every pixel serves a functional purpose, utilizing a dark-mode-first architecture to reduce eye strain during long-duration shifts. The emotional response should be one of calm control, reliability, and absolute accuracy. The interface stays out of the way of the data, using subtle luminosity and structured grids to organize complex signal environments.

## Colors

This design system utilizes a tiered dark palette to establish depth and hierarchy without relying on heavy shadows. 

- **Foundational Layers:** The background uses `#0B101B` for the lowest level (workspace) and `#111827` for surface elements (cards, sidebars).
- **Accents & Action:** Muted Blue is the primary action color, while Cyan is reserved for AI-assisted insights and active signal highlighting.
- **Semantic Logic:** Color is used sparingly and only to denote status. Emerald indicates a nominal environment. Amber and Red are reserved strictly for anomalies and critical interference, ensuring high "pop" against the cool-toned base. 
- **Grays:** Cool grays are used for metadata and secondary labels to maintain high information density without visual clutter.

## Typography

The typography system relies on a dual-font strategy: **Inter** for UI controls, navigation, and general readability; and **JetBrains Mono** for all telemetry, coordinates, frequency data, and timestamps.

- **Scale:** Sizes are kept intentionally small to support high information density. 
- **Readability:** Line heights are tight but legible to allow for maximum vertical data display.
- **Emphasis:** Use the `label-caps` style for section headers within panels and `data-mono` for any value that may change dynamically, preventing "jumping" layouts during data refreshes.

## Layout & Spacing

This design system uses a **Fixed Grid** logic for primary dashboard layouts. The workspace is divided into a 12-column grid with a 16px gutter.

- **Density:** We utilize a 4px baseline grid. Most components use 8px (2 units) or 12px (3 units) of internal padding to maintain a compact, "instrumentation-style" look.
- **Panels:** Sidebars and utility drawers have fixed widths (e.g., 280px for the primary nav, 320px for the analysis inspector) to ensure the central map/graph area remains consistent. The primary nav is the one exception: it collapses to a 56px icon rail and back, at the analyst's choice, so the map can have the width when it is wanted. Both widths are fixed — it is two states, not a draggable panel — and the collapsed state keeps every entry and the active indicator, dropping only the labels.
- **Mobile:** While primarily a desktop experience, the layout reflows to a single column for the inspector and a condensed header on tablet/mobile devices.

## Elevation & Depth

To maintain a professional, flat-technical aesthetic, this design system avoids soft, fuzzy shadows. Instead, it uses **Tonal Layering** and **Low-Contrast Outlines**.

1.  **Level 0 (Background):** `#0B101B` — The canvas.
2.  **Level 1 (Surface):** `#111827` — Cards and panels.
3.  **Borders:** Every surface element must have a 1px solid border of `#1F2937` (for neutral states) or a dimmed version of the accent color (for active states).
4.  **Selection:** Active elements use a subtle inner-glow or a `2px` left-edge accent bar in Primary Blue.
5.  **Overlays:** Modals and tooltips use a slightly darker fill with a more prominent 1px border (`#374151`) to separate them from the background.

## Shapes

The shape language is **Soft (0.25rem)**. This slight rounding provides a modern touch while maintaining the structural integrity of a technical dashboard.

- **Components:** Buttons, input fields, and small cards use a 4px radius.
- **Large Containers:** Dashboard widgets and main panels use 8px (rounded-lg) for a distinct separation of content areas.
- **Data Points:** Markers on maps or charts should be geometric (circles, diamonds, or triangles) with sharp or 1px rounded corners to denote different signal types.

## Components

- **Technical Cards:** Background `#111827`, 1px border `#1F2937`. Header areas should have a subtle bottom border and include a "collapse" or "fullscreen" icon.
- **Status Badges:** Use a "dot + text" format. The dot should have a slight outer glow (5px blur) of its own color to signify "live" status. 
- **Data Tables:** Row-based with alternating subtle backgrounds. No vertical lines; only 1px horizontal dividers. Use `data-mono` for all numeric cells, right-aligned.
- **Buttons:** 
    - *Primary:* Solid `#3B82F6` with white text. 
    - *Secondary:* Ghost style with `#3B82F6` border. 
    - *Utility:* Dark gray background with subtle hover states for map controls.
- **Input Fields:** Inset appearance with `#0B101B` background and `#1F2937` border. Focus state should change border to `#3B82F6` with no glow.
- **Map Controls:** Floating vertical stacks of square icon-buttons, placed in the top-right of the viewport.
- **Sidebar Navigation:** Slim icons with labels. Active states utilize a "high-visibility" indicator—a small 2px cyan line on the far left.