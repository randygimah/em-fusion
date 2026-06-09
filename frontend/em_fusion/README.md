# EM Fusion Frontend

React, TypeScript, Vite, Tailwind, and Vitest frontend for the EM Fusion prototype.

## Lesson One Goal

Build the smallest operational-picture slice for the GNSS degradation scenario:

- scenario status
- active hypothesis summary
- evidence summary
- map boundary ready for Mapbox
- tests around what the analyst should see

Current test focus: the analyst can see the active GNSS degradation hypothesis, confidence, evidence count, and detection summary.

## Scripts

- `npm run dev` starts the Vite dev server.
- `npm run build` checks TypeScript and creates a production build.
- `npm run lint` runs ESLint.
- `npm test` runs Vitest once.
- `npm run test:watch` runs Vitest in watch mode.

## Mapbox

The first map implementation will use direct Mapbox GL JS behind a small React boundary component.

Create a local `.env` file when Mapbox is added:

```bash
VITE_MAPBOX_TOKEN=your_token_here
```
