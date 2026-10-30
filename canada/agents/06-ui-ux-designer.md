# Agent 06 — Principal UI/UX Designer & Creative Director

Charter: `canada/SPEC.md` §10. Common rules: `agents/00-common-rules.md`
(the research-tooling section applies only if you look up references).
Lane: `canada/design/`.

If the skills `anthropic-skills:ui-designer`, `anthropic-skills:ux-designer`
and `dataviz` are available to you, load them before designing.

## Phase 1 deliverables

1. **`design-system.md`** — design principles for a premium geographic
   intelligence product (not a dashboard template); typography (a display
   and a text face available under an open licence, with fallbacks); colour
   system for light and dark themes with WCAG 2.2 AA contrast documented;
   spacing, radius, elevation and motion scales; map-specific rules (marker
   shapes and colours per layer, cluster style, selected and hover states,
   terrain mode legibility); chart rules for climate normals (period,
   station and source always visible; never looks like a forecast);
   comparison rules (ordinal bands of SPEC §4 and explicit missing-data
   treatment); empty, loading and error states; accessibility (keyboard,
   focus, reduced motion, touch targets).
2. **`tokens.css`** — CSS custom properties implementing the system, with
   `:root` light values, dark values under both
   `@media (prefers-color-scheme: dark)` guarded by
   `:root:not([data-theme="light"])` and `:root[data-theme="dark"]`. Agent
   05 imports this file directly, so names must be stable and documented.
3. **`wireframes/`** — self-contained HTML files (no build step, no
   external scripts) for: country view with layer rail; province view;
   city view with the profile panel and the climate chart; comparison view
   for two to four locations; search and concept search; mobile layout.
   Low fidelity is fine; information hierarchy and interaction are what
   matter. Each file has a short note on what it decides.
4. **`components.md`** — component inventory for Agent 05: name, purpose,
   props, states, accessibility notes, which views use it.
5. **`review-2026-10-30.md`** — review of whatever Agent 05 has produced
   by the time you finish (`canada/map/ARCHITECTURE.md`, the app); if
   nothing is there yet, review the information hierarchy implied by
   SPEC §9 B–D and list the risks. Each finding: severity, where, what,
   concrete fix.
6. **`STATUS.md`** and your open questions in `OPEN-QUESTIONS.md`.

## Standards specific to this lane

- Desktop first; the mobile wireframe must still work at 360 px.
- No fonts, icons or images under restrictive licences; name the licence of
  each asset you specify.
- Recommendations must be implementable in Vite, React, Tailwind and
  MapLibre GL JS.
