# Glass restyle, proof of concept (D-265)

**Request (HSE Manager, 2026-10-17/18):** a glassmorphic redesign of the platform; plan in the project notes
(`glassmorphic-redesign-plan.md`), four full renders reviewed, variation **A** chosen with the recommended set:
subtle intensity, glass sidebar over an emerald mesh, solid by default on touch screens with a Glass switch,
gate verdicts / scaffold tags / print exempt, emerald and platinum palette kept.

**Scope of this PoC:** tokens (`frontend/src/styles/tokens.css`), the Tailwind mapping and glass utilities
(`src/app/globals.css`), the shell (sidebar, top bar, mobile drawer, login band), `Card`, the dashboard tiles,
bands and chart cards, dialogs, popovers and menus, the list toolbar and empty state, and a **Surface** choice in
the theme menu. No page logic, API call, permission, KPI or test id changed. Everything else (buttons, inputs,
tables, badges, toasts, the sticky action bars, the ~40 ad-hoc `rounded-xl border bg-surface` cards in the
modules) is the next pass.

Screenshots (EN / AR, light / dark, desktop / phone, solid and glass on the phone):
`docs/screenshots/glass/<name>-<locale>.png` from `e2e/screenshots-glass.spec.ts` (`SCREENSHOTS=1`). The
"before" set is `docs/screenshots/restyle/*-after.png`.

## How glass is built

| Layer | Treatment |
|---|---|
| Page plane | `--page-glow`: a deep emerald bleed from the sidebar edge (fades out at 36% of the width, so it sits under the sidebar and the first gutter, not under the cards), a jade glow at the top end, a faint emerald glow at the bottom. Painted by `.app-mesh::before` (fixed, behind the frame). Mirrored for RTL. Below 1024 px (no sidebar) only the two soft glows remain. |
| Sidebar, mobile drawer, login band | `.sidebar-glass`: `rgb(8 30 26 / 0.55)` + 24 px blur in light (dark: `rgb(5 14 12 / 0.5)`); hover / active pill `--sidebar-hover` (white 12%, dark: jade 16%) with an inset highlight (dark: a jade ring glow). |
| Top bar | `.glass-bar`: strong glass, highlight only, no lift shadow. |
| Cards, KPI tiles, dashboard bands, chart cards, toolbar, empty state | `.glass`: white 72% + 16 px blur, hairline border `rgb(16 32 29 / 0.09)`, inset top highlight, soft graphite shadow (dark: white 6.5%, border white 12%). |
| Dialog, popover, dropdown / theme menu | `.glass-strong`: white 80% + 20 px blur (dark: white 9%). The dialog overlay keeps its dim and gets a 3 px blur. |
| Tables, inputs, selects, buttons, badges, status pills | Unchanged: opaque `bg-surface` / tints inside the glass. One glass layer per stacking context, never glass in glass. |
| Gate verdict panels, scaffold tags, `.paper`, print | Unchanged solids; the print block pins every glass token to flat white. |

### Solid surface (automatic fallbacks and the user's switch)

The glass tokens resolve to the flat theme tokens, so no component has a second code path, when any of these holds:

1. the user picked **Solid** in the theme menu (`<html data-surface="solid">`, stored per device as `hse.surface`, applied before first paint by the boot script);
2. the device has a **coarse pointer** (phones, gate tablets) and the user did not pick Glass: outdoors in sun, opaque wins. "Match device" is the default;
3. the OS asks for **reduced transparency**;
4. the browser has **no `backdrop-filter`**;
5. **print**.

Test ids: `surface-glass`, `surface-solid`, `surface-auto` in the theme menu (`theme-toggle`).

## Contrast (WCAG 2.1, computed on the composited colour)

Text is measured on the glass fill composited over the strongest backdrop it can sit on. The emerald bleed reaches
≈ 0.45 alpha at the card edge nearest the sidebar at 1280 px, and 0 by the second column.

| Pair (light) | Plain page | Under the bleed (0.45) | Under the jade glow (0.5) |
|---|---|---|---|
| Body text on `.glass` | 17.3:1 | 14.2:1 | 16.5:1 |
| Secondary text on `.glass` | 7.2:1 | 5.9:1 | 6.9:1 |
| Link / primary text on `.glass` | 8.2:1 | 6.8:1 | 7.8:1 |
| Success / warning / danger text on `.glass` | 6.5 / 6.9 / 6.4 | 5.4 / 5.7 / 5.3 | 6.2 / 6.6 / 6.1 |
| Focus ring on `.glass` | 5.4:1 | 4.5:1 | 5.2:1 |
| Sidebar text / muted / indicator on the glass sidebar over the bleed | 9.0 / 5.1 / 6.6 | | |

| Pair (dark) | Plain page | Under the bleed (0.45) | Under the teal glow (0.18) |
|---|---|---|---|
| Body text on `.glass` | 13.9:1 | 10.0:1 | 9.6:1 |
| Secondary text on `.glass` | 7.8:1 | 5.6:1 | 5.4:1 |
| Primary text on `.glass` | 7.8:1 | 5.6:1 | 5.4:1 |
| Success / warning / danger text on `.glass` | 9.4 / 10.0 / 7.3 | 6.7 / 7.2 / 5.2 | 6.5 / 6.9 / 5.0 |
| Dark sidebar text / muted over the bleed | 12.6 / 6.0 | | |

Every pair stays above AA (4.5:1); body text stays above AAA everywhere. The restyle targets (secondary ≥ 6.5:1)
hold on the plain page and under the jade glow; directly under the bleed the first column of cards sits at 5.4–5.9:1,
which is why the bleed now ends at 36% of the width. Form-control borders and the status tints are measured against
their own opaque fills and are unchanged from the restyle.

## What to look at

- Dashboard, desktop, light: the mesh behind the sidebar, frosted KPI tiles and bands, the chart cards.
- Theme menu: the new Surface section (Glass / Solid / Match device).
- Dashboard, dark: the teal glow, hairline edges, jade active nav item.
- Phone: Solid by default; the same screens with Glass switched on.
- Login: the glass band and frosted card over the mesh.

## Left for the next pass

- Buttons (outline / secondary as translucent platinum), inputs, table header, badges, alerts, skeleton, toasts.
- The six sticky action bars (field run, PTW config and permits, training sessions, site-vehicle checks; the gate bar stays solid).
- The ad-hoc `rounded-xl border bg-surface` cards in the modules → `<Card>` or `.glass`; nested ones solid.
- Chart grid / axis alpha tokens and glass chart tooltips.
- Performance trace on a throttled mid-range Android profile; then flip nothing: the touch default already protects phones.
