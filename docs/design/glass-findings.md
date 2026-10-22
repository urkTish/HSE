# Glass restyle (D-277 proof of concept, D-278 second pass)

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
| Top bar, the ten sticky action bars (page-level and card footers) | `.glass-bar`: strong glass, highlight only, no lift shadow. The responsive bars (`sm:static`) drop fill, shadow and blur once they stop being sticky. |
| Cards, KPI tiles, dashboard bands, chart cards, toolbar, tables, form sections (`FormSection`, legend floated inside the box), module cards (imports, user invite, site vehicles, permits, incidents, muster) | `.glass`: white 72% + 16 px blur, hairline border `rgb(16 32 29 / 0.09)`, inset top highlight, soft graphite shadow (dark: white 6.5%, border white 12%). |
| Dialog, popover, dropdown / theme menu, AI panel, chart tooltip, the neutral toast | `.glass-strong`: white 80% + 20 px blur (dark: white 9%). The dialog overlay keeps its dim and gets a 3 px blur. |
| Inputs, selects, textareas, multi-select trigger, outline / secondary / destructive-outline buttons | `bg-control` (`--control-glass`): white 60% in light; in dark the surface colour at 60%, so the `--input` border keeps >= 3.3:1 under the emerald bleed (white at 5% dropped it to 2.3:1). Borders, focus ring and the solid emerald primary button unchanged. |
| Table header band | `bg-table-head` (`--table-head-glass`): graphite 4.5% (dark: white 5%) over the table's glass. Rows stay transparent with the accent hover. |
| Nested panels: a card inside a card, import count tiles, notes inside a form, the empty state | `.glass-soft` / `bg-glass-soft`: white 45% (dark: white 4%), hairline border, **no blur, no lift**. Any `.glass` placed inside `.glass`, `.glass-strong` or `.glass-bar` flattens to this by a descendant rule, so one glass layer per stacking context is enforced by CSS, not by review. `.glass-strong` is exempt from the rule (floating layers keep their blur wherever they mount). |
| Badges, status pills, danger / warning / success alerts, chips | Unchanged solid tints. The info alert and the skeleton soften to 85% / 70%. |
| Toasts (sonner) | Neutral toast: strong glass through sonner's `--normal-*` variables plus unlayered `backdrop-filter` / shadow rules (sonner's stylesheet is unlayered, so a layered utility would lose). Success / error / warning / info keep sonner's solid rich colours and get `backdrop-filter: none`. |
| Charts | Series colours unchanged; `--chart-grid` / `--chart-axis` are alpha tokens (graphite 10% / 26%, dark white 10% / 22%) so they sit on glass and on solid alike; tooltip `.glass-strong`. |
| Gate check (`gate/gate-check.tsx`), certificate check (`cert/check.tsx`), scaffold tags, `.paper`, print | Unchanged solids (read in direct sun on gate devices and by third parties); the print block pins every glass token to flat white. |

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

| Pair (second pass) | Light, under the bleed | Light, plain | Dark, under the bleed | Dark, plain |
|---|---|---|---|---|
| `--input` border on the control fill (needs 3:1) | 3.3:1 | 3.6:1 | 3.5:1 | 3.9:1 |
| Body text on the control fill | 16.3:1 | 17.6:1 | 12.9:1 | 14.5:1 |
| Secondary text / placeholder base on the control fill | 6.8:1 | 7.3:1 | 7.2:1 | 8.1:1 |
| Secondary text on the table header band | 5.5:1 | 6.6:1 | 4.7:1 | 6.7:1 |
| Secondary / body text on `.glass-soft` | 6.6 / 15.8 | 7.3 / 17.5 | 4.9 / 8.8 | 6.9 / 12.4 |

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

## Second pass (D-278, 2026-10-19)

Done in one pass on the HSE Manager's "yes to everything": controls, tables, form sections, the ten sticky bars, the
module cards, nested panels, toasts, chart tokens and tooltip, as the layer table above records. Still solid on purpose:
gate check, certificate check, scaffold tags, badges, status alerts, print, repeated list rows (training session
list items, register rows) and the sidebar project switcher.

## Left

- Performance trace on a throttled mid-range Android profile (phones default to Solid, so this only matters for
  users who switch Glass on by hand).
- Sonner's own light / dark theme follows the OS, not the app's theme (pre-existing).
