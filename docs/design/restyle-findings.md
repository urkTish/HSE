# Platform restyle: emerald and platinum (D-238)

**Request (HSE Manager, 2026-10-10):** "make it green, the eye-friendly green used in professional ads, not standard green. Where there is grey, make it platinum or something that looks 5-star. The same for shapes and buttons."

**Scope:** tokens (`frontend/src/styles/tokens.css`), the Tailwind mapping (`src/app/globals.css`), shared UI (`components/ui/*`) and the app shell. No page logic, API calls, permissions or test ids changed. No page hard-coded a theme colour; the only literal colours left are physical ones (pass-colour swatches, the QR code, canvas signatures, print borders).

Before/after set (EN and AR, desktop and 390 px phone, plus dark): `docs/screenshots/restyle/<name>-<locale>-{before,after}.png`. It comes from `e2e/screenshots-restyle.spec.ts`.

## Palette

| Role | Light | Dark |
|---|---|---|
| Brand / primary (buttons, links, nav accent) | `#0c574e` deep emerald (hue ≈171°); hover `#094740`, pressed `#073a34`, sheen `#11655a → #0c574e` | `#5cc3b3`; hover `#7fd2c4`, pressed `#49ab9c` |
| Focus ring | `#0f7566` | `#5cc9b5` |
| Page plane | `#f3f5f6` platinum | `#0a1110` |
| Surface (cards, inputs) | `#ffffff`, outline-button sheen `#ffffff → #f7f9f9` | `#111a19` |
| Muted fill / table header | `#ecf0f1` | `#182321` |
| Secondary text | `#4b5856` | `#a6b5b1` |
| Body text | `#101a18` graphite | `#e6edeb` |
| Border / strong border | `#d9dfe1` / `#c3cbce` | `#283532` / `#3a4946` |
| Form-control border | `#7d898b` | `#6c7c78` |
| Secondary / hover wash | `#eef2f3` / `#edf1f2` (platinum, not green) | `#1c2826` / `#1d2a28` |
| Sidebar | `#0b231e` emerald-black; text `#e6ecea`, muted `#a7b9b4`, active `#15392f`, indicator `#9fd9cc` | `#060f0d`; active `#12302a` |
| Neutral status | `#4b5856` on `#edf0f1` | `#b3c0bd` on `#1d2927` |
| **Safety go-green** (success text / tint) | `#216a1a` on `#e6f3dd` (was `#166534` on `#e3f4e8`) | `#7fd77a` on `#11291b` |
| **Verdict GRANTED / scaffold Green tag** (solid) | `#1b7a2b` (was `#166534`), same in both themes | same |
| Verdict / tag neutral (solid) | `#4f5b5d` | same |

These are unchanged: danger red (`#b42318`), warning amber, info blue (`#1d4f91`), the verdict amber/red/blue fills, the safety-ok…critical solids, chart series 1–8 and the C17 defect ramp. Only the grey catch-all series moved to platinum (`#8f9a9c`, dark `#6c7876`), along with the chart grid and axis.

## Brand green and safety green

- The brand is teal-leaning emerald and the safety green is a yellower signal green. Different hue and different value.
- ΔE2000 brand ↔ GRANTED solid is **21.2**, brand ↔ success text **19.8**, and dark brand ↔ dark success **19.4**. Before the change, the old success `#166534` would have sat at 9.9 from an emerald brand.
- Every safety state keeps its icon and its word (StatusBadge, verdict panel, tag chip).
- Hover washes are platinum, not mint, so a hovered row never reads as "OK".

## Contrast (WCAG 2.1, computed)

| Pair | Ratio |
|---|---|
| Body text on page | 16.2:1 (dark 16.1:1) |
| Secondary text on page / on muted | 6.8:1 / 6.5:1 (dark 9.0:1 / 7.6:1) |
| White on primary button / hover | 8.4:1 / 10.6:1 |
| Primary link text on white / on page | 8.4:1 / 7.7:1 |
| Dark primary-foreground on dark primary | 8.1:1; dark primary text on surface 8.4:1 |
| Focus ring on surface / page | 5.6:1 / 5.1:1 (dark 8.7:1) |
| Form-control border on surface | 3.6:1 (dark 4.0:1) |
| Success text on tint | 5.8:1 (dark 8.8:1) |
| Neutral badge | 6.5:1 (dark 8.0:1) |
| White on GRANTED / Green tag solid | 5.4:1: AA, and AAA for the ≥ 24 px bold verdict word. The old value was 7.1:1, traded for clear separation from the brand. |
| White on neutral verdict / tag | 7.0:1 |
| Sidebar text / muted / indicator | 13.8:1 / 8.0:1 / 10.4:1 |

## What changed in components

- **Button:**
  - Primary has a top sheen gradient, a hairline darker border, a contact shadow plus an inner highlight (`--shadow-btn`), a darker hover, and a pressed state (`--primary-active`, inset shadow, 1 px press).
  - Outline buttons are platinum: white-to-platinum sheen, strong platinum border, platinum hover. Secondary is a bordered platinum fill.
  - Destructive buttons get the same finish.
  - Every variant has a 2 px focus ring with an offset.
- **Inputs, selects and textareas:** a soft control shadow, a darker border on hover, a ring-coloured border plus outline on focus, and a muted fill when disabled.
- **Cards, tables, popovers, menus and dialogs:**
  - Explicit platinum borders and layered graphite-tinted elevation.
  - Table header in platinum with slightly tracked labels.
  - The dialog overlay gets a light blur.
- **Badges:** the neutral badge gets a platinum border. Status tones keep their tint, icon and word.
- **Radius:** the base is now 10 px. Controls use 8 px, cards and tables 14 px, pills stay full.
- **Shell:**
  - Emerald-black sidebar with a faint top light and hairline platinum dividers.
  - The active item has an inner highlight and a jade indicator bar.
  - The brand mark gets a jade ring.
  - Browser `theme-color` follows the sidebar.
- **Paper and print:** the `.paper` and print token overrides follow the new neutrals and brand, and print success uses the new signal green.

## Left as is

- The gate verdict amber, red and blue fills, so gate devices still look the same.
- Chart categorical colours, which are validated for colour-blind safety.
- Physical colour swatches on access-pass settings.
