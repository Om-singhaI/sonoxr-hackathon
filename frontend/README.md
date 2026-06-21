# SonoXR — Landing Page

Scroll-cinematic marketing landing page for SonoXR, a medical-XR product that
reconstructs a beating 3D heart from a 2D cardiac ultrasound for Meta Quest 3.

A single WebGL heart is pinned behind the content. As you scroll, the camera
orbits and dollies, the heart beats, then bursts into ~3,000 particles that drain
into a sloshing pool of "blood," travels through the middle sections as liquid, and
reassembles into the whole heart exactly as the final "Get access" slide settles.

Built from the design handoff in `design_handoff_sonoxr_landing/` (React + TypeScript
+ Vite + three).

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # typecheck + production bundle → dist/
npm run preview  # serve the production build
```

## Architecture

- **`src/App.tsx`** — the 8 transparent content sections (z-index 10), the fixed top
  bar, the right-edge nav dots, the fixed backdrop gradient layers, and the
  IntersectionObserver reveal-on-scroll. Copy is final/verbatim per the handoff.
- **`src/HeartScene.tsx`** — the entire WebGL engine in one imperative `useEffect`:
  owns the renderer, the single rAF loop, and the scroll/mouse/resize listeners.
  Everything is driven by a continuous scalar `f = sectionIndex + intra-section
  progress`, recomputed each frame from `getBoundingClientRect()`. Drives the camera
  keyframes, heartbeat, the heart→particles→blood-pool "melt", the ~3000
  surface-sampled dissolve particles, and the fullscreen ortho blood-pool shader.
- **`public/heart.glb`** — the beating-heart model with baked animation. Sampled for
  the dissolve particles; falls back to a procedural ico-sphere heart if it fails to load.

All per-frame work is kept out of React state.

### Performance

- `renderer.setPixelRatio(min(dpr, 1.5))`
- the fullscreen blood-pool pass is skipped whenever no blood/particles are on screen
  (slides 1–5) — the single biggest win
- the rAF loop pauses when `document.hidden`
- particles are one `Points` draw call updated in a typed array
- GL resources are disposed on unmount

## Placeholder CTAs (TODO — client to wire real destinations)

These three "money" CTAs are dead ends, wired to in-page anchors and marked with a
`data-todo` attribute + `TODO(client)` comments in `src/App.tsx`:

| CTA | Where | Should become |
|---|---|---|
| Watch the Quest 3 demo | hero | real demo (video or `/demo` viewer) |
| Request access / Request a pilot | top bar + access | real Request Access form/route |
| Read the technical write-up | access | docs / write-up page |

The in-page section links and the 8 nav dots are real and final.
